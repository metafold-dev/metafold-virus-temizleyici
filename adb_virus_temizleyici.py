# -*- coding: utf-8 -*-
import datetime
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import webbrowser
import urllib.request
from urllib.parse import quote

from PyQt6.QtCore import QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from config import (
    check_license_status,
    describe_connection_error,
    get_device_id,
    get_theme_stylesheet,
    resource_path,
    safe_dict_parse,
)
from database.threads import auth, db
from gui.adb_cleaner import AdbCleanerWidget


APP_NAME = "MetaFold Virüs Temizleyici"
APP_VERSION = "1.0.0"
APP_USER_MODEL_ID = "MetaFold.VirusCleaner.Standalone"
APP_LOGO_PNG = "assets/metafold_virus_logo_transparent.png"
APP_LOGO_ICO = "assets/metafold_virus_logo_transparent.ico"
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/metafold-dev/metafold-virus-temizleyici/main/update/latest.json"
VIRUS_LICENSE_NODE = "virus_licenses"
VIRUS_DEVICE_NODE = "virus_devices"
VIRUS_DEVICE_REQUEST_NODE = "virus_device_requests"
SUPPORT_WHATSAPP = "905357309054"
BUY_MESSAGE = "Merhaba, MetaFold Virüs Temizleyici aboneliği satın almak istiyorum."


def now_text():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def license_limit(license_data, default=1):
    return 1


def license_title(license_data):
    package_name = str(license_data.get("paket_adi") or license_data.get("package_name") or "").strip()
    if package_name:
        return package_name
    return "Virüs Temizleyici"


def read_standalone_license(uid, token):
    """Sadece ayrı Virüs Temizleyici aboneliğini okur."""
    virus_license = {}
    try:
        virus_license = safe_dict_parse(db.child(VIRUS_LICENSE_NODE).child(uid).get(token).val() or {})
    except Exception:
        virus_license = {}

    if isinstance(virus_license, dict) and virus_license:
        if str(virus_license.get("status", "") or "").strip().lower() == "pending":
            return {}
        data = dict(virus_license)
        data["_license_source"] = "virus"
        return data
    return {}


def open_buy_whatsapp():
    webbrowser.open(f"https://wa.me/{SUPPORT_WHATSAPP}?text={quote(BUY_MESSAGE)}")


def missing_license_text(uid=""):
    extra = f"\n\nKullanıcı UID: {uid}" if uid else ""
    return (
        "Bu hesapta aktif Virüs Temizleyici aboneliği bulunamadı.\n\n"
        "ERP lisansı bu üründe geçerli değildir. Satın Al butonuyla abonelik talebi gönderebilirsiniz."
        f"{extra}"
    )


def parse_version(value):
    parts = []
    for piece in str(value or "0").replace("v", "").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(remote_version, current_version=APP_VERSION):
    return parse_version(remote_version) > parse_version(current_version)


class UpdateWorker(QThread):
    no_update = pyqtSignal()
    update_ready = pyqtSignal(str, str)
    failed = pyqtSignal(str)

    def run(self):
        try:
            request = urllib.request.Request(
                UPDATE_MANIFEST_URL,
                headers={
                    "User-Agent": f"MetaFoldVirusCleaner/{APP_VERSION}",
                    "Cache-Control": "no-cache",
                },
            )
            with urllib.request.urlopen(request, timeout=8) as response:
                manifest = json.loads(response.read().decode("utf-8"))

            remote_version = str(manifest.get("version", "")).strip()
            download_url = str(manifest.get("url", "")).strip()
            expected_sha256 = str(manifest.get("sha256", "") or "").strip().lower()

            if not remote_version or not download_url or not is_newer_version(remote_version):
                self.no_update.emit()
                return

            target_dir = os.path.join(tempfile.gettempdir(), "MetaFoldVirusCleanerUpdate")
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, f"MetaFoldVirusCleaner_{remote_version}.exe")

            with urllib.request.urlopen(download_url, timeout=30) as response, open(target_path, "wb") as output:
                shutil.copyfileobj(response, output)

            if expected_sha256:
                digest = hashlib.sha256()
                with open(target_path, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest().lower() != expected_sha256:
                    self.failed.emit("Güncelleme dosyası doğrulanamadı.")
                    return

            self.update_ready.emit(remote_version, target_path)
        except Exception as err:
            self.failed.emit(str(err))


class DeviceLimitError(Exception):
    def __init__(self, limit):
        super().__init__(f"Cihaz limiti dolu: {limit}")
        self.limit = limit


def build_virus_device_payload(email):
    device_id = get_device_id()
    return {
        "id": device_id,
        "device_id": device_id,
        "email": email,
        "platform": "windows",
        "last_seen": now_iso(),
    }


def report_virus_device(uid, token, email):
    device_path = db.child(VIRUS_DEVICE_REQUEST_NODE).child(uid)
    raw_slots = safe_dict_parse(device_path.get(token).val() or {})
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    payload = build_virus_device_payload(email)
    device_id = payload["device_id"]

    for slot_id, slot_data in slots.items():
        if isinstance(slot_data, dict) and str(slot_data.get("device_id", "") or slot_data.get("id", "")) == device_id:
            device_path.child(slot_id).update(payload, token)
            return slot_id
        if isinstance(slot_data, str) and slot_data == device_id:
            device_path.child(slot_id).set(payload, token)
            return slot_id

    for index in range(1, 51):
        slot_id = f"slot_{index}"
        if slot_id not in slots:
            payload["registered_at"] = now_iso()
            device_path.child(slot_id).set(payload, token)
            return slot_id

    return ""


def ensure_pending_virus_license(uid, token, email):
    profile_path = db.child("users").child(uid).child("profil")
    profile = safe_dict_parse(profile_path.get(token).val() or {})
    if not isinstance(profile, dict):
        profile = {}
    profile["eposta"] = email
    profile["firma_adi"] = profile.get("firma_adi") or "Virus Temizleyici Basvurusu"
    profile_path.set(profile, token)


def register_virus_device(uid, token, email, license_data):
    limit = license_limit(license_data, default=1)
    device_path = db.child(VIRUS_DEVICE_NODE).child(uid)
    raw_slots = safe_dict_parse(device_path.get(token).val() or {})
    slots = raw_slots if isinstance(raw_slots, dict) else {}
    payload = build_virus_device_payload(email)
    device_id = payload["device_id"]

    for slot_id, slot_data in slots.items():
        if isinstance(slot_data, dict) and str(slot_data.get("device_id", "") or slot_data.get("id", "")) == device_id:
            return slot_id
        if isinstance(slot_data, str) and slot_data == device_id:
            return slot_id

    active_slots = [key for key, value in slots.items() if value]
    if len(active_slots) >= limit:
        raise DeviceLimitError(limit)

    for index in range(1, max(limit, 1) + 1):
        slot_id = f"slot_{index}"
        if slot_id not in slots:
            payload["registered_at"] = now_iso()
            device_path.child(slot_id).set(payload, token)
            return slot_id

    raise DeviceLimitError(limit)


class LoginWorker(QThread):
    success = pyqtSignal(dict)
    device_limit = pyqtSignal(int)
    failed = pyqtSignal(str, str)

    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password

    def run(self):
        try:
            user = auth.sign_in_with_email_and_password(self.email, self.password)
            uid = user["localId"]
            token = user["idToken"]
            try:
                report_virus_device(uid, token, self.email)
            except Exception:
                pass
            license_data = read_standalone_license(uid, token)
            if not license_data:
                try:
                    ensure_pending_virus_license(uid, token, self.email)
                except Exception:
                    pass
                self.failed.emit("Lisans Bulunamadı", missing_license_text())
                return

            license_ok, license_reason, expiry_text, remaining = check_license_status(license_data, db, uid, token)
            if not license_ok:
                self.failed.emit("Lisans Kontrolü", license_reason)
                return

            try:
                register_virus_device(uid, token, self.email, license_data)
            except DeviceLimitError as err:
                self.device_limit.emit(err.limit)
                return
            except Exception:
                pass

            user["_virus_license"] = license_data
            user["_virus_expiry"] = expiry_text
            user["_virus_remaining"] = remaining
            user["_email"] = self.email
            self.success.emit(user)
        except Exception as err:
            text = str(err)
            if "INVALID" in text or "NOT_FOUND" in text or "EMAIL_NOT_FOUND" in text:
                self.failed.emit("Giriş Başarısız", "E-posta veya şifre hatalı.")
            else:
                self.failed.emit("Bağlantı Hatası", describe_connection_error(err))


class RegisterWorker(QThread):
    success = pyqtSignal(dict)
    device_limit = pyqtSignal(int)
    failed = pyqtSignal(str, str)

    def __init__(self, email, password):
        super().__init__()
        self.email = email
        self.password = password

    def run(self):
        try:
            user = auth.create_user_with_email_and_password(self.email, self.password)
            uid = user["localId"]
            token = user["idToken"]
            try:
                report_virus_device(uid, token, self.email)
            except Exception:
                pass
            license_data = read_standalone_license(uid, token)
            if not license_data:
                try:
                    ensure_pending_virus_license(uid, token, self.email)
                except Exception:
                    pass
                self.failed.emit("Kayıt Oluşturuldu", missing_license_text(uid))
                return

            license_ok, license_reason, expiry_text, remaining = check_license_status(license_data, db, uid, token)
            if not license_ok:
                self.failed.emit("Lisans Kontrolü", license_reason)
                return

            try:
                register_virus_device(uid, token, self.email, license_data)
            except DeviceLimitError as err:
                self.device_limit.emit(err.limit)
                return
            except Exception:
                pass

            user["_virus_license"] = license_data
            user["_virus_expiry"] = expiry_text
            user["_virus_remaining"] = remaining
            user["_email"] = self.email
            self.success.emit(user)
        except Exception as err:
            text = str(err)
            if "EMAIL_EXISTS" in text:
                self.failed.emit("Kayıt Yapılamadı", "Bu e-posta ile daha önce hesap oluşturulmuş. Giriş yapmayı deneyin.")
            elif "WEAK_PASSWORD" in text:
                self.failed.emit("Kayıt Yapılamadı", "Şifre en az 6 karakter olmalı.")
            elif "INVALID_EMAIL" in text:
                self.failed.emit("Kayıt Yapılamadı", "E-posta adresi geçerli görünmüyor.")
            else:
                self.failed.emit("Bağlantı Hatası", describe_connection_error(err))


class VirusLoginPage(QWidget):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.settings = QSettings("MetaFold", "VirusCleaner")
        self.register_mode = False
        self.build_ui()

    def build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(38, 30, 38, 38)
        outer.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("LoginShell")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        brand = QFrame()
        brand.setObjectName("BrandPanel")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(42, 44, 42, 42)
        brand_layout.setSpacing(18)

        logo = QLabel()
        logo.setObjectName("HeroLogo")
        logo.setAlignment(Qt.AlignmentFlag.AlignLeft)
        pix = QPixmap(resource_path(APP_LOGO_PNG))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(132, 132, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        self.product = QLabel("MetaFold\nVirüs Temizleyici")
        self.product.setObjectName("HeroTitle")
        self.product.setWordWrap(True)
        self.product_text = QLabel(
            "Android reklam virüslerini, şüpheli paketleri ve riskli izinleri teknik servis akışına uygun şekilde analiz eder."
        )
        self.product_text.setObjectName("HeroText")
        self.product_text.setWordWrap(True)

        self.bullets = QLabel(
            "• ADB tabanlı hızlı tarama\n"
            "• Riskli, şüpheli ve korunan uygulama ayrımı\n"
            "• Sistem paketlerini koruyan güvenli temizlik\n"
            "• Tek bilgisayara kilitlenen ayrı abonelik"
        )
        self.bullets.setObjectName("HeroBullets")

        brand_layout.addWidget(logo)
        brand_layout.addWidget(self.product)
        brand_layout.addWidget(self.product_text)
        brand_layout.addSpacing(8)
        brand_layout.addWidget(self.bullets)
        brand_layout.addStretch()

        form = QFrame()
        form.setObjectName("FormPanel")
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(46, 54, 46, 46)
        form_layout.setSpacing(14)

        self.title_lbl = QLabel(APP_NAME)
        self.title_lbl.setObjectName("LoginTitle")
        self.subtitle_lbl = QLabel("Ayrı Virüs Temizleyici aboneliğinizle giriş yapın.")
        self.subtitle_lbl.setObjectName("LoginSubtitle")
        self.subtitle_lbl.setWordWrap(True)
        form_layout.addWidget(self.title_lbl)
        form_layout.addWidget(self.subtitle_lbl)
        form_layout.addSpacing(14)

        self.email_in = QLineEdit()
        self.email_in.setPlaceholderText("E-posta")
        self.email_in.setText(str(self.settings.value("email", "") or ""))

        self.password_in = QLineEdit()
        self.password_in.setPlaceholderText("Şifre")
        self.password_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_in.setText(str(self.settings.value("password", "") or ""))
        self.password_in.returnPressed.connect(self.primary_action)

        self.password_again_in = QLineEdit()
        self.password_again_in.setPlaceholderText("Şifre tekrar")
        self.password_again_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_again_in.returnPressed.connect(self.primary_action)
        self.password_again_in.hide()

        self.remember_cb = QCheckBox("Beni hatırla")
        self.remember_cb.setChecked(str(self.settings.value("remember", "true")).lower() == "true")
        self.auto_login_cb = QCheckBox("Otomatik giriş")
        self.auto_login_cb.setChecked(str(self.settings.value("auto_login", "false")).lower() == "true")
        self.auto_login_cb.stateChanged.connect(self.on_auto_login_changed)

        self.status_lbl = QLabel("")
        self.status_lbl.setObjectName("StatusLabel")
        self.status_lbl.setWordWrap(True)

        self.login_btn = QPushButton("Giriş Yap")
        self.login_btn.setObjectName("PrimaryLoginBtn")
        self.login_btn.clicked.connect(self.primary_action)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.buy_btn = QPushButton("Satın Al")
        self.buy_btn.setObjectName("BuyBtn")
        self.buy_btn.clicked.connect(open_buy_whatsapp)

        self.register_btn = QPushButton("Kayıt Ol")
        self.register_btn.setObjectName("GhostBtn")
        self.register_btn.clicked.connect(self.toggle_register_mode)

        self.forgot_btn = QPushButton("Şifremi Unuttum")
        self.forgot_btn.setObjectName("GhostBtn")
        self.forgot_btn.clicked.connect(self.reset_password)
        action_row.addWidget(self.buy_btn)
        action_row.addWidget(self.register_btn)

        self.note = QLabel("ERP hesabı bu üründe geçerli değildir. Bu araç sadece Virüs Temizleyici aboneliğiyle açılır.")
        self.note.setObjectName("HelpText")
        self.note.setWordWrap(True)

        form_layout.addWidget(self.email_in)
        form_layout.addWidget(self.password_in)
        form_layout.addWidget(self.password_again_in)
        remember_row = QHBoxLayout()
        remember_row.setSpacing(14)
        remember_row.addWidget(self.remember_cb)
        remember_row.addWidget(self.auto_login_cb)
        remember_row.addStretch()
        form_layout.addLayout(remember_row)
        form_layout.addWidget(self.status_lbl)
        form_layout.addWidget(self.login_btn)
        form_layout.addLayout(action_row)
        form_layout.addWidget(self.forgot_btn)
        form_layout.addStretch()
        form_layout.addWidget(self.note)

        shell_layout.addWidget(brand, 5)
        shell_layout.addWidget(form, 4)
        outer.addWidget(shell, 1)
        QTimer.singleShot(350, self.try_auto_login)

    def set_busy(self, busy):
        self.login_btn.setDisabled(busy)
        self.register_btn.setDisabled(busy)
        self.forgot_btn.setDisabled(busy)
        self.email_in.setDisabled(busy)
        self.password_in.setDisabled(busy)
        self.password_again_in.setDisabled(busy)
        if self.current_language() == "EN":
            busy_text = "Creating account..." if self.register_mode else "Checking license..."
        else:
            busy_text = "Hesap oluşturuluyor..." if self.register_mode else "Lisans kontrol ediliyor..."
        self.status_lbl.setText(busy_text if busy else "")

    def current_language(self):
        return self.manager.current_language() if hasattr(self.manager, "current_language") else "TR"

    def tx(self, tr_text, en_text):
        return en_text if self.current_language() == "EN" else tr_text

    def update_language(self, language=None):
        lang = language or self.current_language()
        en = lang == "EN"
        self.product.setText("MetaFold\nVirus Cleaner" if en else "MetaFold\nVirüs Temizleyici")
        self.product_text.setText(
            "Analyzes Android adware, suspicious packages and risky permissions for service workflows."
            if en else
            "Android reklam virüslerini, şüpheli paketleri ve riskli izinleri teknik servis akışına uygun şekilde analiz eder."
        )
        self.bullets.setText(
            "• Fast ADB based scanning\n"
            "• Risky, suspicious and protected app separation\n"
            "• Safe cleanup that protects system packages\n"
            "• Separate subscription locked to one computer"
            if en else
            "• ADB tabanlı hızlı tarama\n"
            "• Riskli, şüpheli ve korunan uygulama ayrımı\n"
            "• Sistem paketlerini koruyan güvenli temizlik\n"
            "• Tek bilgisayara kilitlenen ayrı abonelik"
        )
        self.email_in.setPlaceholderText("Email" if en else "E-posta")
        self.password_in.setPlaceholderText("Password" if en else "Şifre")
        self.password_again_in.setPlaceholderText("Repeat password" if en else "Şifre tekrar")
        self.remember_cb.setText("Remember me" if en else "Beni hatırla")
        self.auto_login_cb.setText("Auto login" if en else "Otomatik giriş")
        self.buy_btn.setText("Buy" if en else "Satın Al")
        self.forgot_btn.setText("Forgot Password" if en else "Şifremi Unuttum")
        self.note.setText(
            "ERP accounts are not valid for this product. This tool opens only with a Virus Cleaner subscription."
            if en else
            "ERP hesabı bu üründe geçerli değildir. Bu araç sadece Virüs Temizleyici aboneliğiyle açılır."
        )
        self.toggle_register_mode_texts()

    def toggle_register_mode_texts(self):
        if self.register_mode:
            self.title_lbl.setText(self.tx("Hesap Oluştur", "Create Account"))
            self.subtitle_lbl.setText(self.tx(
                "Önce hesabınızı oluşturun. Aktif Virüs Temizleyici lisansı varsa otomatik giriş yapılır.",
                "Create your account first. If an active Virus Cleaner license exists, login starts automatically."
            ))
            self.login_btn.setText(self.tx("Hesap Oluştur", "Create Account"))
            self.register_btn.setText(self.tx("Girişe Dön", "Back to Login"))
        else:
            self.title_lbl.setText(APP_NAME if self.current_language() != "EN" else "MetaFold Virus Cleaner")
            self.subtitle_lbl.setText(self.tx(
                "Ayrı Virüs Temizleyici aboneliğinizle giriş yapın.",
                "Sign in with your separate Virus Cleaner subscription."
            ))
            self.login_btn.setText(self.tx("Giriş Yap", "Sign In"))
            self.register_btn.setText(self.tx("Kayıt Ol", "Register"))

    def toggle_register_mode(self):
        self.register_mode = not self.register_mode
        if self.register_mode:
            self.toggle_register_mode_texts()
            self.password_again_in.show()
            self.forgot_btn.hide()
            self.status_lbl.setText("")
        else:
            self.toggle_register_mode_texts()
            self.password_again_in.hide()
            self.forgot_btn.show()
            self.status_lbl.setText("")

    def primary_action(self):
        if self.register_mode:
            self.register()
        else:
            self.login()

    def on_auto_login_changed(self):
        if self.auto_login_cb.isChecked():
            self.remember_cb.setChecked(True)

    def remember_credentials(self, email, password):
        if self.remember_cb.isChecked():
            self.settings.setValue("email", email)
            self.settings.setValue("password", password)
            self.settings.setValue("remember", "true")
            self.settings.setValue("auto_login", "true" if self.auto_login_cb.isChecked() else "false")
        else:
            self.settings.setValue("email", "")
            self.settings.setValue("password", "")
            self.settings.setValue("remember", "false")
            self.settings.setValue("auto_login", "false")
            self.auto_login_cb.setChecked(False)

    def try_auto_login(self):
        if self.register_mode:
            return
        if str(self.settings.value("auto_login", "false")).lower() != "true":
            return
        email = self.email_in.text().strip()
        password = self.password_in.text().strip()
        if email and password:
            self.login()

    def login(self):
        email = self.email_in.text().strip()
        password = self.password_in.text().strip()
        if not email or not password:
            self.status_lbl.setText("E-posta ve şifre girin.")
            return
        self.remember_credentials(email, password)
        self.manager.start_login(email, password)

    def register(self):
        email = self.email_in.text().strip()
        password = self.password_in.text().strip()
        password_again = self.password_again_in.text().strip()
        if not email or not password or not password_again:
            self.status_lbl.setText("E-posta, şifre ve şifre tekrar alanlarını doldurun.")
            return
        if password != password_again:
            self.status_lbl.setText("Şifreler eşleşmiyor.")
            return
        if len(password) < 6:
            self.status_lbl.setText("Şifre en az 6 karakter olmalı.")
            return
        self.remember_credentials(email, password)
        self.manager.start_register(email, password)

    def reset_password(self):
        email = self.email_in.text().strip()
        if not email:
            QMessageBox.warning(self, "Şifre Sıfırlama", "Önce e-posta adresinizi yazın.")
            return
        try:
            auth.send_password_reset_email(email)
            QMessageBox.information(self, "Şifre Sıfırlama", "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi.")
        except Exception as err:
            QMessageBox.warning(self, "Şifre Sıfırlama", describe_connection_error(err))


class VirusCleanerShell(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("MetaFold", "VirusCleaner")
        self.worker = None
        self.update_worker = None
        self.login_page = None
        self.current_user = None
        self._drag_offset = None
        self.info_back_buttons = []
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(resource_path(APP_LOGO_PNG)))
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.resize(1160, 760)
        self.build_ui()
        self.center_window()
        QTimer.singleShot(1200, self.check_for_updates)

    def build_ui(self):
        root = QFrame()
        root.setObjectName("AppRoot")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(1, 1, 1, 1)
        root_layout.setSpacing(0)

        title_bar = QFrame()
        title_bar.setObjectName("WindowTitleBar")
        title_bar.setFixedHeight(46)
        title_bar.mousePressEvent = self.title_mouse_press
        title_bar.mouseMoveEvent = self.title_mouse_move
        title_bar.mouseReleaseEvent = self.title_mouse_release
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 10, 0)
        title_layout.setSpacing(10)

        title_logo = QLabel()
        title_logo.setFixedSize(26, 26)
        pix = QPixmap(resource_path(APP_LOGO_PNG))
        if not pix.isNull():
            title_logo.setPixmap(pix.scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.title_text = QLabel(APP_NAME)
        self.title_text.setObjectName("WindowTitle")
        self.account_text = QLabel("")
        self.account_text.setObjectName("WindowAccount")
        self.account_text.setVisible(False)

        self.title_logout_btn = QPushButton("Çıkış")
        self.title_logout_btn.setObjectName("TitleLogoutBtn")
        self.title_logout_btn.setFixedSize(74, 30)
        self.title_logout_btn.clicked.connect(self.logout)
        self.title_logout_btn.setVisible(False)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("TitleThemeCombo")
        self.theme_combo.setFixedSize(142, 32)
        self.theme_combo.addItems(["🌙 Karanlık", "☀ Aydınlık", "🌊 Okyanus", "🌿 Zümrüt", "◼ Grafit"])
        saved_theme = str(self.settings.value("theme_choice", self.settings.value("theme", "Karanlık")) or "Karanlık")
        if saved_theme in ["Dark", "Dark Flat", "Dark Windows", "Karanlık"]:
            saved_theme = "🌙 Karanlık"
        elif saved_theme in ["Light", "Blue", "Aydınlık"]:
            saved_theme = "☀ Aydınlık"
        elif "Okyanus" in saved_theme or "Ocean" in saved_theme:
            saved_theme = "🌊 Okyanus"
        elif "Zümrüt" in saved_theme or "Emerald" in saved_theme:
            saved_theme = "🌿 Zümrüt"
        elif "Grafit" in saved_theme or "Graphite" in saved_theme:
            saved_theme = "◼ Grafit"
        if saved_theme not in [self.theme_combo.itemText(i) for i in range(self.theme_combo.count())]:
            saved_theme = "🌙 Karanlık"
        self.theme_combo.setCurrentText(saved_theme)
        self.theme_combo.currentTextChanged.connect(self.change_theme)

        self.language_combo = QComboBox()
        self.language_combo.setObjectName("TitleLangCombo")
        self.language_combo.setFixedSize(84, 32)
        self.language_combo.addItems(["TR", "EN"])
        self.language_combo.setCurrentText(str(self.settings.value("language", "TR") or "TR"))
        self.language_combo.currentTextChanged.connect(self.change_language)

        self.license_btn = QPushButton("Lisans")
        self.license_btn.setObjectName("TitleToolBtn")
        self.license_btn.setFixedSize(74, 30)
        self.license_btn.clicked.connect(self.show_license_info)

        self.about_btn = QPushButton("Hakkında")
        self.about_btn.setObjectName("TitleToolBtn")
        self.about_btn.setFixedSize(86, 30)
        self.about_btn.clicked.connect(self.show_about)

        min_btn = QPushButton("−")
        min_btn.setObjectName("WindowButton")
        min_btn.setFixedSize(34, 30)
        min_btn.clicked.connect(self.showMinimized)
        self.max_btn = QPushButton("□")
        self.max_btn.setObjectName("WindowButton")
        self.max_btn.setFixedSize(34, 30)
        self.max_btn.clicked.connect(self.toggle_max_restore)
        close_btn = QPushButton("×")
        close_btn.setObjectName("CloseButton")
        close_btn.setFixedSize(34, 30)
        close_btn.clicked.connect(self.close)

        title_layout.addWidget(title_logo)
        title_layout.addWidget(self.title_text)
        title_layout.addWidget(self.account_text)
        title_layout.addStretch()
        title_layout.addWidget(self.theme_combo)
        title_layout.addWidget(self.language_combo)
        title_layout.addWidget(self.license_btn)
        title_layout.addWidget(self.about_btn)
        title_layout.addWidget(self.title_logout_btn)
        title_layout.addWidget(min_btn)
        title_layout.addWidget(self.max_btn)
        title_layout.addWidget(close_btn)

        self.stack = QStackedWidget()
        self.login_page = VirusLoginPage(self)
        self.license_page = self.create_license_page()
        self.about_page = self.create_about_page()
        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.license_page)
        self.stack.addWidget(self.about_page)
        root_layout.addWidget(title_bar)
        root_layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.apply_theme()
        self.update_language()

    def title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def title_mouse_move(self, event):
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def title_mouse_release(self, event):
        self._drag_offset = None
        event.accept()

    def center_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        area = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(area.center())
        self.move(frame.topLeft())

    def check_for_updates(self):
        if self.update_worker and self.update_worker.isRunning():
            return
        self.update_worker = UpdateWorker()
        self.update_worker.update_ready.connect(self.install_update)
        self.update_worker.failed.connect(lambda _message: None)
        self.update_worker.no_update.connect(lambda: None)
        self.update_worker.finished.connect(lambda: setattr(self, "update_worker", None))
        self.update_worker.start()

    def install_update(self, version, downloaded_exe):
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self,
                "Güncelleme Hazır",
                f"Yeni sürüm indirildi: {version}\n\nGeliştirme modunda otomatik değiştirme yapılmadı."
            )
            return

        current_exe = os.path.abspath(sys.executable)
        bat_path = os.path.join(tempfile.gettempdir(), "metafold_virus_cleaner_update.bat")
        script = f"""@echo off
setlocal
timeout /t 2 /nobreak >nul
copy /Y "{downloaded_exe}" "{current_exe}" >nul
start "" "{current_exe}"
del "{downloaded_exe}" >nul 2>nul
del "%~f0" >nul 2>nul
"""
        with open(bat_path, "w", encoding="utf-8") as handle:
            handle.write(script)

        QMessageBox.information(
            self,
            "Güncelleme",
            f"Yeni sürüm bulundu: {version}\nProgram şimdi güncellenip yeniden açılacak."
        )
        subprocess.Popen(
            ["cmd", "/c", bat_path],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        QApplication.quit()

    def normalized_theme(self):
        choice = str(self.settings.value("theme_choice", self.settings.value("theme", "Dark Flat")) or "Dark Flat")
        if hasattr(self, "theme_combo"):
            choice = self.theme_combo.currentText()
        if "Aydınlık" in choice or "Light" in choice:
            return "Light"
        if "Okyanus" in choice or "Ocean" in choice:
            return "Okyanus"
        if "Zümrüt" in choice or "Emerald" in choice:
            return "Zümrüt"
        if "Grafit" in choice or "Graphite" in choice:
            return "Grafit"
        return "Dark"

    def apply_theme(self):
        theme = self.normalized_theme()
        extra = STANDALONE_STYLE
        if theme == "Light":
            extra += STANDALONE_LIGHT_STYLE
        elif theme == "Okyanus":
            extra += STANDALONE_OCEAN_STYLE
        elif theme == "Zümrüt":
            extra += STANDALONE_EMERALD_STYLE
        elif theme == "Grafit":
            extra += STANDALONE_GRAPHITE_STYLE
        self.setStyleSheet(get_theme_stylesheet(theme) + extra)
        if hasattr(self, "cleaner") and self.cleaner is not None and hasattr(self.cleaner, "set_theme"):
            self.cleaner.set_theme(theme)

    def change_theme(self, choice):
        theme = self.normalized_theme()
        self.settings.setValue("theme_choice", choice)
        self.settings.setValue("theme", theme)
        self.apply_theme()

    def current_language(self):
        if hasattr(self, "language_combo"):
            return self.language_combo.currentText()
        return str(self.settings.value("language", "TR") or "TR")

    def tr(self, tr_text, en_text):
        return en_text if self.current_language() == "EN" else tr_text

    def change_language(self, language):
        self.settings.setValue("language", language)
        self.update_language()

    def update_language(self):
        self.title_text.setText(APP_NAME if self.current_language() != "EN" else "MetaFold Virus Cleaner")
        self.license_btn.setText(self.tr("Lisans", "License"))
        self.about_btn.setText(self.tr("Hakkında", "About"))
        self.title_logout_btn.setText(self.tr("Çıkış", "Logout"))
        for btn in getattr(self, "info_back_buttons", []):
            btn.setText(self.tr("Panele Dön", "Back to Panel"))
        if hasattr(self, "login_page") and self.login_page:
            self.login_page.update_language(self.current_language())
        if hasattr(self, "cleaner") and self.cleaner is not None and hasattr(self.cleaner, "set_language"):
            self.cleaner.set_language(self.current_language())

    def toggle_theme(self):
        if not hasattr(self, "theme_combo"):
            return
        next_index = (self.theme_combo.currentIndex() + 1) % self.theme_combo.count()
        self.theme_combo.setCurrentIndex(next_index)

    def toggle_max_restore(self):
        if self.isMaximized():
            self.showNormal()
            self.max_btn.setText("□")
            return
        self.showMaximized()
        self.max_btn.setText("❐")

    def create_info_page(self, title, subtitle):
        page = QWidget()
        page.setObjectName("InfoPage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 26, 28, 28)
        layout.setSpacing(18)

        header = QFrame()
        header.setObjectName("InfoHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(14)

        logo = QLabel()
        logo.setFixedSize(58, 58)
        pix = QPixmap(resource_path(APP_LOGO_PNG))
        if not pix.isNull():
            logo.setPixmap(pix.scaled(58, 58, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        text_box = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setObjectName("InfoTitle")
        subtitle_lbl = QLabel(subtitle)
        subtitle_lbl.setObjectName("InfoSubtitle")
        subtitle_lbl.setWordWrap(True)
        text_box.addWidget(title_lbl)
        text_box.addWidget(subtitle_lbl)

        back_btn = QPushButton("Panele Dön")
        back_btn.setObjectName("InfoBackBtn")
        back_btn.setFixedSize(112, 36)
        back_btn.clicked.connect(self.go_home)
        self.info_back_buttons.append(back_btn)

        header_layout.addWidget(logo)
        header_layout.addLayout(text_box, 1)
        header_layout.addWidget(back_btn)
        layout.addWidget(header)

        card = QFrame()
        card.setObjectName("InfoCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        card_layout.setSpacing(12)
        layout.addWidget(card, 1)
        page.card_layout = card_layout
        return page

    def create_license_page(self):
        page = self.create_info_page("Lisans", "Abonelik durumu ve kalan kullanım süresi.")
        self.license_rows = {}
        for label in ["Paket", "Bitiş", "Kalan Süre", "Hesap", "Cihaz Limiti"]:
            row = QFrame()
            row.setObjectName("InfoRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            key = QLabel(label)
            key.setObjectName("InfoKey")
            value = QLabel("-")
            value.setObjectName("InfoValue")
            value.setWordWrap(True)
            row_layout.addWidget(key)
            row_layout.addWidget(value, 1)
            page.card_layout.addWidget(row)
            self.license_rows[label] = value
        page.card_layout.addStretch()
        return page

    def create_about_page(self):
        page = self.create_info_page("Hakkında", "MetaFold Virüs Temizleyici ürün bilgileri.")
        items = [
            ("Uygulama", APP_NAME),
            ("Geliştirici", "Ahmet Doğan"),
            ("Web", "www.metafold.net"),
            ("Amaç", "Android reklam virüslerini ve şüpheli paketleri ADB üzerinden analiz eder."),
        ]
        for key_text, value_text in items:
            row = QFrame()
            row.setObjectName("InfoRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(14, 10, 14, 10)
            key = QLabel(key_text)
            key.setObjectName("InfoKey")
            value = QLabel(value_text)
            value.setObjectName("InfoValue")
            value.setWordWrap(True)
            row_layout.addWidget(key)
            row_layout.addWidget(value, 1)
            page.card_layout.addWidget(row)
        page.card_layout.addStretch()
        return page

    def go_home(self):
        if self.current_user and hasattr(self, "cleaner_page"):
            self.stack.setCurrentWidget(self.cleaner_page)
            return
        self.stack.setCurrentWidget(self.login_page)

    def show_about(self):
        self.stack.setCurrentWidget(self.about_page)
        return
        QMessageBox.information(
            self,
            "Hakkında",
            "MetaFold Virüs Temizleyici\n\n"
            "Geliştirici: Ahmet Doğan\n"
            "Web: www.metafold.net\n\n"
            "Android reklam virüslerini ve şüpheli paketleri ADB üzerinden analiz eder."
        )

    def show_license_info(self):
        if not self.current_user:
            self.license_rows["Paket"].setText("Giriş yapılmadı")
            self.license_rows["Bitiş"].setText("-")
            self.license_rows["Kalan Süre"].setText("-")
            self.license_rows["Hesap"].setText("-")
            self.license_rows["Cihaz Limiti"].setText("-")
            self.stack.setCurrentWidget(self.license_page)
            return
        license_data = safe_dict_parse(self.current_user.get("_virus_license") or {})
        if not isinstance(license_data, dict):
            license_data = {}
        self.license_rows["Paket"].setText(license_title(license_data))
        self.license_rows["Bitiş"].setText(str(self.current_user.get("_virus_expiry", "-")))
        self.license_rows["Kalan Süre"].setText(f"{self.current_user.get('_virus_remaining', '-')} gün")
        self.license_rows["Hesap"].setText(str(self.current_user.get("_email", "-")))
        self.license_rows["Cihaz Limiti"].setText(str(license_limit(license_data)))
        self.stack.setCurrentWidget(self.license_page)
        return
        if not self.current_user:
            QMessageBox.information(self, "Lisans", "Henüz giriş yapılmadı.")
            return
        license_data = safe_dict_parse(self.current_user.get("_virus_license") or {})
        title = license_title(license_data if isinstance(license_data, dict) else {})
        expiry = self.current_user.get("_virus_expiry", "-")
        remaining = self.current_user.get("_virus_remaining", "-")
        QMessageBox.information(
            self,
            "Lisans",
            f"Paket: {title}\n"
            f"Bitiş: {expiry}\n"
            f"Kalan süre: {remaining} gün\n"
            f"Hesap: {self.current_user.get('_email', '-')}"
        )

    def start_login(self, email, password):
        if self.worker and self.worker.isRunning():
            return
        self.login_page.set_busy(True)
        self.worker = LoginWorker(email, password)
        self.worker.success.connect(self.show_cleaner)
        self.worker.device_limit.connect(lambda limit: self.handle_device_limit(email, password, limit))
        self.worker.failed.connect(self.handle_login_error)
        self.worker.finished.connect(self.login_worker_finished)
        self.worker.start()

    def start_register(self, email, password):
        if self.worker and self.worker.isRunning():
            return
        self.login_page.set_busy(True)
        self.worker = RegisterWorker(email, password)
        self.worker.success.connect(self.show_cleaner)
        self.worker.device_limit.connect(lambda limit: self.handle_device_limit(email, password, limit))
        self.worker.failed.connect(self.handle_login_error)
        self.worker.finished.connect(self.login_worker_finished)
        self.worker.start()

    def login_worker_finished(self):
        self.login_page.set_busy(False)
        self.worker = None

    def handle_device_limit(self, email, password, limit):
        QMessageBox.warning(
            self,
            "Cihaz Sınırı",
            "Bu Virüs Temizleyici lisansı yalnızca ilk yetkilendirilen bilgisayarda çalışır.\n\n"
            "Başka bilgisayarda kullanmak için yetkili kişinin Firebase üzerinden eski cihaz kaydını silmesi gerekir."
        )
        self.login_page.status_lbl.setText("Bu lisans başka bir bilgisayara kayıtlı.")

    def handle_login_error(self, title, message):
        QMessageBox.warning(self, title, message)
        self.login_page.status_lbl.setText("")

    def show_cleaner(self, user):
        self.current_user = user
        license_data = safe_dict_parse(user.get("_virus_license") or {})
        if not isinstance(license_data, dict):
            license_data = {}

        page = QWidget()
        self.cleaner_page = page
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        self.account_text.setText(
            f"{user.get('_email', '')}  |  {license_title(license_data)}  |  "
            f"Bitiş: {user.get('_virus_expiry', '-')}"
        )
        self.account_text.setVisible(True)
        self.title_logout_btn.setVisible(True)

        self.cleaner = AdbCleanerWidget(self)
        self.cleaner.set_theme(self.normalized_theme())
        self.cleaner.set_language(self.current_language())
        self.cleaner.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.cleaner, 1)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def logout(self):
        self.current_user = None
        if hasattr(self, "account_text"):
            self.account_text.setText("")
            self.account_text.setVisible(False)
        if hasattr(self, "title_logout_btn"):
            self.title_logout_btn.setVisible(False)
        self.stack.setCurrentWidget(self.login_page)



STANDALONE_STYLE = """
    QMainWindow {
        background: transparent;
    }
    QFrame#AppRoot {
        background: #080d16;
        border: 1px solid #253248;
        border-radius: 14px;
    }
    QFrame#WindowTitleBar {
        background: #0a111d;
        border-bottom: 1px solid #172033;
        border-top-left-radius: 13px;
        border-top-right-radius: 13px;
    }
    QLabel#WindowTitle {
        color: #edf5ff;
        font-size: 13px;
        font-weight: 800;
    }
    QLabel#WindowAccount {
        color: #bfdbfe;
        font-size: 12px;
        font-weight: 650;
        padding-left: 10px;
    }
    QPushButton#TitleLogoutBtn {
        background: #182233;
        border: 1px solid #3b4a61;
        color: #f8fafc;
        border-radius: 8px;
        font-weight: 800;
    }
    QPushButton#TitleLogoutBtn:hover {
        background: #223047;
        border-color: #60a5fa;
    }
    QPushButton#TitleToolBtn {
        background: #111a2a;
        border: 1px solid #334155;
        color: #e2e8f0;
        border-radius: 8px;
        font-weight: 800;
    }
    QPushButton#TitleToolBtn:hover {
        background: #1d2a3e;
        border-color: #60a5fa;
    }
    QComboBox#TitleThemeCombo,
    QComboBox#TitleLangCombo {
        background: #111a2a;
        border: 1px solid #334155;
        color: #e2e8f0;
        border-radius: 8px;
        padding-left: 10px;
        padding-right: 8px;
        font-weight: 800;
    }
    QComboBox#TitleThemeCombo:hover,
    QComboBox#TitleLangCombo:hover {
        background: #1d2a3e;
        border-color: #60a5fa;
    }
    QComboBox#TitleThemeCombo::drop-down,
    QComboBox#TitleLangCombo::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox#TitleThemeCombo QAbstractItemView,
    QComboBox#TitleLangCombo QAbstractItemView {
        background: #1f1d31;
        color: #ffffff;
        border: 1px solid #3f3d57;
        outline: 0;
        padding: 6px;
        selection-background-color: #17243a;
        selection-color: #ffffff;
    }
    QPushButton#WindowButton,
    QPushButton#CloseButton {
        background: transparent;
        border: none;
        border-radius: 6px;
        color: #cbd5e1;
        font-size: 17px;
        padding: 0;
    }
    QPushButton#WindowButton:hover {
        background: #1e293b;
    }
    QPushButton#CloseButton:hover {
        background: #ef4444;
        color: white;
    }
    QFrame#LoginShell {
        background: #0b1220;
        border: 1px solid #1d2a3e;
        border-radius: 22px;
    }
    QFrame#BrandPanel {
        background: #08111f;
        border-top-left-radius: 22px;
        border-bottom-left-radius: 22px;
    }
    QFrame#FormPanel {
        background: #0f1727;
        border-left: 1px solid #1d2a3e;
        border-top-right-radius: 22px;
        border-bottom-right-radius: 22px;
    }
    QLabel#HeroLogo {
        background: transparent;
    }
    QLabel#HeroTitle {
        color: #f8fafc;
        font-size: 38px;
        font-weight: 900;
        line-height: 1.05;
    }
    QLabel#HeroText {
        color: #c9d7ea;
        font-size: 14px;
        line-height: 1.45;
    }
    QLabel#HeroBullets {
        color: #dbeafe;
        font-size: 13px;
        line-height: 1.75;
    }
    QLabel#LoginTitle {
        color: #f8fafc;
        font-size: 27px;
        font-weight: 900;
    }
    QLabel#LoginSubtitle,
    QLabel#HelpText,
    QLabel#HeaderSubtitle {
        color: #aebbd0;
        font-size: 12px;
    }
    QLabel#StatusLabel {
        color: #fbbf24;
        min-height: 20px;
    }
    QLineEdit {
        min-height: 30px;
        border-radius: 10px;
        background: #111a2a;
        border: 1px solid #334155;
        padding-left: 12px;
        padding-right: 12px;
    }
    QLineEdit:focus {
        border: 2px solid #38bdf8;
        background: #0d1728;
        padding-left: 11px;
        padding-right: 11px;
    }
    QPushButton#PrimaryLoginBtn {
        min-height: 46px;
        font-size: 15px;
        background: #2563eb;
        border: 1px solid #60a5fa;
        border-radius: 11px;
        font-weight: 900;
    }
    QPushButton#PrimaryLoginBtn:hover {
        background: #1d4ed8;
    }
    QPushButton#BuyBtn {
        min-height: 40px;
        background: #16a34a;
        border: 1px solid #22c55e;
        color: white;
        border-radius: 10px;
        font-weight: 900;
    }
    QPushButton#BuyBtn:hover {
        background: #15803d;
    }
    QPushButton#GhostBtn {
        min-height: 40px;
        background: #0b1220;
        border: 1px solid #475569;
        color: #dbeafe;
        border-radius: 10px;
        font-weight: 800;
    }
    QPushButton#GhostBtn:hover {
        background: #111827;
        border-color: #64748b;
    }
    QFrame#StandaloneHeader {
        background: #0e1728;
        border: 1px solid #263244;
        border-radius: 12px;
    }
    QLabel#HeaderTitle {
        color: #f8fafc;
        font-size: 18px;
        font-weight: 900;
    }
    QPushButton#LogoutBtn {
        background: #182233;
        border: 1px solid #3b4a61;
        border-radius: 9px;
        min-width: 92px;
        font-weight: 800;
    }
    QPushButton#LogoutBtn:hover {
        background: #243247;
    }
    QWidget#InfoPage {
        background: #080d16;
    }
    QFrame#InfoHeader,
    QFrame#InfoCard {
        background: #0f1727;
        border: 1px solid #253248;
        border-radius: 14px;
    }
    QLabel#InfoTitle {
        color: #f8fafc;
        font-size: 26px;
        font-weight: 900;
    }
    QLabel#InfoSubtitle {
        color: #aebbd0;
        font-size: 13px;
    }
    QFrame#InfoRow {
        background: #111a2a;
        border: 1px solid #263244;
        border-radius: 10px;
    }
    QLabel#InfoKey {
        color: #93a4ba;
        font-size: 12px;
        font-weight: 800;
        min-width: 120px;
    }
    QLabel#InfoValue {
        color: #f8fafc;
        font-size: 14px;
        font-weight: 800;
    }
    QPushButton#InfoBackBtn {
        background: #182233;
        border: 1px solid #3b4a61;
        color: #f8fafc;
        border-radius: 9px;
        font-weight: 800;
    }
    QPushButton#InfoBackBtn:hover {
        background: #243247;
        border-color: #60a5fa;
    }
"""

STANDALONE_LIGHT_STYLE = """
    QFrame#AppRoot {
        background: #eef3f8;
        border: 1px solid #c5d0dd;
    }
    QFrame#WindowTitleBar {
        background: #f8fbff;
        border-bottom: 1px solid #d5dee9;
    }
    QLabel#WindowTitle {
        color: #0f172a;
    }
    QLabel#WindowAccount {
        color: #1d4ed8;
    }
    QPushButton#TitleLogoutBtn,
    QPushButton#TitleToolBtn {
        background: #edf3fa;
        border: 1px solid #c4d1df;
        color: #0f172a;
    }
    QPushButton#TitleLogoutBtn:hover,
    QPushButton#TitleToolBtn:hover {
        background: #e0ebf7;
        border-color: #2563eb;
    }
    QComboBox#TitleThemeCombo,
    QComboBox#TitleLangCombo {
        background: #edf3fa;
        border: 1px solid #c4d1df;
        color: #0f172a;
        border-radius: 8px;
        padding-left: 10px;
        padding-right: 8px;
        font-weight: 800;
    }
    QComboBox#TitleThemeCombo:hover,
    QComboBox#TitleLangCombo:hover {
        background: #e0ebf7;
        border-color: #2563eb;
    }
    QComboBox#TitleThemeCombo::drop-down,
    QComboBox#TitleLangCombo::drop-down {
        border: none;
        width: 24px;
    }
    QComboBox#TitleThemeCombo QAbstractItemView,
    QComboBox#TitleLangCombo QAbstractItemView {
        background: #ffffff;
        color: #0f172a;
        border: 1px solid #c4d1df;
        outline: 0;
        padding: 6px;
        selection-background-color: #dbeafe;
        selection-color: #0f172a;
    }
    QFrame#LoginShell,
    QFrame#FormPanel,
    QFrame#BrandPanel {
        background: #f8fbff;
        border-color: #d5dee9;
    }
    QLabel#HeroTitle,
    QLabel#LoginTitle {
        color: #0f172a;
    }
    QLabel#HeroText,
    QLabel#HeroBullets,
    QLabel#LoginSubtitle,
    QLabel#HelpText {
        color: #334155;
    }
    QLabel#StatusLabel {
        color: #b45309;
    }
    QLineEdit {
        background: #f8fbff;
        border: 1px solid #c4d1df;
        color: #0f172a;
    }
    QLineEdit:focus {
        border: 2px solid #2563eb;
        background: #ffffff;
    }
    QPushButton#GhostBtn {
        background: #f8fbff;
        border: 1px solid #c4d1df;
        color: #0f172a;
    }
    QPushButton#GhostBtn:hover {
        background: #e0ebf7;
        border-color: #2563eb;
    }
    QWidget#InfoPage {
        background: #eef3f8;
    }
    QFrame#InfoHeader,
    QFrame#InfoCard {
        background: #f8fbff;
        border: 1px solid #d5dee9;
    }
    QLabel#InfoTitle {
        color: #0f172a;
    }
    QLabel#InfoSubtitle {
        color: #475569;
    }
    QFrame#InfoRow {
        background: #edf3fa;
        border: 1px solid #d7e1ec;
    }
    QLabel#InfoKey {
        color: #64748b;
    }
    QLabel#InfoValue {
        color: #0f172a;
    }
    QPushButton#InfoBackBtn {
        background: #edf3fa;
        border: 1px solid #c4d1df;
        color: #0f172a;
    }
    QPushButton#InfoBackBtn:hover {
        background: #e0ebf7;
        border-color: #2563eb;
    }
"""

STANDALONE_OCEAN_STYLE = """
    QFrame#AppRoot { background: #071923; border: 1px solid #155e75; }
    QFrame#WindowTitleBar { background: #082333; border-bottom: 1px solid #176b82; }
    QPushButton#TitleLogoutBtn, QPushButton#TitleToolBtn,
    QComboBox#TitleThemeCombo, QComboBox#TitleLangCombo {
        background: #0b2a3c; border: 1px solid #176b82; color: #ecfeff;
    }
    QPushButton#TitleLogoutBtn:hover, QPushButton#TitleToolBtn:hover,
    QComboBox#TitleThemeCombo:hover, QComboBox#TitleLangCombo:hover {
        background: #0e3a52; border-color: #67e8f9;
    }
    QFrame#InfoHeader, QFrame#InfoCard, QFrame#LoginShell, QFrame#FormPanel {
        background: #0b2433; border-color: #155e75;
    }
"""

STANDALONE_EMERALD_STYLE = """
    QFrame#AppRoot { background: #eefcf6; border: 1px solid #a7d8c4; }
    QFrame#WindowTitleBar { background: #f7fffb; border-bottom: 1px solid #b7dfcf; }
    QLabel#WindowTitle { color: #0f2d22; }
    QLabel#WindowAccount { color: #047857; }
    QPushButton#TitleLogoutBtn, QPushButton#TitleToolBtn,
    QComboBox#TitleThemeCombo, QComboBox#TitleLangCombo {
        background: #e6f7ef; border: 1px solid #a7d8c4; color: #0f2d22;
    }
    QPushButton#TitleLogoutBtn:hover, QPushButton#TitleToolBtn:hover,
    QComboBox#TitleThemeCombo:hover, QComboBox#TitleLangCombo:hover {
        background: #d6f3e5; border-color: #059669;
    }
    QFrame#LoginShell, QFrame#FormPanel, QFrame#BrandPanel,
    QFrame#InfoHeader, QFrame#InfoCard {
        background: #f7fffb; border-color: #b7dfcf;
    }
    QLabel#HeroTitle, QLabel#LoginTitle, QLabel#InfoTitle { color: #0f2d22; }
    QLabel#HeroText, QLabel#HeroBullets, QLabel#LoginSubtitle,
    QLabel#HelpText, QLabel#InfoSubtitle { color: #31584a; }
"""

STANDALONE_GRAPHITE_STYLE = """
    QFrame#AppRoot { background: #111113; border: 1px solid #3f3f46; }
    QFrame#WindowTitleBar { background: #18181b; border-bottom: 1px solid #2f2f34; }
    QPushButton#TitleLogoutBtn, QPushButton#TitleToolBtn,
    QComboBox#TitleThemeCombo, QComboBox#TitleLangCombo {
        background: #202024; border: 1px solid #3f3f46; color: #f4f4f5;
    }
    QPushButton#TitleLogoutBtn:hover, QPushButton#TitleToolBtn:hover,
    QComboBox#TitleThemeCombo:hover, QComboBox#TitleLangCombo:hover {
        background: #27272a; border-color: #f59e0b;
    }
    QFrame#LoginShell, QFrame#FormPanel, QFrame#BrandPanel,
    QFrame#InfoHeader, QFrame#InfoCard {
        background: #18181b; border-color: #3f3f46;
    }
"""


def main():
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setOrganizationName("MetaFold")
    app.setOrganizationDomain("metafold.net")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName(APP_USER_MODEL_ID)
    app.setWindowIcon(QIcon(resource_path(APP_LOGO_PNG)))
    window = VirusCleanerShell()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
