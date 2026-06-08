# -*- coding: utf-8 -*-
import os
import re
import shutil
import subprocess
import sys
import json
import threading

from PyQt6.QtCore import QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QTextEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QAbstractItemView, QCheckBox, QComboBox, QGroupBox, QFrame, QSizePolicy,
    QApplication
)

from config import resource_path


def hidden_subprocess_kwargs():
    if os.name != "nt":
        return {}
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


ADWARE_KEYWORDS = [
    "adware", "ads", "advert", "adservice", "adserver", "admob", "adcolony",
    "airpush", "appbrain", "appnext", "applovin", "chartboost", "leadbolt",
    "mopub", "revmob", "startapp", "tapjoy", "unityads", "vungle",
    "doubleclick", "mobvista", "inmobi", "ironsource", "offerwall",
    "coupon", "installer", "adclick", "popup", "popunder",
]

KNOWN_SUSPICIOUS_PACKAGES = {
    "com.android.system.service",
    "com.android.systemhelper",
    "com.google.system.service",
    "com.system.update",
    "com.system.tool",
    "com.wifi.service",
    "com.cleaner.booster",
    "com.speed.booster",
    "com.battery.saver",
    "com.privacy.lock",
}

PROTECTED_EXACT_PACKAGES = {
    "android",
    "com.android.systemui",
    "com.google.android.gms",
    "com.google.android.gsf",
    "com.google.android.packageinstaller",
    "com.google.android.permissioncontroller",
    "com.android.packageinstaller",
    "com.android.permissioncontroller",
    "com.whatsapp",
    "com.whatsapp.w4b",
    "com.google.android.dialer",
    "com.android.dialer",
    "com.google.android.contacts",
    "com.android.contacts",
    "com.google.android.apps.messaging",
    "com.android.mms",
    "com.android.phone",
    "com.google.android.youtube",
    "com.android.vending",
    "com.google.android.googlequicksearchbox",
    "com.google.android.inputmethod.latin",
}

PROTECTED_PREFIXES = (
    "com.android.",
    "com.google.android.",
    "com.samsung.",
    "com.sec.",
    "com.miui.",
    "com.xiaomi.",
    "com.huawei.",
    "com.oppo.",
    "com.vivo.",
    "com.realme.",
    "com.oneplus.",
    "com.motorola.",
)

IGNORED_FOREGROUND_PACKAGES = PROTECTED_EXACT_PACKAGES

DEFAULT_RISK_DB = {
    "version": "builtin",
    "packages": {},
    "package_prefixes": [],
    "whitelist": {},
    "protected_prefixes": [],
    "keywords": [],
    "risk_signals": {},
    "labels": {},
}

SIGNAL_MARKERS = {
    "__MF_ACCESSIBILITY__": "accessibility",
    "__MF_NOTIFICATION__": "notification_listener",
    "__MF_OVERLAY__": "overlay",
    "__MF_DEVICE_ADMIN__": "device_admin",
    "__MF_BOOT__": "boot_receiver",
}

PACKAGE_NAME_RE = re.compile(r"\b[a-zA-Z][a-zA-Z0-9_]*(:\.[a-zA-Z0-9_]+){1,}\b")
SIGNAL_IGNORE_PREFIXES = (
    "android.intent.",
    "android.permission.",
    "android.app.",
    "android.service.",
    "java.",
    "kotlin.",
)


def load_risk_db():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else root
    candidates = [
        os.path.join(app_dir, "data", "android_risk_db.json"),
        resource_path(os.path.join("data", "android_risk_db.json")),
        os.path.join(root, "data", "android_risk_db.json"),
    ]
    seen = set()
    for path in candidates:
        normalized = os.path.normcase(os.path.abspath(path)) if path else ""
        if not normalized or normalized in seen or not os.path.exists(path):
            continue
        seen.add(normalized)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                merged = DEFAULT_RISK_DB.copy()
                merged.update(data)
                return merged
        except Exception:
            continue
    return DEFAULT_RISK_DB.copy()


RISK_DB = load_risk_db()


def db_version():
    return str(RISK_DB.get("version") or "builtin")


def risk_signal_rules():
    rules = RISK_DB.get("risk_signals") or {}
    fallback = {
        "accessibility": {"weight": 28, "reason": "erişilebilirlik servisi aktif"},
        "notification_listener": {"weight": 22, "reason": "bildirim erişimi aktif"},
        "overlay": {"weight": 20, "reason": "üstte gösterme izni aktif"},
        "device_admin": {"weight": 36, "reason": "cihaz yöneticisi aktif"},
        "boot_receiver": {"weight": 10, "reason": "telefon açılışında çalışan alıcı"},
    }
    fallback.update(rules)
    return fallback


def db_rule_for_package(package_name):
    packages = RISK_DB.get("packages") or {}
    rule = packages.get(package_name)
    if isinstance(rule, dict):
        return rule
    for prefix_rule in RISK_DB.get("package_prefixes") or []:
        prefix = prefix_rule.get("prefix") if isinstance(prefix_rule, dict) else ""
        if prefix and package_name.startswith(prefix):
            return prefix_rule
    return None


def whitelist_reason(package_name):
    whitelist = RISK_DB.get("whitelist") or {}
    if package_name in whitelist:
        return str(whitelist.get(package_name) or "Korunan uygulama")
    return ""


def extract_package_names(text):
    names = set()
    for match in PACKAGE_NAME_RE.finditer(text or ""):
        name = match.group(0).strip()
        if any(name.startswith(prefix) for prefix in SIGNAL_IGNORE_PREFIXES):
            continue
        if name.count(".") < 1 or len(name) > 160:
            continue
        names.add(name)
    return names


def split_scan_sections(output):
    sections = {"packages": []}
    current = "packages"
    for line in (output or "").splitlines():
        key = SIGNAL_MARKERS.get(line.strip())
        if key:
            current = key
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return {key: "\n".join(value) for key, value in sections.items()}


def build_package_signals(sections):
    package_signals = {}
    for signal_name in SIGNAL_MARKERS.values():
        for package_name in extract_package_names(sections.get(signal_name, "")):
            package_signals.setdefault(package_name, set()).add(signal_name)
    return package_signals


APP_BADGE_COLORS = [
    ("#2563eb", "#38bdf8"),
    ("#7c3aed", "#c084fc"),
    ("#dc2626", "#fb7185"),
    ("#16a34a", "#4ade80"),
    ("#f97316", "#facc15"),
    ("#0891b2", "#22d3ee"),
    ("#be123c", "#f472b6"),
    ("#475569", "#94a3b8"),
]


def make_badge_icon(color, text="", accent=None, size=30):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    if accent:
        gradient = QLinearGradient(2, 2, size - 2, size - 2)
        gradient.setColorAt(0, QColor(accent))
        gradient.setColorAt(1, QColor(color))
        painter.setBrush(gradient)
    else:
        painter.setBrush(QColor(color))
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 9, 9)
    painter.setPen(QColor(255, 255, 255, 55))
    painter.drawRoundedRect(2, 2, size - 4, size - 4, 9, 9)
    if text:
        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setBold(True)
        font.setPointSize(10 if size >= 30 else 9)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, text[:1].upper())
    painter.end()
    return QIcon(pix)


def app_badge_icon(package_name, app_name):
    seed = sum(ord(ch) for ch in f"{package_name}:{app_name}")
    color, accent = APP_BADGE_COLORS[seed % len(APP_BADGE_COLORS)]
    letter = (app_name or package_name or "").strip()[:1]
    return make_badge_icon(color, letter, accent=accent, size=32)


def status_icon(status):
    color = {
        "virus": "#ef4444",
        "suspicious": "#f59e0b",
        "review": "#f59e0b",
        "protected": "#22c55e",
        "clean": "#38bdf8",
    }.get(status, "#38bdf8")
    symbol = {
        "virus": "!",
        "suspicious": "",
        "review": "i",
        "protected": "✓",
        "clean": "✓",
    }.get(status, "i")
    return make_badge_icon(color, symbol)


def find_adb():
    candidates = []
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else root
    candidates.extend([
        resource_path(os.path.join("platform-tools", "adb.exe")),
        resource_path("adb.exe"),
        os.path.join(app_dir, "platform-tools", "adb.exe"),
        os.path.join(app_dir, "adb.exe"),
        os.path.join(root, "adb.exe"),
        os.path.join(root, "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Android", "Sdk", "platform-tools", "adb.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Android", "platform-tools", "adb.exe"),
    ])
    path_adb = shutil.which("adb")
    if path_adb:
        candidates.append(path_adb)
    seen = set()
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate)) if candidate else ""
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def package_label(package_name):
    labels = RISK_DB.get("labels") or {}
    if package_name in labels:
        return str(labels.get(package_name) or package_name)
    clean = package_name.split(".")[-1].replace("_", " ").replace("-", " ").strip()
    known = {
        "com.whatsapp": "WhatsApp",
        "com.whatsapp.w4b": "WhatsApp Business",
        "com.google.android.youtube": "YouTube",
        "com.android.vending": "Google Play Store",
    }
    return known.get(package_name, clean.title() if clean else package_name)


def is_protected_package(package_name):
    if package_name in KNOWN_SUSPICIOUS_PACKAGES or db_rule_for_package(package_name):
        return False
    if whitelist_reason(package_name):
        return True
    if package_name in PROTECTED_EXACT_PACKAGES:
        return True
    db_prefixes = tuple(RISK_DB.get("protected_prefixes") or ())
    return package_name.startswith(PROTECTED_PREFIXES + db_prefixes)


def score_package(package_name, apk_path="", signals=None):
    signals = set(signals or [])
    signal_rules = risk_signal_rules()
    signal_reasons = [
        str(signal_rules.get(signal, {}).get("reason") or signal)
        for signal in sorted(signals)
    ]
    if is_protected_package(package_name):
        if signals:
            details = ", ".join(dict.fromkeys(signal_reasons))
            return 18, f"Korunan/resmi uygulama; izin uyarısı: {details}", "review"
        return 0, whitelist_reason(package_name) or "Korunuyor", "protected"

    db_rule = db_rule_for_package(package_name)
    text = f"{package_name} {apk_path}".lower()
    score = 0
    reasons = []
    if isinstance(db_rule, dict):
        try:
            score += int(db_rule.get("risk", 0))
        except Exception:
            pass
        if db_rule.get("reason"):
            reasons.append(str(db_rule.get("reason")))
    if package_name in KNOWN_SUSPICIOUS_PACKAGES:
        score += 75
        reasons.append("sahte sistem adı")
    keyword_rules = RISK_DB.get("keywords") or []
    db_keyword_terms = set()
    for keyword_rule in keyword_rules:
        if not isinstance(keyword_rule, dict):
            continue
        keyword = str(keyword_rule.get("term", "")).lower()
        if not keyword:
            continue
        db_keyword_terms.add(keyword)
        if keyword in text:
            try:
                score += int(keyword_rule.get("weight", 9))
            except Exception:
                score += 9
            reasons.append(str(keyword_rule.get("reason") or "reklam izi"))
    for keyword in ADWARE_KEYWORDS:
        if keyword in text and keyword not in db_keyword_terms:
            score += 9
            reasons.append("reklam izi")
    if re.search(r"(system|google|android).*(service|update|helper|tool)", text):
        score += 22
        reasons.append("sistem taklidi")
    if "/data/app/" in apk_path.lower():
        score += 3
    for signal in signals:
        rule = signal_rules.get(signal, {})
        try:
            score += int(rule.get("weight", 0))
        except Exception:
            pass
        if rule.get("reason"):
            reasons.append(str(rule.get("reason")))

    score = min(score, 100)
    if score >= 70:
        return score, ", ".join(dict.fromkeys(reasons)), "virus"
    if score >= 12:
        return score, ", ".join(dict.fromkeys(reasons)), "suspicious"
    return score, "Temiz görünüyor", "clean"


def extract_foreground_package(output):
    patterns = [
        r"(:mCurrentFocus|mFocusedApp|topResumedActivity|mResumedActivity)[^\n]*\s([a-zA-Z][\w]*(:\.[\w]+)+)/",
        r"ACTIVITY\s+([a-zA-Z][\w]*(:\.[\w]+)+)/",
        r"Window\{[^\n]*\s([a-zA-Z][\w]*(:\.[\w]+)+)/",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, output):
            package_name = match.group(1).strip()
            if package_name:
                return package_name
    return ""


class AdbWorker(QThread):
    finished_ok = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, adb_path, args, timeout=25):
        super().__init__()
        self.adb_path = adb_path
        self.args = args
        self.timeout = timeout
        self.process = None
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        try:
            if self.process and self.process.poll() is None:
                self.process.kill()
        except Exception:
            pass

    def run(self):
        try:
            if not self.adb_path:
                self.failed.emit("ADB bulunamadı. Lütfen MetaFold'u güncel kurulum paketiyle yeniden kurun veya destek ile iletişime geçin.")
                return
            self.process = subprocess.Popen(
                [self.adb_path] + self.args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding="utf-8",
                errors="replace",
                **hidden_subprocess_kwargs(),
            )
            stdout, stderr = self.process.communicate(timeout=self.timeout)
            if self.cancelled:
                return
            output = (stdout or "") + (stderr or "")
            if self.process.returncode != 0:
                self.failed.emit(output.strip() or "Cihaz ile iletişim kurulurken hata oluştu.")
                return
            self.finished_ok.emit(output)
        except subprocess.TimeoutExpired:
            try:
                if self.process and self.process.poll() is None:
                    self.process.kill()
                    self.process.communicate(timeout=2)
            except Exception:
                pass
            if self.cancelled:
                return
            self.failed.emit("İşlem zaman aşımına uğradı.")
        except Exception as exc:
            if self.cancelled:
                return
            self.failed.emit(str(exc))


class ClickableFrame(QFrame):
    clicked = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class AdbCleanerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.adb_path = find_adb()
        self.worker = None
        self.workers = []
        self.scanned_count = 0
        self.suspicious_count = 0
        self.virus_count = 0
        self.protected_count = 0
        self.busy = False
        self.monitoring = False
        self.last_foreground_package = ""
        self.monitor_error_count = 0
        self.package_signals = {}
        self.scanned_packages = {}
        self.active_filter = "all"
        self.metric_frames = {}
        self.metric_title_labels = {}
        self.current_language = "TR"
        self.current_theme = "Dark"
        self.monitor_timer = QTimer(self)
        self.monitor_timer.setInterval(5000)
        self.monitor_timer.timeout.connect(self.auto_monitor_tick)
        self.setup_ui()
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown_adb)

    def set_theme(self, theme):
        theme_text = str(theme)
        if theme_text in ["Light", "Okyanus", "Zümrüt", "Grafit"]:
            self.current_theme = theme_text
        else:
            self.current_theme = "Dark"
        self.apply_theme_style()

    def set_language(self, language):
        self.current_language = "EN" if str(language).upper() == "EN" else "TR"
        self.update_language()

    def t(self, tr_text, en_text):
        return en_text if self.current_language == "EN" else tr_text

    def update_language(self):
        if not hasattr(self, "hero_title"):
            return
        self.hero_title.setText(self.t("MetaFold Virüs Temizleyici", "MetaFold Virus Cleaner"))
        self.hero_subtitle.setText(self.t(
            f"Android reklam virüslerini güvenli şekilde bulur, resmi paketleri korur. Risk DB: {db_version()}",
            f"Safely finds Android adware and protects official packages. Risk DB: {db_version()}"
        ))
        self.warning_text.setText(self.t(
            "Telefonu bağlamadan önce USB hata ayıklamayı aktif edin. Kabloyu takınca telefonda çıkan USB hata ayıklama iznini onaylayın.",
            "Before connecting the phone, enable USB debugging. After plugging in the cable, approve the USB debugging permission on the phone."
        ))
        self.device_title.setText(self.t("Cihaz", "Device"))
        self.connected_device_label.setText(self.t("Bağlı cihaz:", "Connected device:"))
        if self.device_combo.count() and self.device_combo.itemText(0) in ["Cihaz bekleniyor", "Waiting for device"]:
            self.device_combo.setItemText(0, self.t("Cihaz bekleniyor", "Waiting for device"))
        self.btn_devices.setText(self.t("Cihaz Bul", "Find Device"))
        self.btn_scan.setText(self.t("Taramayı Başlat", "Start Scan"))
        if self.monitoring:
            self.btn_capture_ad.setText(self.t("İzlemeyi Durdur", "Stop Watch"))
        else:
            self.btn_capture_ad.setText(self.t("Otomatik İzle", "Auto Watch"))
        metric_titles = {
            "all": self.t("Taranan", "Scanned"),
            "virus": self.t("Yüksek Risk", "High Risk"),
            "suspicious": self.t("Şüpheli", "Suspicious"),
            "protected": self.t("Korunan", "Protected"),
        }
        for key, label in self.metric_title_labels.items():
            label.setText(metric_titles.get(key, label.text()))
        self.third_party_only.setText(self.t("Sadece sonradan yüklenen uygulamalar", "Only user-installed apps"))
        self.show_clean_apps.setText(self.t("Temiz uygulamaları da göster", "Show clean apps too"))
        self.app_list_title.setText(self.t("Uygulama Listesi", "Application List"))
        self.btn_select_suspicious.setText(self.t("Tehditleri Seç", "Select Threats"))
        self.btn_remove.setText(self.t("Seçilenleri Temizle", "Clean Selected"))
        if self.table.columnCount() == 5:
            self.table.setHorizontalHeaderLabels(
                ["Seç", "Risk", "Uygulama", "Paket adı", "Sonuç"]
                if self.current_language == "TR"
                else ["Select", "Risk", "Application", "Package name", "Result"]
            )
        self.update_metrics()

    def apply_theme_style(self):
        if self.current_theme == "Okyanus":
            self.setStyleSheet("""
                #VirusCleanerRoot { background: #071923; }
                #HeroFrame, #DevicePanel, #AppListPanel { background: #0b2433; border: 1px solid #155e75; border-radius: 10px; }
                #MetricFrame { background: #082333; border: 1px solid #176b82; border-radius: 8px; }
                #MetricFrame[active="true"], #MetricFrame:hover { background: #0e3a52; border: 1px solid #67e8f9; }
                #DeviceTitle { color: #ecfeff; font-weight: 900; }
                QLabel#MetricTitle { color: #a5f3fc; font-size: 12px; font-weight: 800; }
                QLabel#CleanerHeroTitle { font-size: 21px; font-weight: 900; color: #ecfeff; }
                QLabel#CleanerHeroSubtitle, #PanelHint { color: #a5f3fc; font-size: 12px; font-weight: 700; }
                #UsbDebugWarning { background: #12394b; border: 1px solid #06b6d4; border-radius: 8px; }
                QLabel#WarningIcon { background: #06b6d4; color: #06202c; border-radius: 12px; font-weight: 900; }
                QLabel#WarningText { color: #cffafe; font-size: 12px; font-weight: 800; }
                #StatusGood { color: #34d399; font-weight: 800; }
                #StatusWarn { color: #facc15; font-weight: 800; }
                #StatusBad { color: #fb7185; font-weight: 800; }
                #StatusInfo { color: #67e8f9; font-weight: 800; }
                #PanelTitle { color: #ecfeff; font-size: 15px; font-weight: 900; }
                QPushButton#DeviceAction { min-width: 118px; max-width: 150px; min-height: 32px; padding: 7px 14px; color: #ffffff; font-weight: 800; background: #0891b2; border-color: #22d3ee; }
                QTableWidget#VirusAppTable { background: #071923; alternate-background-color: #0b2a3c; color: #ecfeff; border: 1px solid #155e75; border-radius: 8px; gridline-color: transparent; selection-background-color: #0e7490; selection-color: white; }
                QTableWidget#VirusAppTable::item { padding: 8px; border-bottom: 1px solid #12394b; }
                QTableWidget#VirusAppTable::item:hover { background: #0e3a52; }
                QHeaderView::section { background: #0f3a4d; color: #ecfeff; border: none; border-right: 1px solid #176b82; border-bottom: 1px solid #67e8f9; padding: 9px 8px; font-weight: 900; }
            """)
            return

        if self.current_theme == "Zümrüt":
            self.setStyleSheet("""
                #VirusCleanerRoot { background: #eefcf6; }
                #HeroFrame, #DevicePanel, #AppListPanel { background: #f7fffb; border: 1px solid #a7d8c4; border-radius: 10px; }
                #MetricFrame { background: #ffffff; border: 1px solid #b7dfcf; border-radius: 8px; }
                #MetricFrame[active="true"], #MetricFrame:hover { background: #dff6eb; border: 1px solid #059669; }
                #DeviceTitle { color: #0f2d22; font-weight: 900; }
                QLabel#MetricTitle { color: #31584a; font-size: 12px; font-weight: 800; }
                QLabel#CleanerHeroTitle { font-size: 21px; font-weight: 900; color: #0f2d22; }
                QLabel#CleanerHeroSubtitle, #PanelHint { color: #31584a; font-size: 12px; font-weight: 700; }
                #UsbDebugWarning { background: #ecfdf5; border: 1px solid #10b981; border-radius: 8px; }
                QLabel#WarningIcon { background: #059669; color: white; border-radius: 12px; font-weight: 900; }
                QLabel#WarningText { color: #065f46; font-size: 12px; font-weight: 800; }
                #StatusGood { color: #059669; font-weight: 800; }
                #StatusWarn { color: #b45309; font-weight: 800; }
                #StatusBad { color: #dc2626; font-weight: 800; }
                #StatusInfo { color: #047857; font-weight: 800; }
                #PanelTitle { color: #0f2d22; font-size: 15px; font-weight: 900; }
                QPushButton#DeviceAction { min-width: 118px; max-width: 150px; min-height: 32px; padding: 7px 14px; color: #ffffff; font-weight: 800; background: #059669; border-color: #34d399; }
                QTableWidget#VirusAppTable { background: #ffffff; alternate-background-color: #effaf5; color: #0f2d22; border: 1px solid #b7dfcf; border-radius: 8px; gridline-color: transparent; selection-background-color: #bbf7d0; selection-color: #0f2d22; }
                QTableWidget#VirusAppTable::item { padding: 8px; border-bottom: 1px solid #d9f7ea; }
                QTableWidget#VirusAppTable::item:hover { background: #e6f7ef; }
                QHeaderView::section { background: #c7f2df; color: #064e3b; border: none; border-right: 1px solid #9bd5be; border-bottom: 1px solid #059669; padding: 9px 8px; font-weight: 900; }
            """)
            return

        if self.current_theme == "Grafit":
            self.setStyleSheet("""
                #VirusCleanerRoot { background: #111113; }
                #HeroFrame, #DevicePanel, #AppListPanel { background: #18181b; border: 1px solid #3f3f46; border-radius: 10px; }
                #MetricFrame { background: #202024; border: 1px solid #3f3f46; border-radius: 8px; }
                #MetricFrame[active="true"], #MetricFrame:hover { background: #27272a; border: 1px solid #f59e0b; }
                #DeviceTitle { color: #f4f4f5; font-weight: 900; }
                QLabel#MetricTitle { color: #d4d4d8; font-size: 12px; font-weight: 800; }
                QLabel#CleanerHeroTitle { font-size: 21px; font-weight: 900; color: #f4f4f5; }
                QLabel#CleanerHeroSubtitle, #PanelHint { color: #a1a1aa; font-size: 12px; font-weight: 700; }
                #UsbDebugWarning { background: #291c0b; border: 1px solid #f59e0b; border-radius: 8px; }
                QLabel#WarningIcon { background: #f59e0b; color: #111113; border-radius: 12px; font-weight: 900; }
                QLabel#WarningText { color: #fef3c7; font-size: 12px; font-weight: 800; }
                #StatusGood { color: #22c55e; font-weight: 800; }
                #StatusWarn { color: #f59e0b; font-weight: 800; }
                #StatusBad { color: #ef4444; font-weight: 800; }
                #StatusInfo { color: #fbbf24; font-weight: 800; }
                #PanelTitle { color: #f4f4f5; font-size: 15px; font-weight: 900; }
                QPushButton#DeviceAction { min-width: 118px; max-width: 150px; min-height: 32px; padding: 7px 14px; color: #111113; font-weight: 900; background: #f59e0b; border-color: #fbbf24; }
                QTableWidget#VirusAppTable { background: #111113; alternate-background-color: #18181b; color: #f4f4f5; border: 1px solid #3f3f46; border-radius: 8px; gridline-color: transparent; selection-background-color: #92400e; selection-color: white; }
                QTableWidget#VirusAppTable::item { padding: 8px; border-bottom: 1px solid #27272a; }
                QTableWidget#VirusAppTable::item:hover { background: #27272a; }
                QHeaderView::section { background: #2f2f34; color: #fef3c7; border: none; border-right: 1px solid #52525b; border-bottom: 1px solid #f59e0b; padding: 9px 8px; font-weight: 900; }
            """)
            return

        if self.current_theme == "Light":
            self.setStyleSheet("""
                #VirusCleanerRoot { background: #eef3f8; }
                #HeroFrame { background: #f8fbff; border: 1px solid #d5dee9; border-radius: 10px; }
                #MetricFrame { background: #f8fbff; border: 1px solid #d5dee9; border-radius: 8px; }
                #MetricFrame[active="true"] { background: #e8f1fb; border: 1px solid #2563eb; }
                #MetricFrame:hover { background: #eef6ff; border: 1px solid #60a5fa; }
                #DevicePanel { background: #f8fbff; border: 1px solid #d5dee9; border-radius: 8px; }
                #DeviceTitle { color: #0f172a; font-weight: 900; }
                QLabel#MetricTitle { color: #475569; font-size: 12px; font-weight: 800; }
                QLabel#CleanerHeroTitle { font-size: 21px; font-weight: 900; color: #0f172a; }
                QLabel#CleanerHeroSubtitle { font-size: 12px; color: #475569; }
                #UsbDebugWarning { background: #fff7ed; border: 1px solid #fb923c; border-radius: 8px; }
                QLabel#WarningIcon { background: #f97316; color: #ffffff; border-radius: 12px; font-weight: 900; }
                QLabel#WarningText { color: #9a3412; font-size: 12px; font-weight: 800; }
                QPushButton#DeviceAction {
                    min-width: 118px;
                    max-width: 150px;
                    min-height: 32px;
                    padding: 7px 14px;
                    color: #ffffff;
                    font-weight: 800;
                }
                #StatusGood { color: #16a34a; font-weight: 800; }
                #StatusWarn { color: #d97706; font-weight: 800; }
                #StatusBad { color: #dc2626; font-weight: 800; }
                #StatusInfo { color: #2563eb; font-weight: 800; }
                #AppListPanel { background: #f8fbff; border: 1px solid #d5dee9; border-radius: 10px; }
                #PanelTitle { color: #0f172a; font-size: 15px; font-weight: 900; }
                #PanelHint { color: #64748b; font-size: 12px; font-weight: 700; }
                QTableWidget#VirusAppTable {
                    background: #ffffff;
                    alternate-background-color: #f4f7fb;
                    color: #0f172a;
                    border: 1px solid #d1dbe8;
                    border-radius: 8px;
                    gridline-color: transparent;
                    selection-background-color: #dbeafe;
                    selection-color: #0f172a;
                }
                QTableWidget#VirusAppTable::item {
                    padding: 8px;
                    border-bottom: 1px solid #e2e8f0;
                }
                QTableWidget#VirusAppTable::item:hover {
                    background: #edf5ff;
                }
                QHeaderView::section {
                    background: #e6eef8;
                    color: #1e293b;
                    border: none;
                    border-right: 1px solid #c7d4e4;
                    border-bottom: 1px solid #2563eb;
                    padding: 9px 8px;
                    font-weight: 900;
                }
            """)
            return

        self.setStyleSheet("""
            #HeroFrame { background: #111827; border: 1px solid #253044; border-radius: 10px; }
            #MetricFrame { background: #1f2937; border: 1px solid #334155; border-radius: 8px; }
            #MetricFrame[active="true"] { background: #243247; border: 1px solid #60a5fa; }
            #MetricFrame:hover { background: #243247; border: 1px solid #38bdf8; }
            #DevicePanel { background: #111318; border: 1px solid #303846; border-radius: 8px; }
            #DeviceTitle { color: #f8fafc; font-weight: 900; }
            QLabel#MetricTitle { color: #cbd5e1; font-size: 12px; font-weight: 800; }
            QLabel#CleanerHeroTitle { font-size: 21px; font-weight: 900; color: #f8fafc; }
            QLabel#CleanerHeroSubtitle { font-size: 12px; color: #cbd5e1; }
            #UsbDebugWarning { background: #451a03; border: 1px solid #f59e0b; border-radius: 8px; }
            QLabel#WarningIcon { background: #f59e0b; color: #111827; border-radius: 12px; font-weight: 900; }
            QLabel#WarningText { color: #fde68a; font-size: 12px; font-weight: 800; }
            QPushButton#DeviceAction {
                min-width: 118px;
                max-width: 150px;
                min-height: 32px;
                padding: 7px 14px;
                color: #ffffff;
                font-weight: 800;
            }
            #StatusGood { color: #22c55e; font-weight: 800; }
            #StatusWarn { color: #f59e0b; font-weight: 800; }
            #StatusBad { color: #ef4444; font-weight: 800; }
            #StatusInfo { color: #38bdf8; font-weight: 800; }
            #AppListPanel { background: #151b26; border: 1px solid #2f3a4c; border-radius: 10px; }
            #PanelTitle { color: #f8fafc; font-size: 15px; font-weight: 900; }
            #PanelHint { color: #94a3b8; font-size: 12px; font-weight: 700; }
            QTableWidget#VirusAppTable {
                background: #111827;
                alternate-background-color: #182231;
                color: #f8fafc;
                border: 1px solid #273449;
                border-radius: 8px;
                gridline-color: transparent;
                selection-background-color: #1d4ed8;
                selection-color: #ffffff;
            }
            QTableWidget#VirusAppTable::item {
                padding: 8px;
                border-bottom: 1px solid #223047;
            }
            QTableWidget#VirusAppTable::item:hover {
                background: #223047;
            }
            QHeaderView::section {
                background: #1f2937;
                color: #e5edf8;
                border: none;
                border-right: 1px solid #334155;
                border-bottom: 1px solid #38bdf8;
                padding: 9px 8px;
                font-weight: 900;
            }
        """)

    def setup_ui(self):
        self.setObjectName("VirusCleanerRoot")
        self.apply_theme_style()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        hero = QFrame()
        hero.setObjectName("HeroFrame")
        hero.setMaximumHeight(92)
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(12, 8, 12, 8)
        hero_layout.setSpacing(12)

        logo = QLabel()
        logo_size = 70
        logo.setFixedSize(logo_size, logo_size)
        logo.setStyleSheet("background: transparent; border: none;")
        pix = QPixmap(resource_path("assets/metafold_virus_logo_transparent.png"))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(logo_size, logo_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        hero_layout.addWidget(logo)

        title_box = QVBoxLayout()
        self.hero_title = QLabel("MetaFold Virüs Temizleyici")
        self.hero_title.setObjectName("CleanerHeroTitle")
        self.hero_subtitle = QLabel(f"Android reklam virüslerini güvenli şekilde bulur, resmi paketleri korur. Risk DB: {db_version()}")
        self.hero_subtitle.setObjectName("CleanerHeroSubtitle")
        title_box.addWidget(self.hero_title)
        title_box.addWidget(self.hero_subtitle)
        hero_layout.addLayout(title_box, 1)
        layout.addWidget(hero)

        usb_warning = QFrame()
        usb_warning.setObjectName("UsbDebugWarning")
        usb_warning.setMaximumHeight(42)
        warning_layout = QHBoxLayout(usb_warning)
        warning_layout.setContentsMargins(10, 6, 10, 6)
        warning_icon = QLabel("!")
        warning_icon.setObjectName("WarningIcon")
        warning_icon.setFixedSize(24, 24)
        warning_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.warning_text = QLabel(
            "Telefonu bağlamadan önce USB hata ayıklamayı aktif edin. "
            "Kabloyu takınca telefonda çıkan USB hata ayıklama iznini onaylayın."
        )
        self.warning_text.setObjectName("WarningText")
        self.warning_text.setWordWrap(True)
        warning_layout.addWidget(warning_icon)
        warning_layout.addWidget(self.warning_text, 1)
        layout.addWidget(usb_warning)

        connection = QFrame()
        connection.setObjectName("DevicePanel")
        connection.setMinimumHeight(76)
        connection.setMaximumHeight(76)
        connection_layout = QHBoxLayout(connection)
        connection_layout.setContentsMargins(12, 10, 12, 10)
        connection_layout.setSpacing(8)
        self.adb_input = QLineEdit(self.adb_path)
        self.adb_input.hide()
        self.device_combo = QComboBox()
        self.device_combo.addItem("Cihaz bekleniyor")
        self.device_combo.setMinimumHeight(34)
        self.btn_devices = QPushButton("Cihaz Bul")
        self.btn_scan = QPushButton("Taramayı Başlat")
        self.btn_capture_ad = QPushButton("Otomatik İzle")
        for btn in [self.btn_devices, self.btn_scan, self.btn_capture_ad]:
            btn.setObjectName("DeviceAction")
            btn.setMinimumWidth(118)
            btn.setMinimumHeight(34)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_devices.clicked.connect(self.load_devices)
        self.btn_scan.clicked.connect(self.scan_packages)
        self.btn_capture_ad.clicked.connect(self.toggle_auto_monitor)
        self.device_title = QLabel("Cihaz")
        self.device_title.setObjectName("DeviceTitle")
        self.connected_device_label = QLabel("Bağlı cihaz:")
        connection_layout.addWidget(self.device_title)
        connection_layout.addWidget(self.connected_device_label)
        connection_layout.addWidget(self.device_combo, 10)
        connection_layout.addStretch(1)
        connection_layout.addWidget(self.btn_devices)
        connection_layout.addWidget(self.btn_scan)
        connection_layout.addWidget(self.btn_capture_ad)
        layout.addWidget(connection)

        metrics = QHBoxLayout()
        self.metric_scanned = self.metric_card("Taranan", "0", "#38bdf8", "all")
        self.metric_virus = self.metric_card("Yüksek Risk", "0", "#ef4444", "virus")
        self.metric_suspicious = self.metric_card("Şüpheli", "0", "#f59e0b", "suspicious")
        self.metric_protected = self.metric_card("Korunan", "0", "#22c55e", "protected")
        for card, _label in [self.metric_scanned, self.metric_virus, self.metric_suspicious, self.metric_protected]:
            metrics.addWidget(card)
        layout.addLayout(metrics)

        options = QHBoxLayout()
        self.third_party_only = QCheckBox("Sadece sonradan yüklenen uygulamalar")
        self.third_party_only.setChecked(True)
        self.show_clean_apps = QCheckBox("Temiz uygulamaları da göster")
        self.show_clean_apps.toggled.connect(lambda _checked: self.render_package_table(log_summary=False) if self.scanned_packages else None)
        options.addWidget(self.third_party_only)
        options.addWidget(self.show_clean_apps)
        options.addStretch()
        layout.addLayout(options)

        self.status_title = QLabel("Hazır")
        self.status_title.setObjectName("StatusInfo")
        self.status_title.setStyleSheet("font-size: 14px;")
        layout.addWidget(self.status_title)

        app_list_panel = QFrame()
        app_list_panel.setObjectName("AppListPanel")
        app_list_layout = QVBoxLayout(app_list_panel)
        app_list_layout.setContentsMargins(12, 10, 12, 12)
        app_list_layout.setSpacing(8)

        app_list_header = QHBoxLayout()
        self.app_list_title = QLabel("Uygulama Listesi")
        self.app_list_title.setObjectName("PanelTitle")
        self.btn_select_suspicious = QPushButton("Tehditleri Seç")
        self.btn_remove = QPushButton("Seçilenleri Temizle")
        self.btn_remove.setStyleSheet("background-color: #dc2626;")
        self.btn_select_suspicious.clicked.connect(self.select_suspicious)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.app_count_label = QLabel("Tarama bekleniyor")
        self.app_count_label.setObjectName("PanelHint")
        app_list_header.addWidget(self.app_list_title)
        app_list_header.addWidget(self.btn_select_suspicious)
        app_list_header.addWidget(self.btn_remove)
        app_list_header.addStretch()
        app_list_header.addWidget(self.app_count_label)
        app_list_layout.addLayout(app_list_header)

        self.table = QTableWidget(0, 5)
        self.table.setObjectName("VirusAppTable")
        self.table.setHorizontalHeaderLabels(["Seç", "Risk", "Uygulama", "Paket adı", "Sonuç"])
        self.table.setMinimumHeight(500)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(True)
        self.table.setIconSize(QSize(28, 28))
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.horizontalHeader().setMinimumSectionSize(48)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 52)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        app_list_layout.addWidget(self.table, 1)
        layout.addWidget(app_list_panel, 8)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(48)
        self.log_box.setMaximumHeight(68)
        layout.addWidget(self.log_box)
        self.add_event("Hazır", "USB hata ayıklama açık olan telefonu kabloyla bağlayın.", "info")
        self.update_language()

    def metric_card(self, title, value, color, filter_key):
        frame = ClickableFrame()
        frame.setObjectName("MetricFrame")
        frame.setCursor(Qt.CursorShape.PointingHandCursor)
        frame.setProperty("active", filter_key == self.active_filter)
        frame.clicked.connect(lambda: self.set_filter(filter_key))
        frame.setToolTip(f"{title} uygulamaları göster")
        frame.setMinimumHeight(56)
        frame.setMaximumHeight(64)
        box = QVBoxLayout(frame)
        box.setContentsMargins(12, 6, 12, 6)
        label = QLabel(title)
        label.setObjectName("MetricTitle")
        number = QLabel(value)
        number.setStyleSheet(f"color: {color}; font-size: 22px; font-weight: 900;")
        box.addWidget(label)
        box.addWidget(number)
        self.metric_frames[filter_key] = frame
        self.metric_title_labels[filter_key] = label
        return frame, number

    def set_filter(self, filter_key):
        self.active_filter = filter_key
        self.refresh_filter_styles()
        if self.scanned_packages:
            self.render_package_table(log_summary=False)
        else:
            self.update_metrics()

    def refresh_filter_styles(self):
        for key, frame in self.metric_frames.items():
            frame.setProperty("active", key == self.active_filter)
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def filter_label(self):
        if self.current_language == "EN":
            return {
                "all": "All",
                "virus": "High Risk",
                "suspicious": "Suspicious",
                "protected": "Protected",
            }.get(self.active_filter, "All")
        return {
            "all": "Genel",
            "virus": "Yüksek Risk",
            "suspicious": "Şüpheli",
            "protected": "Korunan",
        }.get(self.active_filter, "Genel")

    def should_show_status(self, status):
        if self.active_filter == "virus":
            return status == "virus"
        if self.active_filter == "suspicious":
            return status in ("suspicious", "review")
        if self.active_filter == "protected":
            return status == "protected"
        return self.show_clean_apps.isChecked() or status in ("virus", "suspicious", "review")

    def update_metrics(self):
        self.metric_scanned[1].setText(str(self.scanned_count))
        self.metric_virus[1].setText(str(self.virus_count))
        self.metric_suspicious[1].setText(str(self.suspicious_count))
        self.metric_protected[1].setText(str(self.protected_count))
        if hasattr(self, "app_count_label") and hasattr(self, "table"):
            self.app_count_label.setText(f"{self.table.rowCount()} gösterilen / {self.scanned_count} taranan • {self.filter_label()}")

    def set_status(self, text, level="info"):
        names = {"clean": "StatusGood", "warn": "StatusWarn", "bad": "StatusBad", "info": "StatusInfo"}
        self.status_title.setObjectName(names.get(level, "StatusInfo"))
        self.status_title.setText(text)
        self.status_title.style().unpolish(self.status_title)
        self.status_title.style().polish(self.status_title)

    def add_event(self, title, text, level="info"):
        colors = {"clean": "#22c55e", "warn": "#f59e0b", "bad": "#ef4444", "info": "#38bdf8"}
        color = colors.get(level, "#38bdf8")
        self.log_box.append(f"<b style='color:{color}'>{title}</b><br><span>{text}</span><br>")

    def set_busy(self, busy):
        self.busy = busy
        for widget in [self.btn_devices, self.btn_scan, self.btn_select_suspicious, self.btn_remove]:
            widget.setEnabled(not busy)

    def adb_args(self, args):
        device = self.device_combo.currentData() or self.device_combo.currentText().strip()
        if device and device != "Cihaz bekleniyor":
            return ["-s", device] + args
        return args

    def run_adb(self, args, callback, timeout=25, show_error=True, fail_callback=None):
        self._adb_shutdown_started = False
        if self.busy:
            self.add_event("İşlem devam ediyor", "Mevcut ADB işlemi tamamlandıktan sonra tekrar deneyin.", "warn")
            return
        self.adb_path = self.adb_input.text().strip() or find_adb()
        self.set_busy(True)
        worker = AdbWorker(self.adb_path, args, timeout)
        self.worker = worker
        self.workers.append(worker)
        worker.failed.connect(lambda message, w=worker: self.on_worker_failed_safe(w, message, show_error, fail_callback))
        worker.finished_ok.connect(lambda output, w=worker: self.on_worker_ok(w, output, callback))
        worker.finished.connect(lambda w=worker: self.cleanup_worker(w))
        worker.start()

    def cleanup_worker(self, worker):
        try:
            if worker in self.workers:
                self.workers.remove(worker)
            if self.worker is worker:
                self.worker = self.workers[-1] if self.workers else None
            worker.deleteLater()
        except Exception:
            pass

    def on_worker_failed_safe(self, worker, message, show_error=True, fail_callback=None):
        self.set_busy(False)
        if fail_callback:
            fail_callback(message)
            return
        if show_error:
            self.set_status("Cihaz ile bağlantı kurulamadı", "bad")
            self.add_event("Hata", message, "bad")
            QMessageBox.warning(self, "Bağlantı Hatası", message)

    def on_worker_failed(self, message):
        self.set_busy(False)
        self.set_status("Cihaz ile bağlantı kurulamadı", "bad")
        self.add_event("Hata", message, "bad")
        QMessageBox.warning(self, "Bağlantı Hatası", message)

    def on_worker_ok(self, worker, output, callback):
        self.set_busy(False)
        try:
            callback(output)
        except Exception as exc:
            self.set_status("Tarama işlenemedi", "bad")
            self.add_event("Tarama hatası", str(exc), "bad")
            QMessageBox.warning(self, "Tarama Hatası", f"Tarama sonucu işlenirken hata oluştu:\n{exc}")

    def kill_adb_server(self):
        adb_path = self.adb_path or find_adb()
        if not adb_path:
            return
        try:
            subprocess.run(
                [adb_path, "kill-server"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                **hidden_subprocess_kwargs(),
            )
        except Exception:
            pass

    def kill_adb_server_async(self):
        try:
            threading.Thread(target=self.kill_adb_server, daemon=True).start()
        except Exception:
            pass

    def shutdown_adb(self, wait_ms=80, async_kill=True):
        if getattr(self, "_adb_shutdown_started", False):
            return
        self._adb_shutdown_started = True
        self.monitoring = False
        try:
            self.monitor_timer.stop()
        except Exception:
            pass
        for worker in list(self.workers):
            try:
                worker.cancel()
                if wait_ms and wait_ms > 0:
                    worker.wait(int(wait_ms))
            except Exception:
                pass
        self.workers = [worker for worker in self.workers if worker.isRunning()]
        self.worker = None
        self.busy = False
        if async_kill:
            self.kill_adb_server_async()
        else:
            self.kill_adb_server()

    def closeEvent(self, event):
        self.shutdown_adb()
        super().closeEvent(event)

    def load_devices(self):
        self.set_status("Cihaz aranıyor...", "info")
        self.add_event("Cihaz aranıyor", "Telefon bağlantısı kontrol ediliyor.", "info")
        self.run_adb(["devices"], self.parse_devices)

    def parse_devices(self, output):
        self.device_combo.clear()
        devices = []
        for line in output.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
        if devices:
            for serial in devices:
                self.device_combo.addItem(self.device_display_name(serial), serial)
            self.set_status("Cihaz bulundu", "clean")
            self.add_event("Cihaz bulundu", f"{len(devices)} cihaz taramaya hazır.", "clean")
        else:
            self.device_combo.addItem("Cihaz bekleniyor")
            self.set_status("Cihaz bulunamadı", "warn")
            self.add_event("Cihaz bulunamadı", "Telefondaki USB iznini onaylayıp tekrar deneyin.", "warn")

    def device_display_name(self, serial):
        def prop(name):
            try:
                result = subprocess.run(
                    [self.adb_path, "-s", serial, "shell", "getprop", name],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                    **hidden_subprocess_kwargs(),
                )
                return (result.stdout or "").strip()
            except Exception:
                return ""
        manufacturer = prop("ro.product.manufacturer").strip()
        model = prop("ro.product.model").strip()
        brand = prop("ro.product.brand").strip()
        maker = manufacturer or brand
        if maker and model and maker.lower() not in model.lower():
            return f"{maker.title()} {model}"
        return model or maker.title() or serial

    def scan_packages(self):
        self.table.setRowCount(0)
        self.scanned_count = self.suspicious_count = self.virus_count = self.protected_count = 0
        self.package_signals = {}
        self.scanned_packages = {}
        self._scan_third_party_only = self.third_party_only.isChecked()
        self.update_metrics()
        self.app_count_label.setText("Tarama sürüyor...")
        self.set_status("Uygulamalar taranıyor...", "info")
        self.add_event("Uygulamalar taranıyor", "?nce uygulama listesi okunuyor; izin sinyalleri ikinci aşamada kontrol edilecek.", "info")
        args = ["shell", "pm", "list", "packages", "-f"]
        if self._scan_third_party_only:
            args.append("-3")
        self.run_adb(
            self.adb_args(args),
            self.parse_packages,
            timeout=45,
            show_error=False,
            fail_callback=lambda message: self.retry_package_scan_user0(message),
        )

    def is_profile_permission_error(self, message):
        text = str(message or "")
        return "SecurityException" in text and "does not have permission to access user" in text

    def retry_package_scan_user0(self, message):
        if not self.is_profile_permission_error(message):
            self.show_scan_error(message)
            return
        self.set_status("Kısıtlı profil atlandı", "warn")
        self.add_event(
            "Profil atlandı",
            "Cihazdaki iş/özel profil ADB ile okunamıyor. Ana kullanıcı uygulamaları taranıyor.",
            "warn",
        )
        args = ["shell", "pm", "list", "packages", "-f"]
        if getattr(self, "_scan_third_party_only", True):
            args.append("-3")
        args.extend(["--user", "0"])
        self.run_adb(
            self.adb_args(args),
            self.parse_packages,
            timeout=45,
            show_error=False,
            fail_callback=lambda retry_message: self.retry_package_scan_cmd_user0(retry_message),
        )

    def retry_package_scan_cmd_user0(self, message):
        args = ["shell", "cmd", "package", "list", "packages", "-f"]
        if getattr(self, "_scan_third_party_only", True):
            args.append("-3")
        args.extend(["--user", "0"])
        self.run_adb(
            self.adb_args(args),
            self.parse_packages,
            timeout=45,
            show_error=False,
            fail_callback=lambda final_message: self.show_scan_error(final_message),
        )

    def show_scan_error(self, message):
        if self.is_profile_permission_error(message):
            text = (
                "Bu cihazda iş profili/özel alan gibi ADB erişimine kapalı bir kullanıcı profili var. "
                "Ana kullanıcı da okunamadı. Telefonda kişisel ana kullanıcı açıkken tekrar deneyin."
            )
        else:
            text = "Uygulama listesi okunamadı. USB hata ayıklama iznini kontrol edip tekrar deneyin."
        self.set_status("Tarama başlatılamadı", "bad")
        self.add_event("Tarama hatası", text, "bad")
        QMessageBox.warning(self, "Tarama Hatası", text)

    def run_signal_scan(self):
        scan_script = (
            "echo __MF_ACCESSIBILITY__; settings get secure enabled_accessibility_services 2>/dev/null || true; "
            "echo __MF_NOTIFICATION__; settings get secure enabled_notification_listeners 2>/dev/null || true; "
            "echo __MF_OVERLAY__; "
            "(cmd appops query-op SYSTEM_ALERT_WINDOW allow 2>/dev/null || "
            "cmd appops query-op android:system_alert_window allow 2>/dev/null || true); "
            "echo __MF_DEVICE_ADMIN__; dumpsys device_policy 2>/dev/null | grep -E 'ComponentInfo|admin=|Active admin' || true; "
            "echo __MF_BOOT__; cmd package query-receivers -a android.intent.action.BOOT_COMPLETED 2>/dev/null || true"
        )
        self.run_adb(
            self.adb_args(["shell", "sh", "-c", scan_script]),
            self.apply_signal_scan,
            timeout=30,
            show_error=False,
            fail_callback=lambda _message: self.add_event("İzin taraması atlandı", "Uygulama listesi okundu; bu cihaz derin izin sinyallerine yanıt vermedi.", "warn"),
        )

    def parse_packages(self, output):
        self.scanned_packages = {}
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("package:"):
                continue
            payload = line[len("package:"):]
            apk_path, package_name = payload.rsplit("=", 1) if "=" in payload else ("", payload)
            if package_name:
                self.scanned_packages[package_name] = apk_path
        if not self.scanned_packages and self.is_profile_permission_error(output):
            self.retry_package_scan_user0(output)
            return
        self.render_package_table()
        if self.scanned_packages:
            self.run_signal_scan()
        else:
            self.set_status("Uygulama listesi okunamadı", "warn")
            self.add_event("Liste boş geldi", "Telefon uygulama listesi döndürmedi. USB iznini kontrol edip tekrar deneyin.", "warn")

    def apply_signal_scan(self, output):
        sections = split_scan_sections(output)
        self.package_signals = build_package_signals(sections)
        if self.package_signals:
            self.add_event(
                "İzin sinyalleri okundu",
                f"{len(self.package_signals)} uygulamada erişilebilirlik, bildirim, üstte gösterme veya açılış alıcısı sinyali bulundu.",
                "info",
            )
            self.render_package_table()
        else:
            self.add_event("İzin sinyali yok", "Derin taramada ek risk sinyali bulunmadı.", "clean")

    def render_package_table(self, log_summary=True):
        self.table.setRowCount(0)
        self.scanned_count = self.suspicious_count = self.virus_count = self.protected_count = 0
        for package_name, apk_path in self.scanned_packages.items():
            self.scanned_count += 1
            risk, reason, status = score_package(package_name, apk_path, self.package_signals.get(package_name))
            app_name = package_label(package_name)
            if status == "protected":
                self.protected_count += 1
            elif status == "review":
                self.suspicious_count += 1
            elif status == "virus":
                self.virus_count += 1
            elif status == "suspicious":
                self.suspicious_count += 1
            if self.should_show_status(status):
                self.add_package_row(package_name, app_name, risk, reason, status, checked=status == "virus")
            self.update_metrics()

        if self.virus_count or self.suspicious_count:
            self.set_status(f"{self.virus_count} yüksek risk, {self.suspicious_count} şüpheli/inceleme uygulaması bulundu", "bad")
        else:
            self.set_status("Tehdit bulunamadı", "clean")
        if log_summary:
            self.add_event("Tarama tamamlandı", f"{self.scanned_count} uygulama tarandı, {self.protected_count} önemli paket korundu.", "info")

    def find_package_row(self, package_name):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 3) or self.table.item(row, 2)
            if item and item.data(Qt.ItemDataRole.UserRole) == package_name:
                return row
        return -1

    def add_package_row(self, package_name, app_name, risk, reason, status, checked=False):
        row = self.find_package_row(package_name)
        if row < 0:
            row = self.table.rowCount()
            self.table.insertRow(row)
        check = QTableWidgetItem("")
        removable = status not in ("protected", "review") and not is_protected_package(package_name)
        if not removable:
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        else:
            check.setFlags(check.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        check.setCheckState(Qt.CheckState.Checked if checked and removable else Qt.CheckState.Unchecked)
        check.setData(Qt.ItemDataRole.UserRole, status)
        status_text = {
            "virus": "Yüksek Risk",
            "suspicious": "?üpheli",
            "review": "İncele",
            "protected": "Korunuyor",
            "clean": "Temiz",
        }.get(status, "Bilgi")
        status_item = QTableWidgetItem(status_text)
        status_item.setIcon(status_icon(status))
        app_item = QTableWidgetItem(app_name)
        app_item.setIcon(app_badge_icon(package_name, app_name))
        app_item.setData(Qt.ItemDataRole.UserRole, package_name)
        package_item = QTableWidgetItem(package_name)
        package_item.setData(Qt.ItemDataRole.UserRole, package_name)
        result_item = QTableWidgetItem(reason)
        result_item.setToolTip(package_name)
        color = {
            "virus": QColor("#ef4444"),
            "suspicious": QColor("#f59e0b"),
            "review": QColor("#f59e0b"),
            "protected": QColor("#22c55e"),
            "clean": QColor("#38bdf8"),
        }.get(status, QColor("#38bdf8"))
        background = {
            "virus": QColor("#2b1218"),
            "suspicious": QColor("#2a2111"),
            "review": QColor("#2a2111"),
            "protected": QColor("#11251b"),
            "clean": QColor("#101f2c"),
        }.get(status, QColor("#101f2c"))
        status_item.setForeground(color)
        result_item.setForeground(color)
        package_item.setForeground(QColor("#94a3b8"))
        for item in [check, status_item, app_item, package_item, result_item]:
            item.setBackground(background)
            item.setToolTip(package_name if item is not result_item else reason)
        self.table.setItem(row, 0, check)
        self.table.setItem(row, 1, status_item)
        self.table.setItem(row, 2, app_item)
        self.table.setItem(row, 3, package_item)
        self.table.setItem(row, 4, result_item)
        self.table.setRowHeight(row, 48)
        self.table.selectRow(row)
        self.update_metrics()

    def toggle_auto_monitor(self):
        if self.monitoring:
            self.monitoring = False
            self.monitor_timer.stop()
            self.btn_capture_ad.setText("Otomatik İzle")
            self.set_status("Otomatik izleme durdu", "info")
            self.add_event("İzleme durdu", "Reklam izleme kapatıldı.", "info")
            return
        self.monitoring = True
        self.last_foreground_package = ""
        self.monitor_error_count = 0
        self.btn_capture_ad.setText("İzlemeyi Durdur")
        self.set_status("Otomatik reklam izleme açık", "info")
        self.add_event("Otomatik izleme başladı", "Reklam çıkarsa ekrandaki uygulama otomatik yakalanacak.", "info")
        self.auto_monitor_tick()
        self.monitor_timer.start()

    def auto_monitor_tick(self):
        if not self.monitoring or self.busy:
            return
        self.capture_foreground_app(auto=True)

    def capture_foreground_app(self, auto=False):
        if not auto:
            self.set_status("Ekrandaki uygulama izleniyor...", "info")
            self.add_event("İzleme başladı", "Reklam ekrandayken aktif uygulama yakalanıyor.", "info")
        command = (
            "dumpsys window | grep -E 'mCurrentFocus|mFocusedApp|topResumedActivity'; "
            "dumpsys activity top | grep ACTIVITY; true"
        )
        self.run_adb(
            self.adb_args(["shell", "sh", "-c", command]),
            lambda out: self.parse_foreground_app(out, auto),
            timeout=8,
            show_error=not auto,
            fail_callback=self.on_monitor_failed if auto else None,
        )

    def on_monitor_failed(self, message):
        self.monitor_error_count += 1
        if self.monitor_error_count == 1:
            self.set_status("Otomatik izleme devam ediyor", "warn")
            self.add_event("İzleme gecikti", "Telefon yanıt vermekte yavaş kaldı; pencere gösterilmeden izleme sürüyor.", "warn")

    def parse_foreground_app(self, output, auto=False):
        package_name = extract_foreground_package(output)
        if not package_name:
            if not auto:
                self.set_status("Aktif uygulama bulunamadı", "warn")
                self.add_event("Yakalanamadı", "Reklam tam ekrandayken tekrar deneyin.", "warn")
            return
        if auto and package_name == self.last_foreground_package:
            return
        self.last_foreground_package = package_name
        app_name = package_label(package_name)
        if is_protected_package(package_name):
            if not auto:
                self.set_status("Görünen uygulama güvenli", "clean")
                self.add_event("Yanlış alarm engellendi", f"{app_name} korunan/önemli uygulama olduğu için tehdit sayılmadı.", "clean")
            return
        risk, reason, status = score_package(package_name)
        status = "virus" if risk >= 70 else "suspicious"
        if self.find_package_row(package_name) >= 0:
            return
        self.add_package_row(package_name, app_name, max(risk, 90), "ekranda reklam olarak yakalandı", status, checked=True)
        if status == "virus":
            self.virus_count += 1
        else:
            self.suspicious_count += 1
        self.update_metrics()
        self.set_status("Reklam uygulaması yakalandı", "bad")
        self.add_event("Reklam yakalandı", f"{app_name} temizleme listesine eklendi.", "bad")

    def select_suspicious(self):
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            app_item = self.table.item(row, 2)
            status = check_item.data(Qt.ItemDataRole.UserRole) if check_item else ""
            package_name = app_item.data(Qt.ItemDataRole.UserRole) if app_item else ""
            can_remove = bool(package_name) and not is_protected_package(package_name) and status in ("virus", "suspicious")
            if check_item:
                check_item.setCheckState(Qt.CheckState.Checked if can_remove else Qt.CheckState.Unchecked)

    def selected_packages(self):
        selected = []
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            app_item = self.table.item(row, 2)
            status = check_item.data(Qt.ItemDataRole.UserRole) if check_item else ""
            if check_item and app_item and check_item.checkState() == Qt.CheckState.Checked and status != "protected":
                package_name = app_item.data(Qt.ItemDataRole.UserRole)
                if not is_protected_package(package_name):
                    selected.append((package_name, app_item.text()))
        return selected

    def remove_selected(self):
        packages = self.selected_packages()
        if not packages:
            QMessageBox.information(self, "Temizleme", "Temizlenecek virüs veya şüpheli uygulama seçilmedi.")
            return
        names = "\n".join([name for _pkg, name in packages[:8]])
        answer = QMessageBox.question(
            self,
            "Temizleme Onayı",
            f"{len(packages)} uygulama temizlenecek:\n\n{names}\n\nDevam edilsin mi",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._remove_queue = packages[:]
        self._remove_next()

    def _remove_next(self):
        if not self._remove_queue:
            self.set_status("Temizleme tamamlandı", "clean")
            self.add_event("Temizleme tamamlandı", "Seçilen tehditler telefondan kaldırıldı.", "clean")
            self.scan_packages()
            return
        package_name, app_name = self._remove_queue.pop(0)
        if is_protected_package(package_name):
            self.add_event("Koruma", f"{app_name} silinmedi.", "clean")
            self._remove_next()
            return
        self._current_remove = (package_name, app_name)
        self.set_status(f"{app_name} temizleniyor...", "warn")
        self.run_adb(self.adb_args(["shell", "pm", "uninstall", "--user", "0", package_name]), self._remove_done, timeout=35)

    def _remove_done(self, output):
        package_name, app_name = getattr(self, "_current_remove", ("", ""))
        if "Success" in output:
            self.add_event("Temizlendi", f"{app_name} kaldırıldı.", "clean")
            self._remove_next()
            return
        self.add_event("Temizleme deneniyor", f"{app_name} için ikinci kaldırma yöntemi deneniyor.", "warn")
        self.run_adb(self.adb_args(["uninstall", package_name]), lambda _out: self._remove_next(), timeout=35)
