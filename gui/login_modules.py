# -*- coding: utf-8 -*-
import datetime
import base64
import ctypes
import hashlib
from ctypes import wintypes
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QCheckBox, QStackedWidget, QMessageBox, QFileDialog, QApplication, QGraphicsOpacityEffect, QSizePolicy, QDialog, QTextEdit
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QSettings, QRectF, QEasingCurve
from PyQt6.QtGui import QPixmap, QFont, QPainter, QColor, QPen, QLinearGradient
from config import resource_path, get_device_id, safe_dict_parse, check_license_status, describe_connection_error, MEVCUT_SURUM, read_license_data
from database.threads import auth, db

AGREEMENTS_VERSION = "2026.05.20"

def profile_device_limit(profile, keys, default=2):
    if not isinstance(profile, dict):
        return default
    for key in keys:
        raw = str(profile.get(key, "") or "").strip()
        if not raw:
            continue
        try:
            limit = int(float(raw.replace(",", ".")))
            return max(1, min(limit, 99))
        except Exception:
            pass
    return default

AGREEMENT_TEXTS = {
    "terms": {
        "title": "Kullanıcı Sözleşmesi",
        "html": """
            <h2>Kullanıcı Sözleşmesi</h2>
            <p>Bu sözleşme MetaFold Teknik Servis uygulamasını kullanan işletme hesabı için temel kullanım şartlarını açıklar.</p>
            <ul>
                <li>Hesap sahibi, uygulamaya girilen müşteri, cihaz, servis, ödeme ve stok bilgilerinin doğruluğundan sorumludur.</li>
                <li>Hesap sahibi, kendi çalışanlarının ve yetkili kullanıcılarının uygulama içindeki işlemlerinden sorumludur.</li>
                <li>Uygulama; servis takibi, müşteri bilgilendirme, stok ve kasa yönetimi amacıyla kullanılmalıdır.</li>
                <li>Hesap bilgileri, ekran şifreleri ve giriş bilgileri üçüncü kişilerle paylaşılmamalıdır.</li>
                <li>Yetkisiz erişim, veri silme, tersine mühendislik, lisans atlatma veya kötüye kullanım girişimleri yasaktır.</li>
                <li>Hesap sahibi, müşteri verilerini hukuka uygun şekilde toplamak ve gerektiğinde müşterilerini bilgilendirmekle yükümlüdür.</li>
            </ul>
            <p>Bu metin genel bilgilendirme amaçlıdır. İşletmenizin özel hukuki ihtiyacı için profesyonel hukuki destek almanız önerilir.</p>
        """,
    },
    "privacy": {
        "title": "KVKK ve Gizlilik Aydınlatma Metni",
        "html": """
            <h2>KVKK ve Gizlilik Aydınlatma Metni</h2>
            <p>MetaFold Teknik Servis uygulamasında işletme hesabı kapsamında aşağıdaki kişisel veriler işlenebilir:</p>
            <ul>
                <li>Hesap bilgileri: firma adı, e-posta adresi, lisans ve cihaz bilgileri.</li>
                <li>Müşteri kayıtları: ad soyad, telefon, adres, cihaz bilgisi, arıza açıklaması, işlem notları ve ödeme bilgileri.</li>
                <li>Servis belgeleri: cihaz fotoğrafları, fiş ve takip bağlantısı bilgileri.</li>
            </ul>
            <p>Bu veriler; teknik servis sürecini yürütmek, müşteri cihaz durumunu takip etmek, fiş/rapor oluşturmak, stok ve kasa kayıtlarını tutmak, lisans ve güvenlik kontrollerini sağlamak amacıyla işlenir.</p>
            <p>Veriler uygulamanın kullandığı bulut altyapısında ve kullanıcının yerel bilgisayarında saklanabilir. Hesap sahibi, kendi müşterilerine karşı veri sorumlusu sıfatıyla gerekli bilgilendirmeleri yapmakla yükümlüdür.</p>
            <p>Veri güvenliği için kullanıcı bazlı erişim, lisans kontrolü, oturum kontrolü ve veritabanı güvenlik kuralları uygulanır. Buna rağmen hesap şifresinin korunması, cihaz güvenliği ve yetkili personel yönetimi hesap sahibinin sorumluluğundadır.</p>
        """,
    },
    "cloud": {
        "title": "Bulut Senkronizasyonu ve Fotoğraf Saklama Açık Rızası",
        "html": """
            <h2>Bulut Senkronizasyonu ve Fotoğraf Saklama Açık Rızası</h2>
            <p>Uygulamanın birden fazla cihazda çalışabilmesi, kayıtların eş zamanlı görülebilmesi ve cihaz fotoğraflarının servis kayıtlarına eklenebilmesi için bazı veriler bulut servislerine aktarılabilir.</p>
            <ul>
                <li>Servis kayıtları ve müşteri bilgileri Firebase Realtime Database üzerinde saklanabilir.</li>
                <li>Cihaz fotoğrafları üçüncü taraf görsel barındırma veya bulut altyapısında saklanabilir.</li>
                <li>Müşteri takip linkleri, yalnızca ilgili servis kaydının sınırlı durum bilgisini göstermek için kullanılabilir.</li>
            </ul>
            <p>Bu onay, bulut senkronizasyonu ve cihaz fotoğraflarının servis süreci için saklanmasına ilişkindir. Hesap sahibi, kendi müşterilerinden gerekli bilgilendirme ve izin süreçlerini almakla yükümlüdür.</p>
        """,
    },
}

class AgreementDialog(QDialog):
    def __init__(self, title, html_content, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(620, 520)
        layout = QVBoxLayout(self)
        header = QLabel(f"<b>{title}</b>")
        header.setStyleSheet("font-size: 18px;")
        layout.addWidget(header)
        text = QTextEdit()
        text.setReadOnly(True)
        text.setHtml(html_content)
        text.setStyleSheet("QTextEdit { padding: 12px; font-size: 14px; }")
        layout.addWidget(text)
        btn = QPushButton("Okudum")
        btn.setFixedHeight(38)
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

def _dpapi_blob(data):
    return DATA_BLOB(len(data), ctypes.cast(ctypes.create_string_buffer(data), ctypes.POINTER(ctypes.c_char)))

def protect_secret(text):
    if not text:
        return ""
    raw = text.encode("utf-8")
    in_blob = _dpapi_blob(raw)
    out_blob = DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        return ""
    try:
        encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)

def unprotect_secret(value):
    if not value:
        return ""
    try:
        encrypted = base64.b64decode(str(value).encode("ascii"))
        in_blob = _dpapi_blob(encrypted)
        out_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
            return ""
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except:
        return ""

def trial_device_key():
    raw = f"metafold-trial:{get_device_id()}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

class SplashScreen(QWidget):
    def __init__(self, next_window):
        super().__init__()
        self.next_window = next_window
        self.phase = 0
        self.progress_phase = 0
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(720, 300)
        qr = self.frameGeometry()
        cp = QApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

        self.logo_pix = QPixmap(resource_path("metafold.ico"))
        self.banner_pix = QPixmap(resource_path("banner.png"))
        if self.banner_pix.isNull():
            self.banner_pix = QPixmap(resource_path("metafold_banner.png"))

        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self.tick_splash)
        self.render_timer.start(33)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(320)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.start_fade_in()

    def tick_splash(self):
        self.phase = (int(getattr(self, "phase", 0)) + 1) % 360
        self.progress_phase = (int(getattr(self, "progress_phase", 0)) + 4) % 360
        self.update()

    def splash_gradient(self):
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#050814"))
        gradient.setColorAt(0.42, QColor("#0b1424"))
        gradient.setColorAt(0.72, QColor("#10233d"))
        gradient.setColorAt(1.0, QColor("#07111f"))
        return gradient

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        outer = QRectF(8, 8, self.width() - 16, self.height() - 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.splash_gradient())
        painter.drawRoundedRect(outer, 26, 26)

        panel = QRectF(28, 28, self.width() - 56, self.height() - 56)
        painter.setBrush(QColor(6, 12, 28, 142))
        painter.setPen(QPen(QColor(255, 255, 255, 46), 1))
        painter.drawRoundedRect(panel, 22, 22)

        if not self.banner_pix.isNull():
            banner = self.banner_pix.scaled(210, 52, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(int((self.width() - banner.width()) / 2), 42, banner)

        if not self.logo_pix.isNull():
            logo_size = 76
            logo_x = int((self.width() - logo_size) / 2)
            logo_y = 94
            painter.setBrush(QColor(255, 255, 255, 22))
            painter.setPen(QPen(QColor("#2f81ff"), 3))
            painter.drawEllipse(logo_x - 6, logo_y - 6, logo_size + 12, logo_size + 12)
            painter.drawPixmap(logo_x, logo_y, self.logo_pix.scaled(logo_size, logo_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        painter.setPen(QColor(255, 255, 255, 245))
        painter.setFont(QFont("Segoe UI", 22, QFont.Weight.Black))
        painter.drawText(QRectF(0, 180, self.width(), 36), Qt.AlignmentFlag.AlignCenter, "MetaFold Teknik Servis ERP")
        painter.setPen(QColor(203, 213, 225, 232))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        painter.drawText(QRectF(0, 215, self.width(), 22), Qt.AlignmentFlag.AlignCenter, f"v{MEVCUT_SURUM}  |  Sistem hazirlaniyor")

        bar_w = 360
        bar_h = 10
        bar_x = int((self.width() - bar_w) / 2)
        bar_y = 252
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 42))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 5, 5)

        bar_gradient = QLinearGradient(bar_x, bar_y, bar_x + bar_w, bar_y)
        bar_gradient.setColorAt(0.0, QColor("#1d4ed8"))
        bar_gradient.setColorAt(0.45, QColor("#2563eb"))
        bar_gradient.setColorAt(0.72, QColor("#06b6d4"))
        bar_gradient.setColorAt(1.0, QColor("#38bdf8"))
        painter.setBrush(bar_gradient)
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 5, 5)
        painter.end()

    def start_fade_in(self):
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass
        self.anim.setDuration(320)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.anim.setStartValue(0)
        self.anim.setEndValue(1)
        self.anim.finished.connect(self.schedule_fade_out)
        self.anim.start()

    def schedule_fade_out(self):
        QTimer.singleShot(900, self.start_fade_out)

    def start_fade_out(self):
        try:
            self.anim.finished.disconnect()
        except Exception:
            pass
        self.anim.setDuration(280)
        self.anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.anim.setStartValue(1)
        self.anim.setEndValue(0)
        self.anim.finished.connect(self.finish_splash)
        self.anim.start()

    def finish_splash(self): 
        if hasattr(self, "render_timer"):
            self.render_timer.stop()
        self.close()
        if not self.next_window.is_intentionally_hidden:
            if hasattr(self.next_window, "show_login_polished"):
                self.next_window.show_login_polished()
            else:
                if hasattr(self.next_window, "center_on_active_screen"):
                    self.next_window.center_on_active_screen(force=True, reset_user_position=True)
                self.next_window.show()

class LoginScreen(QWidget):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.settings = QSettings("MetaFold", "Servis")
        self.current_theme = "Dark"
        self.avatar_glow_hue = 190
        self.login_bg_phase = 0
        self.setFont(QFont("Segoe UI", 10))
        self.setStyleSheet("LoginScreen, QWidget { background: transparent; }")
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        self.bg_frame = QWidget(self)
        self.bg_frame.setObjectName("LoginFrame")
        self.bg_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.bg_frame.setStyleSheet(self.login_frame_style())
        
        frame_layout = QVBoxLayout(self.bg_frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)
        
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(20, 14, 20, 0)
        self.login_banner_label = QLabel()
        self.login_banner_label.setFixedSize(150, 34)
        banner_pix = QPixmap(resource_path("banner.png"))
        if banner_pix.isNull():
            banner_pix = QPixmap(resource_path("metafold_banner.png"))
        if not banner_pix.isNull():
            self.login_banner_label.setPixmap(banner_pix.scaled(150, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.login_banner_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.login_btn_min = QPushButton("—")
        self.login_btn_close = QPushButton("×")
        for b in [self.login_btn_min, self.login_btn_close]: 
            b.setFixedSize(32, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_btn_min.clicked.connect(self.manager.showMinimized)
        self.login_btn_close.clicked.connect(self.manager.handle_close)
        top_layout.addWidget(self.login_banner_label)
        top_layout.addStretch()
        top_layout.addWidget(self.login_btn_min)
        top_layout.addWidget(self.login_btn_close)
        frame_layout.addLayout(top_layout)

        self.login_hero_title = QLabel("MetaFold Teknik Servis ERP")
        self.login_hero_title.setObjectName("LoginHeroTitle")
        self.login_hero_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.login_hero_subtitle = QLabel("Servis, stok, kasa ve müşteri takibini tek merkezden yönetin")
        self.login_hero_subtitle.setObjectName("LoginHeroSubtitle")
        self.login_hero_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.apply_login_chrome_style()
        frame_layout.addSpacing(2)
        frame_layout.addWidget(self.login_hero_title)
        frame_layout.addWidget(self.login_hero_subtitle)
        
        self.auth_stack = QStackedWidget()
        self.auth_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self.auth_pages = []
        self.init_login_page()
        self.init_register_page()
        self.auth_stack.currentChanged.connect(self.sync_auth_stack_size)
        self.sync_auth_stack_size(0)
        self.avatar_glow_timer = QTimer(self)
        self.avatar_glow_timer.timeout.connect(self.tick_avatar_glow)
        self.avatar_glow_timer.start(160)
        self.login_bg_timer = QTimer(self)
        self.login_bg_timer.timeout.connect(self.tick_login_background)
        self.login_bg_timer.start(1800)
        
        frame_layout.addStretch(1)
        frame_layout.addWidget(self.auth_stack, alignment=Qt.AlignmentFlag.AlignCenter)
        frame_layout.addStretch(2)
        main_layout.addWidget(self.bg_frame)
        
        if self.settings.value("remember", "false") == "true":
            kayitli_mail = str(self.settings.value("email", ""))
            kayitli_sifre = unprotect_secret(self.settings.value("password_secure", ""))
            self.login_email.setText(kayitli_mail)
            self.login_pass.setText(kayitli_sifre)
            self.remember_cb.setChecked(True)
            if self.settings.value("auto_login", "false") == "true":
                self.auto_login_cb.setChecked(True)
                if kayitli_mail and kayitli_sifre: 
                    self.lbl_status.setText("Sistem senkronizasyonu kuruluyor...")
                    QTimer.singleShot(1500, self.handle_login)

    def animated_login_gradient(self, theme):
        theme = str(theme or "Dark")
        if theme == "Light":
            stops = [
                "stop:0.00 #eef5ff",
                "stop:0.45 #dbeafe",
                "stop:1.00 #f8fafc",
            ]
        elif theme == "Emerald":
            stops = [
                "stop:0.00 #031712",
                "stop:0.50 #0f2f2a",
                "stop:1.00 #06111f",
            ]
        elif theme == "Ocean":
            stops = [
                "stop:0.00 #061322",
                "stop:0.48 #0b2a45",
                "stop:1.00 #07111f",
            ]
        elif theme == "Graphite":
            stops = [
                "stop:0.00 #080b10",
                "stop:0.52 #151c27",
                "stop:1.00 #0a0f18",
            ]
        else:
            stops = [
                "stop:0.00 #060914",
                "stop:0.45 #0d1728",
                "stop:0.74 #10233d",
                "stop:1.00 #07111f",
            ]
        return f"qlineargradient(x1:0, y1:0, x2:1, y2:1, {', '.join(stops)})"

    def login_theme_palette(self):
        theme = str(getattr(self, "current_theme", "Dark"))
        aurora = self.animated_login_gradient(theme)
        if theme == "Light":
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(255, 255, 255, 0.74)",
                "field_bg": "rgba(255, 255, 255, 0.82)",
                "field_hover": "rgba(255, 255, 255, 0.96)",
                "text": "#0f172a",
                "sub": "#475569",
                "border": "rgba(37, 99, 235, 0.24)",
                "accent": "#2563eb",
                "accent_hover": "#0891b2",
                "link": "#2563eb",
                "link_hover": "#0891b2",
                "top_text": "#0f172a",
                "chrome_bg": "rgba(255,255,255,0.58)",
                "chrome_border": "rgba(15,23,42,0.12)",
                "button_stops": ("#2563eb", "#06b6d4", "#14b8a6", "#84cc16"),
            }
        if theme == "Emerald":
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(6, 78, 59, 0.48)",
                "field_bg": "rgba(236, 253, 245, 0.10)",
                "field_hover": "rgba(236, 253, 245, 0.15)",
                "text": "#ecfdf5",
                "sub": "#bbf7d0",
                "border": "rgba(52, 211, 153, 0.35)",
                "accent": "#10b981",
                "accent_hover": "#34d399",
                "link": "#86efac",
                "link_hover": "#bbf7d0",
                "top_text": "#ecfdf5",
                "chrome_bg": "rgba(236,253,245,0.10)",
                "chrome_border": "rgba(236,253,245,0.20)",
                "button_stops": ("#059669", "#10b981", "#22c55e", "#a3e635"),
            }
        if theme == "Ocean":
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(8, 47, 73, 0.50)",
                "field_bg": "rgba(224, 242, 254, 0.10)",
                "field_hover": "rgba(224, 242, 254, 0.15)",
                "text": "#f0f9ff",
                "sub": "#bae6fd",
                "border": "rgba(125, 211, 252, 0.35)",
                "accent": "#0284c7",
                "accent_hover": "#22d3ee",
                "link": "#7dd3fc",
                "link_hover": "#67e8f9",
                "top_text": "#f0f9ff",
                "chrome_bg": "rgba(224,242,254,0.10)",
                "chrome_border": "rgba(224,242,254,0.20)",
                "button_stops": ("#2563eb", "#0ea5e9", "#06b6d4", "#2dd4bf"),
            }
        if theme == "Graphite":
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(17, 24, 39, 0.56)",
                "field_bg": "rgba(255, 255, 255, 0.08)",
                "field_hover": "rgba(255, 255, 255, 0.12)",
                "text": "#f8fafc",
                "sub": "#cbd5e1",
                "border": "rgba(148, 163, 184, 0.34)",
                "accent": "#64748b",
                "accent_hover": "#38bdf8",
                "link": "#93c5fd",
                "link_hover": "#67e8f9",
                "top_text": "#f8fafc",
                "chrome_bg": "rgba(255,255,255,0.10)",
                "chrome_border": "rgba(255,255,255,0.18)",
                "button_stops": ("#64748b", "#2563eb", "#38bdf8", "#22d3ee"),
            }
        return {
            "frame_bg": aurora,
            "card_bg": "rgba(15, 23, 42, 0.74)",
            "field_bg": "rgba(255, 255, 255, 0.08)",
            "field_hover": "rgba(255, 255, 255, 0.13)",
            "text": "#f8fafc",
            "sub": "#cbd5e1",
            "border": "rgba(147, 197, 253, 0.34)",
            "accent": "#2563eb",
            "accent_hover": "#22d3ee",
            "link": "#93c5fd",
            "link_hover": "#67e8f9",
            "top_text": "#f8fafc",
            "chrome_bg": "rgba(255,255,255,0.10)",
            "chrome_border": "rgba(255,255,255,0.18)",
            "button_stops": ("#1d4ed8", "#2563eb", "#06b6d4", "#38bdf8"),
        }

    def apply_login_chrome_style(self):
        p = self.login_theme_palette()
        if hasattr(self, "login_hero_title"):
            self.login_hero_title.setStyleSheet(f"QLabel#LoginHeroTitle {{ color: {p['top_text']}; font-size: 28px; font-weight: 900; letter-spacing: 0px; }}")
        if hasattr(self, "login_hero_subtitle"):
            self.login_hero_subtitle.setStyleSheet(f"QLabel#LoginHeroSubtitle {{ color: {p['sub']}; font-size: 13px; font-weight: 700; }}")
        chrome = f"QPushButton {{ background-color: {p['chrome_bg']}; color: {p['top_text']}; border: 1px solid {p['chrome_border']}; border-radius: 8px; font-size: 15px; }} QPushButton:hover {{ background-color: rgba(255,255,255,0.20); }}"
        close = f"QPushButton {{ background-color: {p['chrome_bg']}; color: {p['top_text']}; border: 1px solid {p['chrome_border']}; border-radius: 8px; font-size: 15px; }} QPushButton:hover {{ background-color: #e81123; color: white; border-color: #e81123; }}"
        if hasattr(self, "login_btn_min"):
            self.login_btn_min.setStyleSheet(chrome)
        if hasattr(self, "login_btn_close"):
            self.login_btn_close.setStyleSheet(close)

    def login_card_style(self):
        p = self.login_theme_palette()
        text = p["text"]
        sub = p["sub"]
        border = p["border"]
        accent = p["accent"]
        accent_hover = p["accent_hover"]
        b0, b1, b2, b3 = p["button_stops"]
        return f"""
            #LoginCard {{
                background-color: {p["card_bg"]};
                border: 1px solid {border};
                border-radius: 22px;
            }}
            QLineEdit {{
                background-color: {p["field_bg"]};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 9px 14px;
                color: {text};
                font-size: 15px;
                font-weight: 700;
                selection-background-color: {accent};
            }}
            QLineEdit:hover {{
                border: 1px solid rgba(125, 211, 252, 0.45);
                background-color: {p["field_hover"]};
            }}
            QLineEdit:focus {{
                border: 2px solid {accent_hover};
                padding: 8px 13px;
                background-color: {p["field_hover"]};
            }}
            QCheckBox {{
                color: {sub};
                font-size: 13px;
                spacing: 7px;
                min-height: 24px;
            }}
            QCheckBox::indicator {{
                width: 17px;
                height: 17px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.30);
                background-color: rgba(255, 255, 255, 0.08);
            }}
            QCheckBox::indicator:checked {{
                background-color: {accent_hover};
                border: 1px solid {accent_hover};
            }}
            QPushButton#LoginBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {b0},
                    stop:0.46 {b1},
                    stop:0.74 {b2},
                    stop:1 {b3});
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.48);
                border-radius: 8px;
                padding: 10px;
                font-weight: bold;
                font-size: 15px;
            }}
            QPushButton#LoginBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {b1},
                    stop:0.46 {b2},
                    stop:0.74 {b3},
                    stop:1 {b2});
            }}
            QPushButton#LoginBtn:pressed {{
                background-color: #1e40af;
            }}
            QPushButton#ForgotBtn {{
                background-color: transparent;
                color: {p["link"]};
                font-size: 13px;
                border: none;
                padding: 6px;
            }}
            QPushButton#ForgotBtn:hover {{
                color: {p["link_hover"]};
                text-decoration: underline;
            }}
            QLabel#Title {{
                font-size: 18px;
                font-weight: 900;
                color: {text};
            }}
            QLabel#SubTitle {{
                font-size: 13px;
                color: {sub};
            }}
            QPushButton#AgreementBtn {{
                background-color: transparent;
                color: {p["link"]};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 5px 8px;
                font-size: 12px;
            }}
            QPushButton#AgreementBtn:hover {{
                border-color: {p["link_hover"]};
                background-color: rgba(37, 99, 235, 0.18);
            }}
        """

    def login_frame_style(self):
        p = self.login_theme_palette()
        return f"""
            #LoginFrame {{
                background: {p["frame_bg"]};
                border-radius: 0px;
            }}
        """

    def refresh_theme(self, theme_name=None):
        if theme_name:
            self.current_theme = str(theme_name)
        if hasattr(self, "bg_frame"):
            self.bg_frame.setStyleSheet(self.login_frame_style())
        self.apply_login_chrome_style()
        for page in getattr(self, "auth_pages", []):
            page.setStyleSheet(self.login_card_style())

    def sync_auth_stack_size(self, index):
        if not hasattr(self, "auth_stack"):
            return
        widget = self.auth_stack.widget(index)
        if widget is not None:
            self.auth_stack.setFixedSize(widget.size())

    def show_register_page(self):
        self.auth_stack.setCurrentIndex(1)

    def show_login_page(self):
        self.auth_stack.setCurrentIndex(0)

    def init_login_page(self):
        p = QWidget()
        p.setObjectName("LoginCard")
        p.setStyleSheet(self.login_card_style())
        self.auth_pages.append(p)
        l = QVBoxLayout(p)
        l.setContentsMargins(34, 22, 34, 16)
        l.setSpacing(3)
        p.setFixedSize(372, 388)
        
        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(74, 74)
        self.avatar_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.avatar_label.setStyleSheet("background-color: transparent;")
        self.update_avatar(use_custom=False)

        l.addWidget(self.avatar_label, alignment=Qt.AlignmentFlag.AlignCenter)
        l.addSpacing(18)
        
        self.login_email = QLineEdit()
        self.login_email.setPlaceholderText("E-posta Adresi")
        self.login_email.setFixedHeight(40)
        self.login_pass = QLineEdit()
        self.login_pass.setPlaceholderText("Şifre")
        self.login_pass.setFixedHeight(40)
        self.login_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.login_email.returnPressed.connect(self.handle_login)
        self.login_pass.returnPressed.connect(self.handle_login)
        l.addWidget(self.login_email)
        l.addWidget(self.login_pass)
        l.addSpacing(5)

        b_forgot = QPushButton("Şifremi Unuttum")
        b_forgot.setObjectName("ForgotBtn")
        b_forgot.setFixedHeight(26)
        b_forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        b_forgot.clicked.connect(self.handle_forgot_password)
        h_cb = QHBoxLayout()
        h_cb.setContentsMargins(0, 0, 0, 0)
        self.remember_cb = QCheckBox("Beni Hatırla")
        self.auto_login_cb = QCheckBox("Otomatik Giriş")
        h_cb.addWidget(self.remember_cb)
        h_cb.addWidget(self.auto_login_cb)
        h_cb.setSpacing(20)
        l.addLayout(h_cb)
        l.addWidget(b_forgot, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet("color: #f87171; font-size: 13px;")
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setFixedHeight(14)
        l.addWidget(self.lbl_status)
        
        b = QPushButton("Giriş Yap")
        b.setObjectName("LoginBtn")
        b.setFixedHeight(42)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.handle_login)
        l.addWidget(b)
        
        b_reg = QPushButton("Yeni Firma Kaydı Oluştur")
        b_reg.setObjectName("ForgotBtn")
        b_reg.setFixedHeight(26)
        b_reg.setCursor(Qt.CursorShape.PointingHandCursor)
        b_reg.clicked.connect(self.show_register_page)
        l.addWidget(b_reg, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.auth_stack.addWidget(p)

    def handle_forgot_password(self):
        email = self.login_email.text().strip()
        if not email:
            QMessageBox.warning(self, "E-posta Gerekli", "Şifre sıfırlama bağlantısı için e-posta adresinizi yazın.")
            self.login_email.setFocus()
            return
        try:
            auth.send_password_reset_email(email)
            QMessageBox.information(
                self,
                "Şifre Sıfırlama",
                "Şifre sıfırlama bağlantısı e-posta adresinize gönderildi.\n\n"
                "Mesajı gelen kutusunda göremezseniz lütfen spam/gereksiz klasörünü de kontrol edin."
            )
        except Exception as e:
            QMessageBox.warning(self, "Şifre Sıfırlama Hatası", f"Bağlantı gönderilemedi:\n{str(e)}")

    def tick_avatar_glow(self):
        if not hasattr(self, "avatar_label") or not self.avatar_label.isVisible():
            return
        self.avatar_glow_hue = (int(getattr(self, "avatar_glow_hue", 190)) + 3) % 360
        self.update_avatar(use_custom=False)

    def tick_login_background(self):
        if not self.isVisible() or not hasattr(self, "bg_frame"):
            return
        self.login_bg_phase = (int(getattr(self, "login_bg_phase", 0)) + 2) % 360
        self.bg_frame.setStyleSheet(self.login_frame_style())

    def update_avatar(self, use_custom=False):
        custom_logo = ""
        pixmap = QPixmap(custom_logo) if custom_logo else QPixmap(resource_path("metafold.ico"))
        if pixmap.isNull():
            pixmap = QPixmap(resource_path("metafold.ico"))
        size = self.avatar_label.width() if hasattr(self, "avatar_label") and self.avatar_label.width() > 0 else 86
        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(255, 255, 255, 235))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, size, size)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.drawPixmap(0, 0, pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        track = QColor(255, 255, 255, 42)
        painter.setPen(QPen(track, 3))
        painter.drawEllipse(5, 5, size - 10, size - 10)
        base = (int(getattr(self, "avatar_glow_hue", 190)) * 3) % 360
        accent_colors = ["#38bdf8", "#2563eb", "#60a5fa"]
        for i in range(6):
            color = QColor(accent_colors[i % len(accent_colors)])
            color.setAlpha(max(70, 230 - i * 24))
            pen = QPen(color, 4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawArc(5, 5, size - 10, size - 10, int((base - i * 12) * 16), int(16 * 16))
        painter.end()
        self.avatar_label.setPixmap(rounded)

    def init_register_page(self):
        p = QWidget()
        p.setObjectName("LoginCard")
        p.setStyleSheet(self.login_card_style())
        self.auth_pages.append(p)
        l = QVBoxLayout(p)
        l.setContentsMargins(34, 20, 34, 18)
        l.setSpacing(5)
        p.setFixedSize(500, 400)
        
        title = QLabel("Yeni Firma Kaydı")
        title.setObjectName("Title")
        title.setFixedHeight(34)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.addWidget(title)
        l.addSpacing(4)
        
        self.reg_com = QLineEdit(); self.reg_com.setPlaceholderText("Firma / Bayi Adı"); self.reg_com.setFixedHeight(40)
        self.reg_mail = QLineEdit(); self.reg_mail.setPlaceholderText("Kurumsal E-posta"); self.reg_mail.setFixedHeight(40)
        self.reg_p1 = QLineEdit(); self.reg_p1.setPlaceholderText("Şifre"); self.reg_p1.setFixedHeight(40); self.reg_p1.setEchoMode(QLineEdit.EchoMode.Password)
        self.reg_com.returnPressed.connect(self.handle_register)
        self.reg_mail.returnPressed.connect(self.handle_register)
        self.reg_p1.returnPressed.connect(self.handle_register)
        l.addWidget(self.reg_com); l.addWidget(self.reg_mail); l.addWidget(self.reg_p1)

        self.cb_terms = QCheckBox("Kullanıcı Sözleşmesini okudum ve kabul ediyorum")
        self.cb_privacy = QCheckBox("KVKK Aydınlatma Metnini okudum")
        self.cb_cloud = QCheckBox("Bulut ve fotoğraf saklama açık rızasını veriyorum")
        l.addLayout(self.create_agreement_row(self.cb_terms, "terms"))
        l.addLayout(self.create_agreement_row(self.cb_privacy, "privacy"))
        l.addLayout(self.create_agreement_row(self.cb_cloud, "cloud"))
        
        b = QPushButton("Kayıt Ol")
        b.setObjectName("LoginBtn")
        b.setFixedHeight(42)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(self.handle_register)
        l.addWidget(b)
        
        b_back = QPushButton("← Giriş Ekranına Dön")
        b_back.setObjectName("ForgotBtn")
        b_back.setFixedHeight(26)
        b_back.setCursor(Qt.CursorShape.PointingHandCursor)
        b_back.clicked.connect(self.show_login_page)
        l.addWidget(b_back, alignment=Qt.AlignmentFlag.AlignCenter)
        self.auth_stack.addWidget(p)

    def create_agreement_row(self, checkbox, agreement_key):
        row = QHBoxLayout()
        row.setSpacing(8)
        checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        checkbox.setMinimumHeight(28)
        btn = QPushButton("Görüntüle")
        btn.setObjectName("AgreementBtn")
        btn.setFixedSize(76, 28)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: self.show_agreement(agreement_key))
        row.addWidget(checkbox, 1)
        row.addWidget(btn)
        return row

    def show_agreement(self, agreement_key):
        agreement = AGREEMENT_TEXTS.get(agreement_key, {})
        AgreementDialog(agreement.get("title", "Sözleşme"), agreement.get("html", ""), self).exec()

    def agreements_accepted(self):
        return (
            getattr(self, "cb_terms", None) and self.cb_terms.isChecked()
            and getattr(self, "cb_privacy", None) and self.cb_privacy.isChecked()
            and getattr(self, "cb_cloud", None) and self.cb_cloud.isChecked()
        )

    def handle_login(self):
        email = self.login_email.text().strip(); password = self.login_pass.text().strip()
        if not email or not password: self.lbl_status.setText("Lütfen tüm alanları doldurun."); return
        try:
            self.lbl_status.setText("Oturum kontrol ediliyor...")
            QApplication.processEvents()
            
            u = auth.sign_in_with_email_and_password(email, password)
            uid = u['localId']
            token = u['idToken']
            prof = safe_dict_parse(db.child("users").child(uid).child("profil").get(token).val() or {})
            if not isinstance(prof, dict):
                prof = {}
            license_data = read_license_data(db, uid, token, prof)
            license_ok, license_reason, _, _ = check_license_status(license_data, db, uid, token)
            if not license_ok:
                self.lbl_status.setText("")
                self.settings.setValue("auto_login", "false")
                self.auto_login_cb.setChecked(False)
                QMessageBox.warning(self, "Lisans Kontrolü", license_reason)
                return
            
            device_id = get_device_id()
            devices_req = db.child("users").child(uid).child("aktif_cihazlar").get(token).val() or {}
            devices = safe_dict_parse(devices_req)
            if not isinstance(devices, dict):
                devices = {}
            pc_limit = profile_device_limit(
                license_data,
                ["pc_limit", "desktop_limit", "bilgisayar_limit", "max_pc", "pc_cihaz_limiti"],
                2
            )
            
            if device_id not in devices.values():
                if len(devices) >= pc_limit:
                    self.lbl_status.setText("")
                    res = QMessageBox.question(self, "Cihaz Sınırı Uyarı", 
                                             f"Lisansınız aynı anda maksimum {pc_limit} bilgisayarda kullanım içindir.\n\nDiğer tüm bilgisayarların oturumunu kapatıp yetkiyi bu bilgisayara almak ister misiniz?", 
                                             QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
                    if res == QMessageBox.StandardButton.Yes:
                        db.child("users").child(uid).child("aktif_cihazlar").remove(token)
                        db.child("users").child(uid).child("aktif_cihazlar").push(device_id, token)
                    else:
                        self.lbl_status.setText("Cihaz sınırına ulaşıldı.")
                        self.settings.setValue("auto_login", "false"); self.auto_login_cb.setChecked(False)
                        return
                else:
                    db.child("users").child(uid).child("aktif_cihazlar").push(device_id, token)
            
            self.settings.setValue("email", email if self.remember_cb.isChecked() else "")
            self.settings.setValue("password", "")
            self.settings.setValue("password_secure", protect_secret(password) if self.remember_cb.isChecked() else "")
            self.settings.setValue("remember", "true" if self.remember_cb.isChecked() else "false")
            self.settings.setValue("auto_login", "true" if self.auto_login_cb.isChecked() and self.remember_cb.isChecked() else "false")
            self.lbl_status.setText("")
            u["_metafold_profile"] = prof
            u["_metafold_license"] = license_data
            self.manager.login_success(u, email)
        except Exception as e:
            self.settings.setValue("auto_login", "false"); self.auto_login_cb.setChecked(False); self.lbl_status.setText("")
            if "INVALID" in str(e) or "NOT_FOUND" in str(e): QMessageBox.warning(self, "Giriş Başarısız", "E-posta veya şifre hatalı!")
            else: QMessageBox.warning(self, "Sistem Hatası", describe_connection_error(e))

    def handle_register(self):
        if not self.reg_com.text().strip() or not self.reg_mail.text().strip() or not self.reg_p1.text().strip():
            QMessageBox.warning(self, "Hata", "Lütfen bilgileri eksiksiz doldurun.")
            return
        if not self.agreements_accepted():
            QMessageBox.warning(
                self,
                "Sözleşme Onayı Gerekli",
                "Kayıt oluşturmak için kullanıcı sözleşmesini, KVKK aydınlatma metnini ve bulut/fotoğraf açık rızasını onaylamanız gerekir."
            )
            return
        local_trial_uid = str(self.settings.value("trial_registered_uid", "") or "").strip()
        if local_trial_uid:
            QMessageBox.warning(
                self,
                "Deneme Sürümü Kullanıldı",
                "Bu bilgisayarda daha önce deneme hesabı oluşturulmuş. Aynı bilgisayarda tekrar deneme hesabı açılamaz."
            )
            return

        device_key = trial_device_key()
        try:
            existing_trial = safe_dict_parse(db.child("trial_devices").child(device_key).get().val() or {})
            if isinstance(existing_trial, dict) and existing_trial.get("uid"):
                self.settings.setValue("trial_registered_uid", existing_trial.get("uid"))
                QMessageBox.warning(
                    self,
                    "Deneme Sürümü Kullanıldı",
                    "Bu bilgisayarda daha önce deneme hesabı oluşturulmuş. Aynı bilgisayarda tekrar deneme hesabı açılamaz."
                )
                return
        except:
            pass

        try:
            u = auth.create_user_with_email_and_password(self.reg_mail.text(), self.reg_p1.text())
            uid = u['localId']
            token = u['idToken']
            try:
                existing_trial = safe_dict_parse(db.child("trial_devices").child(device_key).get(token).val() or {})
                if isinstance(existing_trial, dict) and existing_trial.get("uid") and existing_trial.get("uid") != uid:
                    try:
                        auth.delete_user_account(token)
                    except:
                        pass
                    self.settings.setValue("trial_registered_uid", existing_trial.get("uid"))
                    QMessageBox.warning(
                        self,
                        "Deneme Sürümü Kullanıldı",
                        "Bu bilgisayarda daha önce deneme hesabı oluşturulmuş. Aynı bilgisayarda tekrar deneme hesabı açılamaz."
                    )
                    return
            except:
                pass
            now_text = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
            now_dt = datetime.datetime.now()
            expiry_dt = now_dt + datetime.timedelta(days=30)
            expiry_text = expiry_dt.strftime("%d.%m.%Y")
            license_payload = {
                "owner_uid": uid,
                "active": True,
                "lisans_bitis": expiry_text,
                "lisans_olusturma": now_text,
                "lisans_tipi": "deneme",
                "pc_limit": 2,
                "mobile_limit": 2,
                "paket_adi": "2 PC + 2 Mobil",
                "trial_device_key": device_key,
                "trial_days": 30,
                "created_at_ms": int(now_dt.timestamp() * 1000),
                "expires_at_ms": int(expiry_dt.timestamp() * 1000),
                "created_by": "client_trial"
            }
            consent_data = {
                "sozlesme_surumu": AGREEMENTS_VERSION,
                "uygulama_surumu": str(MEVCUT_SURUM),
                "kabul_tarihi": now_text,
                "eposta": self.reg_mail.text().strip(),
                "firma": self.reg_com.text().strip(),
                "kullanici_sozlesmesi": True,
                "kvkk_aydinlatma": True,
                "bulut_fotograf_acik_riza": True,
            }
            profile_payload = {
                "firma_adi": self.reg_com.text().strip(),
                "eposta": self.reg_mail.text(),
                "sozlesme_surumu": AGREEMENTS_VERSION,
                "sozlesme_onay_tarihi": now_text
            }
            db.child("users").child(u['localId']).child("profil").set(profile_payload, token)
            try:
                db.child("licenses").child(uid).set(license_payload, token)
            except Exception:
                legacy_profile_payload = dict(profile_payload)
                legacy_profile_payload.update(license_payload)
                db.child("users").child(u['localId']).child("profil").set(legacy_profile_payload, token)
            db.child("users").child(u['localId']).child("onaylar").child(AGREEMENTS_VERSION.replace(".", "_")).set(consent_data, token)
            db.child("users").child(u['localId']).child("onaylar").child("son").set(consent_data, token)
            try:
                db.child("trial_devices").child(device_key).set({
                    "uid": uid,
                    "email": self.reg_mail.text(),
                    "firma": self.reg_com.text().strip(),
                    "created_at": now_text
                }, token)
            except:
                pass
            self.settings.setValue("trial_registered_uid", uid)
            QMessageBox.information(self, "Başarılı", "Firma kaydı başarıyla tamamlandı!"); self.auth_stack.setCurrentIndex(0)
        except Exception as e: QMessageBox.warning(self, "Kayıt Hatası", str(e))
