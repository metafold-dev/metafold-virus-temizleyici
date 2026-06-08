# -*- coding: utf-8 -*-
import pyrebase
import requests
import os
import sys
import datetime

MEVCUT_SURUM = 11.2
NETLIFY_URL = "https://wondrous-twilight-be4910.netlify.app"
IMGBB_API_KEY = "7626e8c1a051205ee2cc3135e7aff05e"

if os.name == 'nt':
    import ctypes
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('metafold.teknik.servis.11.2')
    except: pass

def resource_path(relative_path):
    try: return os.path.join(sys._MEIPASS, relative_path)
    except Exception: return os.path.join(os.path.abspath("."), relative_path)

def safe_float(val, default=0.0):
    try:
        if isinstance(val, (int, float)): return float(val)
        if isinstance(val, str):
            v = val.replace("₺", "").replace("TL", "").replace("$", "").replace(" ", "").strip()
            if not v: return default
            if "," in v and "." in v: v = v.replace(".", "").replace(",", ".")
            elif "," in v: v = v.replace(",", ".")
            elif "." in v:
                parts = v.split(".")
                if len(parts[-1]) == 3: v = v.replace(".", "")
            return float(v)
        return default
    except: return default

def format_money(val, symbol=""):
    try:
        f_val = float(safe_float(val))
        formatted = f"{f_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted} {symbol}".strip()
    except: return f"0,00 {symbol}".strip()

def format_public_money(val, symbol="TL"):
    try:
        f_val = float(safe_float(val))
        has_cents = abs(f_val - round(f_val)) > 0.004
        if has_cents:
            formatted = f"{f_val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            formatted = f"{int(round(f_val)):,}".replace(",", ".")
        return f"{formatted} {symbol}".strip()
    except:
        return f"0 {symbol}".strip()

def get_photo_url(data):
    if not isinstance(data, dict): return ""
    photos = data.get("photos", {})
    if isinstance(photos, dict):
        for item in photos.values():
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item.get("url").startswith("http"):
                return item.get("url")
            if isinstance(item, str) and item.startswith("http"):
                return item
    elif isinstance(photos, list):
        for item in photos:
            if isinstance(item, dict) and isinstance(item.get("url"), str) and item.get("url").startswith("http"):
                return item.get("url")
            if isinstance(item, str) and item.startswith("http"):
                return item
    keys = ["photo_url", "foto_url", "resim_url", "fotograf", "foto", "resim", "image_url", "url", "link", "photo"]
    for key in keys:
        val = data.get(key)
        if val and isinstance(val, str) and val.startswith("http"): return val
    for k, v in data.items():
        if isinstance(v, str) and v.startswith("http") and ("ibb.co" in v or "imgbb" in v or "firebasestorage" in v): return v
        if isinstance(v, dict):
            for sk, sv in v.items():
                if isinstance(sv, str) and sv.startswith("http"): return sv
    return ""

def safe_dict_parse(raw_data):
    if not raw_data: return {}
    if isinstance(raw_data, list):
        return {str(i): v for i, v in enumerate(raw_data) if v is not None}
    return raw_data

def describe_connection_error(error):
    text = str(error)
    status_code = getattr(getattr(error, "response", None), "status_code", None)
    if status_code == 402 or "402 Client Error" in text or "Payment Required" in text:
        return (
            "Firebase bağlantısı ödeme/kota doğrulaması nedeniyle reddedildi.\n\n"
            "Firebase Console > Usage and billing ekranını, Google Cloud Billing durumunu "
            "ve projenin Realtime Database ayarlarını kontrol edin. Sorun geçiciyse programdan "
            "çıkıp tekrar giriş yapın."
        )
    if status_code in [401, 403] or "Permission denied" in text or "Unauthorized" in text:
        return (
            "Firebase yetkilendirme hatası oluştu.\n\n"
            "Oturum süresi dolmuş olabilir. Programdan çıkıp tekrar giriş yapın. "
            "Devam ederse Realtime Database kurallarını kontrol edin."
        )
    if "Connection" in text or "timeout" in text.lower() or "Max retries" in text:
        return "Sunucu bağlantısı kurulamadı. İnternet bağlantısını kontrol edip tekrar deneyin."
    return f"Bağlantı veya sunucu hatası:\n{text}"

def get_secure_now(db=None, user_id=None, token=None):
    """Firebase sunucu zamanını kullanır; alınamazsa yerel zamana düşer."""
    try:
        if db is not None and user_id and token:
            ref = db.child("users").child(user_id).child("_license_time_check")
            ref.update({"now": {".sv": "timestamp"}}, token)
            val = ref.child("now").get(token).val()
            ref.remove(token)
            if isinstance(val, (int, float)):
                return datetime.datetime.fromtimestamp(float(val) / 1000.0)
    except:
        pass
    return datetime.datetime.now()

def read_license_data(db=None, user_id=None, token=None, profile=None):
    """Read the server-controlled license node first; fall back to legacy profile fields."""
    legacy_profile = safe_dict_parse(profile or {})
    if not isinstance(legacy_profile, dict):
        legacy_profile = {}
    try:
        if db is not None and user_id and token:
            license_data = safe_dict_parse(db.child("licenses").child(user_id).get(token).val() or {})
            if isinstance(license_data, dict) and license_data:
                merged = dict(legacy_profile)
                merged.update(license_data)
                return merged
    except:
        pass
    return legacy_profile

def check_license_status(profile, db=None, user_id=None, token=None):
    if not isinstance(profile, dict):
        return False, "Lisans profili doğrulanamadı. Lütfen destek ile iletişime geçin.", "", -1

    active_value = profile.get("active", True)
    if str(active_value).strip().lower() in ["false", "0", "pasif", "disabled", "blocked", "iptal"]:
        return False, "Lisans hesabı pasif durumda. Lütfen destek ile iletişime geçin.", "", -1

    status_value = str(profile.get("status", "") or "").strip().lower()
    if status_value in ["pasif", "disabled", "blocked", "iptal", "inactive"]:
        return False, "Lisans hesabı pasif durumda. Lütfen destek ile iletişime geçin.", "", -1

    expiry_text = str(profile.get("lisans_bitis", "")).strip()
    if expiry_text in ["Süresiz", "SÃ¼resiz", "Suresiz", "SINIRSIZ", "LIFETIME"]:
        return True, "", expiry_text, 9999

    expires_at_ms = profile.get("expires_at_ms", profile.get("expiresAtMs", ""))
    if expires_at_ms not in [None, ""]:
        try:
            expiry_date = datetime.datetime.fromtimestamp(float(expires_at_ms) / 1000.0).date()
            expiry_text = expiry_text or expiry_date.strftime("%d.%m.%Y")
            now_date = get_secure_now(db, user_id, token).date()
            remaining = (expiry_date - now_date).days
            if remaining < 0:
                return False, "Lisans süreniz dolduğu için program açılamaz. Lütfen lisansınızı yenileyin.", expiry_text, remaining
            return True, "", expiry_text, remaining
        except:
            return False, "Lisans tarihi doğrulanamadı. Lütfen destek ile iletişime geçin.", expiry_text, -1

    if not expiry_text:
        return False, "Lisans tarihi bulunamadı. Lütfen lisansınızı yenileyin veya destek ile iletişime geçin.", "", -1

    try:
        expiry_date = datetime.datetime.strptime(expiry_text, "%d.%m.%Y").date()
    except:
        return False, "Lisans tarihi doğrulanamadı. Lütfen destek ile iletişime geçin.", expiry_text, -1

    now_date = get_secure_now(db, user_id, token).date()
    remaining = (expiry_date - now_date).days
    if remaining < 0:
        return False, "Lisans süreniz dolduğu için program açılamaz. Lütfen lisansınızı yenileyin.", expiry_text, remaining
    return True, "", expiry_text, remaining

def get_firebase_config():
    return {
        "apiKey": "AIzaSyD43dPyY9sIYN52tTpZIIzLFU4g2q3bqhM",
        "authDomain": "metafold-teknik-servis.firebaseapp.com",
        "databaseURL": "https://metafold-teknik-servis-default-rtdb.europe-west1.firebasedatabase.app",
        "projectId": "metafold-teknik-servis",
        "storageBucket": "metafold-teknik-servis.appspot.com", 
        "messagingSenderId": "818658668337",
        "appId": "1:818658668337:web:99b468149a24bfd0fa8a10"
    }

DARK_THEME = """
    QMainWindow, QDialog, QStackedWidget { background-color: #202124; color: #f3f6fb; font-family: "Segoe UI"; }
    QWidget { color: #f3f6fb; font-family: "Segoe UI"; }
    QLabel, QCheckBox, QRadioButton, QGroupBox { color: #f3f6fb; }
    QTabWidget::pane { border: 1px solid #3a3d44; border-radius: 8px; background: #25272c; top: -1px; }
    QTabBar::tab { background: transparent; color: #b9c0cb; padding: 10px 14px; margin: 2px; border-radius: 7px; font-weight: 600; }
    QTabBar::tab:hover { background: #30333a; color: #ffffff; }
    QTabBar::tab:selected { background: #313844; color: #ffffff; border-bottom: 2px solid #60a5fa; }
    QPushButton { background-color: #2563eb; color: white; border-radius: 7px; padding: 9px 13px; font-weight: 600; border: 1px solid #2f6feb; }
    QPushButton:hover { background-color: #1d4ed8; border-color: #3b82f6; }
    QPushButton:pressed { background-color: #1e40af; }
    QPushButton:disabled { background-color: #3a3d44; color: #8f98a8; border-color: #3a3d44; }
    QPushButton#SecondaryBtn { background-color: transparent; color: #93c5fd; border: none; padding: 6px; }
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QListWidget { background-color: #2b2e35; color: #f8fafc; border: 1px solid #454a54; border-radius: 7px; padding: 9px 11px; outline: 0; selection-background-color: #2563eb; }
    QLineEdit:hover, QTextEdit:hover, QComboBox:hover, QDateEdit:hover, QListWidget:hover { border-color: #5b6472; }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus { border: 2px solid #60a5fa; padding: 8px 10px; background-color: #30343c; }
    QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 26px; }
    QComboBox QAbstractItemView { background-color: #2b2e35; color: #f8fafc; border: 1px solid #454a54; selection-background-color: #2563eb; selection-color: white; outline: none; padding: 4px; }
    QTableWidget { background-color: #24272d; alternate-background-color: #2a2e35; color: #f3f6fb; gridline-color: #373b44; border: 1px solid #3a3d44; border-radius: 8px; outline: 0; selection-background-color: #1d4ed8; selection-color: white; }
    QTableWidget::item { padding: 6px; border: none; }
    QTableWidget::item:hover { background-color: #303844; }
    QHeaderView { background-color: #27313d; }
    QHeaderView::section { background-color: #2d3745; color: #f8fafc; padding: 9px; border: none; border-right: 1px solid #4b5563; border-bottom: 1px solid #60a5fa; font-weight: 800; }
    QHeaderView::section:first { border-top-left-radius: 7px; }
    QHeaderView::section:last { border-top-right-radius: 7px; border-right: none; }
    QTableCornerButton::section { background-color: #2d3745; border: none; border-right: 1px solid #4b5563; border-bottom: 1px solid #60a5fa; }
    QMenu { background-color: #2b2e35; color: #f8fafc; border: 1px solid #484d58; border-radius: 8px; padding: 6px; }
    QMenu::item { padding: 8px 22px 8px 12px; border-radius: 6px; }
    QMenu::item:selected { background-color: #2563eb; color: white; }
    QGroupBox { background-color: #25272c; border: 1px solid #3a3d44; border-radius: 8px; margin-top: 14px; padding-top: 12px; font-weight: 700; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #dce3ee; background-color: #202124; }
    QListWidget::item { padding: 7px; border-radius: 6px; }
    QListWidget::item:hover { background-color: #303844; }
    QListWidget::item:selected { background-color: #2563eb; color: white; }
    QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px; border: 1px solid #647084; background-color: #2b2e35; }
    QCheckBox::indicator:checked { background-color: #2563eb; border: 1px solid #2563eb; }
    #DialogFrame { background-color: #25272c; border-radius: 10px; border: 1px solid #424753; }
"""

LIGHT_THEME = """
    QMainWindow, QDialog, QStackedWidget { background-color: #f3f6fb; color: #172033; font-family: "Segoe UI"; }
    QWidget { color: #172033; font-family: "Segoe UI"; }
    QLabel, QCheckBox, QRadioButton, QGroupBox { color: #172033; }
    QTabWidget::pane { border: 1px solid #d8e0eb; border-radius: 8px; background: rgba(255, 255, 255, 0.72); top: -1px; }
    QTabBar::tab { background: transparent; color: #526174; padding: 10px 14px; margin: 2px; border-radius: 7px; font-weight: 600; }
    QTabBar::tab:hover { background: #edf3fa; color: #172033; }
    QTabBar::tab:selected { background: #ffffff; color: #172033; border-bottom: 2px solid #2563eb; }
    QPushButton { background-color: #2563eb; color: white; border-radius: 7px; padding: 9px 13px; font-weight: 600; border: 1px solid #2563eb; }
    QPushButton:hover { background-color: #1d4ed8; border-color: #1d4ed8; }
    QPushButton:pressed { background-color: #1e40af; }
    QPushButton:disabled { background-color: #e4e9f1; color: #98a3b3; border-color: #e4e9f1; }
    QPushButton#SecondaryBtn { background-color: transparent; color: #2563eb; border: none; padding: 6px; }
    QLineEdit, QTextEdit, QComboBox, QDateEdit, QListWidget { background-color: rgba(255,255,255,0.92); color: #172033; border: 1px solid #c9d6e4; border-radius: 7px; padding: 9px 11px; outline: 0; selection-background-color: #2563eb; selection-color: white; }
    QLineEdit:hover, QTextEdit:hover, QComboBox:hover, QDateEdit:hover, QListWidget:hover { border-color: #aabbd0; background-color: #ffffff; }
    QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus { border: 2px solid #2563eb; padding: 8px 10px; background-color: #ffffff; }
    QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 26px; }
    QComboBox QAbstractItemView { background-color: #ffffff; color: #172033; border: 1px solid #c9d6e4; selection-background-color: #2563eb; selection-color: white; outline: none; padding: 4px; }
    QTableWidget { background-color: rgba(255,255,255,0.88); alternate-background-color: #f6f9fd; color: #172033; gridline-color: #e1e8f1; border: 1px solid #d8e0eb; border-radius: 8px; outline: 0; selection-background-color: #dbeafe; selection-color: #172033; }
    QTableWidget::item { padding: 6px; border: none; }
    QTableWidget::item:hover { background-color: #edf3fa; }
    QHeaderView { background-color: #e7eef7; }
    QHeaderView::section { background-color: #dbeafe; color: #1e3a5f; padding: 9px; border: none; border-right: 1px solid #b6c8dd; border-bottom: 1px solid #2563eb; font-weight: 800; }
    QHeaderView::section:first { border-top-left-radius: 7px; }
    QHeaderView::section:last { border-top-right-radius: 7px; border-right: none; }
    QTableCornerButton::section { background-color: #dbeafe; border: none; border-right: 1px solid #b6c8dd; border-bottom: 1px solid #2563eb; }
    QMenu { background-color: #ffffff; color: #172033; border: 1px solid #d8e0eb; border-radius: 8px; padding: 6px; }
    QMenu::item { padding: 8px 22px 8px 12px; border-radius: 6px; }
    QMenu::item:selected { background-color: #2563eb; color: white; }
    QGroupBox { background-color: rgba(255,255,255,0.74); border: 1px solid #d8e0eb; border-radius: 8px; margin-top: 14px; padding-top: 12px; font-weight: 700; }
    QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; color: #44546a; background-color: #f3f6fb; }
    QListWidget::item { padding: 7px; border-radius: 6px; }
    QListWidget::item:hover { background-color: #edf3fa; }
    QListWidget::item:selected { background-color: #2563eb; color: white; }
    QCheckBox::indicator { width: 17px; height: 17px; border-radius: 4px; border: 1px solid #9eb0c4; background-color: rgba(255,255,255,0.88); }
    QCheckBox::indicator:checked { background-color: #2563eb; border: 1px solid #2563eb; }
    #DialogFrame { background-color: #ffffff; border-radius: 10px; border: 1px solid #d8e0eb; }
"""

def get_theme_stylesheet(theme_name):
    theme = str(theme_name or "Dark")
    if "Light" in theme or "Açık" in theme:
        return LIGHT_THEME
    if "Ocean" in theme or "Okyanus" in theme:
        return DARK_THEME.replace("#2563eb", "#0891b2").replace("#1d4ed8", "#0e7490").replace("#60a5fa", "#67e8f9") + """
            QMainWindow, QDialog, QStackedWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #071923, stop:0.55 #0b2433, stop:1 #12394b); }
            QWidget { color: #e6fbff; }
            QTabWidget::pane { background-color: rgba(5, 22, 31, 0.92); border: 1px solid #155e75; }
            QTabBar::tab:selected { background-color: #0e7490; border-bottom: 2px solid #67e8f9; color: white; }
            QTabBar::tab:hover { background-color: #164e63; }
            QTableWidget, QListWidget { background-color: rgba(8, 29, 42, 0.94); alternate-background-color: #0f2f43; border-color: #155e75; }
            QHeaderView { background-color: #0f3a4d; }
            QHeaderView::section { background-color: #0f3a4d; color: #ecfeff; border-right: 1px solid #176b82; border-bottom: 1px solid #67e8f9; font-weight: 800; }
            QTableCornerButton::section { background-color: #0f3a4d; border-right: 1px solid #176b82; border-bottom: 1px solid #67e8f9; }
            QLineEdit, QTextEdit, QComboBox, QDateEdit { background-color: #082333; border-color: #176b82; color: #ecfeff; }
            QGroupBox, #DialogFrame { background-color: rgba(8, 29, 42, 0.88); border-color: #155e75; }
        """
    if "Emerald" in theme or "Zümrüt" in theme:
        return LIGHT_THEME.replace("#2563eb", "#059669").replace("#1d4ed8", "#047857").replace("#60a5fa", "#34d399") + """
            QMainWindow, QDialog, QStackedWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #eefcf6, stop:0.48 #d9f7ea, stop:1 #b7ead5); color: #0f2d22; }
            QWidget, QLabel, QCheckBox, QRadioButton, QGroupBox { color: #0f2d22; }
            QTabWidget::pane { background-color: rgba(255,255,255,0.76); border: 1px solid #a7d8c4; }
            QTabBar::tab:selected { background-color: #ffffff; border-bottom: 3px solid #059669; color: #0f2d22; }
            QTabBar::tab:hover { background-color: #e6f7ef; }
            QTableWidget, QListWidget { background-color: rgba(255,255,255,0.92); alternate-background-color: #effaf5; border-color: #b7dfcf; }
            QHeaderView { background-color: #dff6eb; }
            QHeaderView::section { background-color: #c7f2df; color: #064e3b; border-right: 1px solid #9bd5be; border-bottom: 1px solid #059669; font-weight: 800; }
            QTableCornerButton::section { background-color: #c7f2df; border-right: 1px solid #9bd5be; border-bottom: 1px solid #059669; }
            QLineEdit, QTextEdit, QComboBox, QDateEdit { background-color: #ffffff; border-color: #a7d8c4; color: #0f2d22; }
            QGroupBox, #DialogFrame { background-color: rgba(255,255,255,0.82); border-color: #a7d8c4; }
        """
    if "Graphite" in theme or "Grafit" in theme:
        return DARK_THEME.replace("#2563eb", "#f59e0b").replace("#1d4ed8", "#d97706").replace("#60a5fa", "#fbbf24") + """
            QMainWindow, QDialog, QStackedWidget { background-color: #111113; color: #f4f4f5; }
            QWidget { color: #f4f4f5; }
            QTabWidget::pane { background-color: #18181b; border: 1px solid #3f3f46; }
            QTabBar::tab { color: #a1a1aa; }
            QTabBar::tab:selected { background-color: #27272a; border-bottom: 2px solid #f59e0b; color: #ffffff; }
            QTabBar::tab:hover { background-color: #202024; color: #ffffff; }
            QTableWidget, QListWidget { background-color: #18181b; alternate-background-color: #202024; border-color: #3f3f46; }
            QHeaderView { background-color: #27272a; }
            QHeaderView::section { background-color: #2f2f34; color: #fef3c7; border-right: 1px solid #52525b; border-bottom: 1px solid #f59e0b; font-weight: 800; }
            QTableCornerButton::section { background-color: #2f2f34; border-right: 1px solid #52525b; border-bottom: 1px solid #f59e0b; }
            QLineEdit, QTextEdit, QComboBox, QDateEdit { background-color: #18181b; border-color: #3f3f46; color: #f4f4f5; }
            QGroupBox, #DialogFrame { background-color: #18181b; border-color: #3f3f46; }
        """
    return DARK_THEME

def get_device_id():
    """Bilgisayarın benzersiz donanım kimliğini döndürür (Lisanslama için)"""
    import uuid
    if os.name == "nt":
        try:
            windll_getnode = getattr(uuid, "_windll_getnode", None)
            if windll_getnode:
                node = windll_getnode()
                if isinstance(node, int) and 0 <= node < (1 << 48):
                    return str(node)
        except Exception:
            pass
        try:
            import hashlib
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
                machine_guid = str(winreg.QueryValueEx(key, "MachineGuid")[0]).strip()
            if machine_guid:
                return hashlib.sha256(f"metafold:{machine_guid}".encode("utf-8")).hexdigest()[:24]
        except Exception:
            pass
    return str(uuid.getnode())
