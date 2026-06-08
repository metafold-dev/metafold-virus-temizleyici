# -*- coding: utf-8 -*-
import os
import sys
import json
import random
import base64
import tempfile
import csv
import io
import html
import re
import requests
import webbrowser
import urllib.parse
import datetime
import time
import zipfile
import subprocess
import uuid
import hashlib
import shutil
import socket
import unicodedata

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, 
                             QLabel, QPushButton, QLineEdit, QTextEdit, QTableWidget, QTableWidgetItem, 
                             QComboBox, QHeaderView, QGraphicsOpacityEffect, QMessageBox, QMenu, 
                             QInputDialog, QDialog, QDialogButtonBox, QStackedWidget, QCheckBox, 
                             QCompleter, QFileDialog, QGridLayout, QGroupBox, QListWidget, QSizePolicy, QDateEdit, QListWidgetItem,
                             QScrollArea, QFrame, QAbstractItemView, QStyledItemDelegate, QStyle, QListView,
                             QCalendarWidget)
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, QSettings, QStringListModel, QPoint, QDate, QSize, QSizeF, QMarginsF, QEvent, QEasingCurve, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QCursor, QPixmap, QMovie, QTextDocument, QIcon, QPainter, QPen, QPageSize, QPageLayout, QRegion, QShortcut, QKeySequence
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog

from config import (MEVCUT_SURUM, resource_path, get_theme_stylesheet,
                    safe_float, format_money, format_public_money, safe_dict_parse, NETLIFY_URL, get_photo_url,
                    check_license_status, describe_connection_error, get_firebase_config, read_license_data)
from database.threads import auth, db, FetchRatesThread
from gui.adb_cleaner import AdbCleanerWidget
from gui.dialogs import CustomEditDialog, InfoDialog, PhotoDialog, PatternLock, PartDialog, ReadOnlyDialog, ViewImageDialog, ViewPatternDialog, get_record_photos

SUPPORT_RESTORE_PASSWORD_HASH = "fc5928b509767acc5c05d5cc8745e249d9ba388c21f8d63de752443e653164c6"
LOCAL_CACHE_SCHEMA_VERSION = 1
LOCAL_CACHE_AGGREGATE_FILE = "data_cache.json"
LOCAL_CACHE_SECTIONS = {
    "kayitlar",
    "sabit_bayiler",
    "kasa",
    "stok",
    "cop_kutusu",
    "firmalar",
    "toptanci",
    "toptanci_odemeler",
}
LOCAL_CACHE_AUTO_REFRESH_MS = 10 * 60 * 1000
LOCAL_CACHE_CLOUD_REFRESH_SECONDS = 30 * 60
LOCAL_CACHE_RECENT_RECORD_LIMIT = 300
LOCAL_CACHE_CHANGED_RECORD_LIMIT = 500
LOCAL_CACHE_SYNC_LOOKBACK_MS = 5 * 60 * 1000
DOWNLOAD_USAGE_FILE = "download_usage.json"

def estimate_json_bytes(value):
    if value is None:
        return 0
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
    except Exception:
        try:
            return len(str(value).encode("utf-8"))
        except Exception:
            return 0

def subprocess_no_console_flags():
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)

class SuggestionDeleteDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(option.rect, QColor("#1d4ed8" if selected else "#111827"))
        text_rect = option.rect.adjusted(12, 0, -48, 0)
        icon_rect = option.rect.adjusted(option.rect.width() - 38, 5, -10, -5)
        painter.setPen(QColor("#f8fafc"))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, str(index.data() or ""))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#dc2626" if selected else "#3b1118"))
        painter.drawRoundedRect(icon_rect, 7, 7)
        painter.setPen(QColor("#ffffff" if selected else "#fca5a5"))
        painter.drawText(icon_rect, Qt.AlignmentFlag.AlignCenter, "✕")
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(260, 30)

class ImagePreviewDialog(QDialog):
    def __init__(self, title, pixmap, subtitle="", parent=None, initial_zoom=1.0):
        super().__init__(parent)
        self.original_pixmap = QPixmap(pixmap)
        self.zoom = max(0.25, min(float(initial_zoom or 1.0), 5.0))
        self.setWindowTitle(title)
        self.resize(820, 760)
        self.setMinimumSize(520, 420)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        top = QHBoxLayout()
        title_lbl = QLabel(f"<b>{title}</b>")
        title_lbl.setStyleSheet("font-size:16px; color:#f8fafc;")
        self.zoom_lbl = QLabel()
        self.zoom_lbl.setStyleSheet("color:#cbd5e1; font-weight:700; min-width:58px;")
        top.addWidget(title_lbl)
        if subtitle:
            sub_lbl = QLabel(subtitle)
            sub_lbl.setStyleSheet("color:#94a3b8;")
            top.addWidget(sub_lbl)
        top.addStretch()

        btn_zoom_out = QPushButton("-")
        btn_zoom_in = QPushButton("+")
        btn_fit = QPushButton("Sığdır")
        btn_100 = QPushButton("100%")
        self.btn_full = QPushButton("Tam Ekran")
        btn_close = QPushButton("Kapat")
        for btn in [btn_zoom_out, btn_zoom_in, btn_fit, btn_100, self.btn_full, btn_close]:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(32)
        for btn in [btn_zoom_out, btn_zoom_in]:
            btn.setFixedWidth(38)
        top.addWidget(btn_zoom_out)
        top.addWidget(btn_zoom_in)
        top.addWidget(btn_fit)
        top.addWidget(btn_100)
        top.addWidget(self.zoom_lbl)
        top.addWidget(self.btn_full)
        top.addWidget(btn_close)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background:#ffffff; border:1px solid #cbd5e1;")

        self.scroll = QScrollArea()
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.image_label)
        self.scroll.setStyleSheet("""
            QScrollArea { background:#0f172a; border:1px solid #334155; border-radius:8px; }
            QScrollBar:vertical, QScrollBar:horizontal { background:#111827; width:12px; height:12px; }
            QScrollBar::handle { background:#475569; border-radius:6px; min-height:24px; min-width:24px; }
            QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
        """)

        root.addLayout(top)
        root.addWidget(self.scroll, 1)
        self.setStyleSheet("""
            QDialog { background:#111827; }
            QPushButton {
                background:#2563eb; color:white; border:none; border-radius:6px;
                padding:6px 12px; font-weight:700;
            }
            QPushButton:hover { background:#1d4ed8; }
            QPushButton:pressed { background:#1e40af; }
        """)

        btn_zoom_in.clicked.connect(lambda: self.set_zoom(self.zoom * 1.25))
        btn_zoom_out.clicked.connect(lambda: self.set_zoom(self.zoom / 1.25))
        btn_100.clicked.connect(lambda: self.set_zoom(1.0))
        btn_fit.clicked.connect(self.fit_to_window)
        self.btn_full.clicked.connect(self.toggle_fullscreen)
        btn_close.clicked.connect(self.accept)

        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(lambda: self.set_zoom(self.zoom * 1.25))
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(lambda: self.set_zoom(self.zoom * 1.25))
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(lambda: self.set_zoom(self.zoom / 1.25))
        QShortcut(QKeySequence("Ctrl+0"), self).activated.connect(lambda: self.set_zoom(1.0))
        QShortcut(QKeySequence("F11"), self).activated.connect(self.toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.accept)
        self.apply_zoom()

    def apply_zoom(self):
        if self.original_pixmap.isNull():
            return
        size = QSize(
            max(1, int(self.original_pixmap.width() * self.zoom)),
            max(1, int(self.original_pixmap.height() * self.zoom)),
        )
        scaled = self.original_pixmap.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.zoom_lbl.setText(f"{int(self.zoom * 100)}%")

    def set_zoom(self, value):
        self.zoom = max(0.25, min(float(value), 5.0))
        self.apply_zoom()

    def fit_to_window(self):
        if self.original_pixmap.isNull():
            return
        viewport = self.scroll.viewport().size()
        scale_w = max(0.25, (viewport.width() - 24) / max(1, self.original_pixmap.width()))
        scale_h = max(0.25, (viewport.height() - 24) / max(1, self.original_pixmap.height()))
        self.set_zoom(min(scale_w, scale_h, 5.0))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.btn_full.setText("Tam Ekran")
        else:
            self.showFullScreen()
            self.btn_full.setText("Pencereye Dön")

class ConnectionCheckWorker(QThread):
    result = pyqtSignal(bool)

    def __init__(self, host, timeout=0.8):
        super().__init__()
        self.host = host
        self.timeout = timeout

    def run(self):
        try:
            with socket.create_connection((self.host, 443), timeout=float(self.timeout or 0.8)):
                self.result.emit(True)
        except Exception:
            self.result.emit(False)


class FirebaseRecordStreamWorker(QThread):
    stream_event = pyqtSignal(dict)
    stream_status = pyqtSignal(str, bool)

    def __init__(self, user_id, token, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.token = token
        self.stream = None
        self.running = True
        self._initial_snapshot_seen = False

    def run(self):
        while self.running:
            try:
                self._initial_snapshot_seen = False
                self.stream_status.emit("Kayıt dinleyici bağlanıyor", True)
                self.stream = db.child("users").child(self.user_id).child("sync_meta").child("kayitlar").child("latest").stream(
                    self.stream_handler,
                    token=self.token,
                )
                while self.running:
                    self.msleep(1000)
            except Exception as exc:
                if not self.running:
                    break
                self.stream_status.emit(str(exc), False)
                self.msleep(10000)
            finally:
                try:
                    if self.stream:
                        self.stream.close()
                except Exception:
                    pass
                self.stream = None

    def stream_handler(self, message):
        if not self.running or not isinstance(message, dict):
            return
        event = str(message.get("event", "") or "")
        path = str(message.get("path", "/") or "/")
        data = message.get("data")

        # .stream() ilk bağlandığında path'in mevcut halini yollar. İlk veri zaten get()
        # ile alındığı için bu büyük ilk paketi UI'da tekrar işlemiyoruz.
        if False and not self._initial_snapshot_seen and event == "put" and path == "/":
            self._initial_snapshot_seen = True
            self.stream_status.emit("Kayıt dinleyici aktif", True)
            return

        self._initial_snapshot_seen = True
        if event == "put" and path == "/" and data is None:
            self.stream_status.emit("Kayit dinleyici aktif", True)
            return
        if event in ("put", "patch"):
            self.stream_event.emit({
                "event": event,
                "path": path,
                "data": data,
            })

    def stop(self):
        self.running = False
        try:
            if self.stream:
                self.stream.close()
        except Exception:
            pass


class FirebaseDeltaFetchWorker(QThread):
    delta_fetched = pyqtSignal(dict)

    def __init__(self, user_id, token, since_ms, latest_meta, parent=None):
        super().__init__(parent)
        self.user_id = user_id
        self.token = token
        self.since_ms = int(safe_float(since_ms, 0))
        self.latest_meta = latest_meta if isinstance(latest_meta, dict) else {}

    def meta_ms(self, value):
        try:
            return int(safe_float(value, 0))
        except Exception:
            return 0

    def run(self):
        result = {
            "ok": False,
            "records": {},
            "deleted": [],
            "latest_ms": self.meta_ms(self.latest_meta.get("last_changed_at_ms")),
            "download_bytes": 0,
            "error": "",
        }
        try:
            latest_id = str(self.latest_meta.get("last_changed_id", "") or "")
            latest_action = str(self.latest_meta.get("last_action", "upsert") or "upsert")
            latest_ms = self.meta_ms(self.latest_meta.get("last_changed_at_ms"))
            latest_only = bool(self.latest_meta.get("latest_only"))
            force_latest = bool(self.latest_meta.get("force_latest"))
            records_ref = db.child("users").child(self.user_id).child("kayitlar")

            if latest_only:
                if latest_id:
                    if latest_action == "delete":
                        result["deleted"] = [latest_id]
                    else:
                        record = records_ref.child(latest_id).get(self.token).val()
                        result["download_bytes"] += estimate_json_bytes(record)
                        if isinstance(record, dict):
                            result["records"][latest_id] = record
                        else:
                            result["deleted"] = [latest_id]
                result["ok"] = True
                self.delta_fetched.emit(result)
                return

            meta_ref = db.child("users").child(self.user_id).child("sync_meta").child("kayitlar")
            changed_raw = meta_ref.child("changed_ids").get(self.token).val() or {}
            deleted_raw = meta_ref.child("deleted_ids").get(self.token).val() or {}
            result["download_bytes"] += estimate_json_bytes(changed_raw) + estimate_json_bytes(deleted_raw)
            changed_map = safe_dict_parse(changed_raw)
            deleted_map = safe_dict_parse(deleted_raw)
            if not isinstance(changed_map, dict):
                changed_map = {}
            if not isinstance(deleted_map, dict):
                deleted_map = {}

            changed_ids = {}
            deleted_ids = {}
            for kid, changed_ms in changed_map.items():
                ms = self.meta_ms(changed_ms)
                if ms > self.since_ms:
                    changed_ids[str(kid)] = ms
            for kid, deleted_ms in deleted_map.items():
                ms = self.meta_ms(deleted_ms)
                if ms > self.since_ms:
                    deleted_ids[str(kid)] = ms

            if latest_id and (latest_ms > self.since_ms or force_latest):
                if latest_action == "delete":
                    deleted_ids[latest_id] = latest_ms
                else:
                    changed_ids[latest_id] = latest_ms

            for kid in list(deleted_ids.keys()):
                changed_ids.pop(kid, None)

            for kid, changed_ms in sorted(changed_ids.items(), key=lambda item: item[1]):
                record = records_ref.child(kid).get(self.token).val()
                result["download_bytes"] += estimate_json_bytes(record)
                if isinstance(record, dict):
                    result["records"][kid] = record
                else:
                    deleted_ids[kid] = max(deleted_ids.get(kid, 0), changed_ms)

            result["deleted"] = sorted(deleted_ids, key=lambda kid: deleted_ids.get(kid, 0))
            result["ok"] = True
        except Exception as exc:
            result["error"] = str(exc)
        self.delta_fetched.emit(result)


class ConnectionBadge(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.online = True
        self.setFixedSize(32, 24)
        self.setToolTip("Bağlantı kontrol ediliyor")

    def set_online(self, online, tooltip=""):
        self.online = bool(online)
        if tooltip:
            self.setToolTip(tooltip)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(34, 197, 94, 32) if self.online else QColor(239, 68, 68, 48)
        border = QColor(34, 197, 94, 100) if self.online else QColor(248, 113, 113, 210)
        color = QColor("#22c55e") if self.online else QColor("#fecaca")
        painter.setPen(QPen(border, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 10, 10)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(color, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        center_x = self.width() // 2
        base_y = 17
        painter.drawArc(center_x - 10, base_y - 14, 20, 18, 35 * 16, 110 * 16)
        painter.drawArc(center_x - 7, base_y - 10, 14, 12, 35 * 16, 110 * 16)
        painter.drawArc(center_x - 4, base_y - 6, 8, 7, 35 * 16, 110 * 16)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center_x - 2, base_y - 1, 4, 4)
        if not self.online:
            painter.setPen(QPen(QColor("#ef4444"), 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(center_x + 7, 6, center_x + 11, 18)
        painter.end()

class MainApp(QMainWindow):
    def __init__(self, user_info, email, manager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("MetaFold Teknik Servis ERP")
        self.setWindowFlags(Qt.WindowType.Widget)
        self.user_id = user_info['localId']
        self.token = user_info['idToken']
        self.refresh_token = user_info.get('refreshToken', '')
        self.user_email = email
        self.settings = QSettings("MetaFold", "Servis")
        self.normalize_language_setting()
        self.download_session_started_at = datetime.datetime.now()
        self.download_session_bytes = 0
        self.download_usage_shortcut = QShortcut(QKeySequence("Ctrl+Shift+D"), self)
        self.download_usage_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.download_usage_shortcut.activated.connect(self.show_download_usage_dialog)
        self.session_custom_logo = str(self.user_setting_value("custom_logo", "") or "")
        self.support_restore_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F12"), self)
        self.support_restore_shortcut.activated.connect(self.open_support_restore_gate)
        self.staff_pin_recovery_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F11"), self)
        self.staff_pin_recovery_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self.staff_pin_recovery_shortcut.activated.connect(self.open_staff_pin_recovery_gate)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        self.w_tables = []
        self.search_boxes = []
        self.filter_labels = []
        self.kayitlar_data = {} 
        self.audit_session_logs = {}
        self.usd_rate = 32.50
        self.eur_rate = 35.00
        
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.run_scheduled_refresh)
        self.token_refresh_timer = QTimer(self)
        self.token_refresh_timer.timeout.connect(lambda: self.ensure_firebase_session(force=True))
        self._last_token_refresh = datetime.datetime.now()
        self._refreshing_tables = False
        self._refresh_requested = False
        self._wholesalers_loaded = False
        self._cache_fallback_sections = set()
        self._cache_preferred_sections = set()
        self._read_only_cache_mode = False
        self._cache_only_refresh = False
        self._cache_boot_refresh = False
        self._refresh_prefer_cache = False
        self._refresh_force_cloud = False
        self._scheduled_refresh_prefer_cache = True
        self._scheduled_refresh_force_cloud = False
        self._background_cloud_refresh_scheduled = False
        self._last_connection_online = True
        self._connection_check_worker = None
        self.connection_check_timer = QTimer(self)
        self.connection_check_timer.timeout.connect(self.start_connection_check)
        
        prof = safe_dict_parse(user_info.get("_metafold_profile") or {})
        if not isinstance(prof, dict) or not prof:
            profile_raw = db.child("users").child(self.user_id).child("profil").get(self.token).val() or {}
            self.record_download_usage("profil", payload=profile_raw, detail="Profil okuma")
            prof = safe_dict_parse(profile_raw)
        if not isinstance(prof, dict):
            prof = {}
        license_data = safe_dict_parse(user_info.get("_metafold_license") or {})
        if not isinstance(license_data, dict) or not license_data:
            license_data = read_license_data(db, self.user_id, self.token, prof)
        self.firma_adi = prof.get("firma_adi", "MetaFold Firması")
        self.profile_data = prof
        self.license_data = license_data
        license_type = str(license_data.get("lisans_tipi", "") or "").strip().lower()
        self.is_trial_license = license_type in ("deneme", "trial")
        if not license_type and license_data.get("trial_device_key"):
            try:
                created_text = str(license_data.get("lisans_olusturma", "") or "").strip().split()[0]
                expiry_text = str(license_data.get("lisans_bitis", "") or "").strip()
                created_date = datetime.datetime.strptime(created_text, "%d.%m.%Y").date()
                expiry_date = datetime.datetime.strptime(expiry_text, "%d.%m.%Y").date()
                self.is_trial_license = (expiry_date - created_date).days <= 31
            except:
                self.is_trial_license = False
        self.dükkan_adresi = prof.get("dükkan_adresi", "")
        self.receipt_shop_name = str(self.user_setting_value("receipt_shop_name", "") or "")
        self.receipt_shop_address = str(self.user_setting_value("receipt_shop_address", "") or "")
        self.current_staff = {"id": "owner", "name": "YÖNETİCİ", "role": "Yönetici"}
        self.staff_role_tabs = {
            "Yönetici": set(range(18)),
            "Servis Personeli": {0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 15, 17},
            "Kasa Kapalı Personel": {0, 1, 2, 3, 4, 5, 6, 7, 8, 11, 15, 17},
            "Sadece Görüntüleme": {0, 2, 3, 4, 5, 6, 7, 8, 11, 15},
        }
        self.ensure_staff_accounts_ready_on_startup()
        self.auto_select_single_staff_account()
        
        self.license_blocked = False
        self.license_block_reason = ""
        license_ok, license_reason, license_expiry, license_remaining = check_license_status(license_data, db, self.user_id, self.token)
        self.bitis_tarihi = license_expiry
        self.lisans_kalan = license_remaining
        if not license_ok:
            self.license_blocked = True
            self.license_block_reason = license_reason
        
        self.rates_thread = FetchRatesThread()
        self.rates_thread.rates_fetched.connect(self.on_rates_fetched)
        self.rates_thread.start()
        
        self.setup_custom_titlebar()
        self.update_connection_badge(True, "Bağlantı aktif")
        self.connection_check_timer.start(15000)
        QTimer.singleShot(1200, self.start_connection_check)
        self.central_widget.setObjectName("CentralWidget")
        self.setup_global_search_bar()
        
        self.cihaz_listesi = set()
        self.ariza_listesi = set()
        self.operation_listesi = set()
        self.musteri_listesi = set()
        self.bayi_isimleri = set()
        self._suggestion_popup_meta = {}
        self.selected_bayi_key = ""
        self.selected_customer_key = ""
        self.staff_gate_required = self.should_show_staff_gate()
        if self.staff_gate_required and hasattr(self, "global_search_bar"):
            self.global_search_bar.hide()
        
        self.main_body = QWidget()
        self.main_body_layout = QHBoxLayout(self.main_body)
        self.main_body_layout.setContentsMargins(0, 0, 0, 0)
        self.main_body_layout.setSpacing(0)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("AppSidebar")
        self.sidebar.setFixedWidth(248)
        self.sidebar_layout = QVBoxLayout(self.sidebar)
        self.sidebar_layout.setContentsMargins(10, 12, 10, 12)
        self.sidebar_layout.setSpacing(8)
        self.sidebar_nav = QScrollArea()
        self.sidebar_nav.setObjectName("SidebarScroll")
        self.sidebar_nav.setWidgetResizable(True)
        self.sidebar_nav.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.sidebar_nav.setFrameShape(QFrame.Shape.NoFrame)
        self.sidebar_nav_content = QWidget()
        self.sidebar_nav_layout = QVBoxLayout(self.sidebar_nav_content)
        self.sidebar_nav_layout.setContentsMargins(0, 0, 0, 0)
        self.sidebar_nav_layout.setSpacing(7)
        self.sidebar_nav.setWidget(self.sidebar_nav_content)
        self.nav_buttons = {}
        self.nav_base_labels = {}
        self.sidebar_sections = {}
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        self.tabs.setStyleSheet("QTabWidget::pane { border: 0; }")
        self.main_body_layout.addWidget(self.sidebar)
        self.main_body_layout.addWidget(self.tabs, 1)
        if self.staff_gate_required:
            self.main_body.hide()
        self.layout.addWidget(self.main_body, 1)
        self.staff_gate = self.create_staff_gate_screen()
        self.layout.addWidget(self.staff_gate, 1)
        self.staff_gate.hide()
        if self.staff_gate_required:
            QTimer.singleShot(0, lambda: self.show_staff_gate(startup=True))
        
        # Arayüzü Kuran Ana Fonksiyon
        self.init_tabs()
        self.install_no_wheel_combobox_filters()
        self.manager.setStyleSheet(get_theme_stylesheet(self.user_setting_value("theme", "Dark")))
        self.apply_staff_permissions()
        
        self.blink_state = False
        self.blink_timer = QTimer(self)
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.blink_timer.start(600)
        
        # Pyrebase stream kendi ic thread'inde HTTP hatalarini traceback olarak basabiliyor.
        # Guvenli senkron icin kayitlar stream ile dinlenir; eski polling dongusu calismaz.
        self.stream_worker = None
        self.delta_fetch_worker = None
        self._pending_sync_meta = None
        self._last_sync_meta = {}
        self.sync_session_id = uuid.uuid4().hex
        self.token_refresh_timer.start(45 * 60 * 1000)
        
        QTimer.singleShot(3000, self.cleanup_trash)
        self.load_initial_tables_from_cache_or_cloud()
        self.start_firebase_stream()
        self.translate_ui()
        if self.license_blocked:
            QTimer.singleShot(0, self.blocked_license_logout)
        else:
            QTimer.singleShot(900, self.show_release_notes_once)
        QTimer.singleShot(5000, self.guncelleme_kontrolu)
        QTimer.singleShot(6500, self.run_auto_backup_if_due)
        QTimer.singleShot(3000, self.update_management_report)

    def show_release_notes_once(self):
        key = f"release_notes_seen_{MEVCUT_SURUM}"
        if self.settings.value(key, "false") == "true":
            return
        notes_html = f"""
        <div style='line-height:1.45;'>
            <h2>MetaFold Servis v{MEVCUT_SURUM} Yenilikleri</h2>
            <ul>
                <li><b>Servis akışı yenilendi:</b> Yeni kayıtlar artık "İşlem Bekleyenler" altında başlar; teknik servis süreci "İşlemdekiler", tamamlanan cihazlar "Teslim/İade", kapanan kayıtlar "Teslim Edilenler" akışında izlenir.</li>
                <li><b>Bekleyenler ayrımı netleşti:</b> "Parça Bekliyor" artık işlemdeki cihaz olarak değerlendirilir; "İşlem Bekliyor" ayrı takip edilir.</li>
                <li><b>Firebase veri kullanımı azaltıldı:</b> Masaüstü açılışta yerel cache'i kullanır, eski kayıtları tekrar tekrar indirmez ve değişen kayıtları sync_meta/stream üzerinden alır.</li>
                <li><b>Canlı senkron güçlendirildi:</b> Firebase polling yerine stream/delta mantığı kullanılır; tablo komple yenilenmeden değişen kayıt satırları güncellenir.</li>
                <li><b>Veri indirme sayacı:</b> Gizli veri kullanım penceresiyle toplam, oturum ve son indirme kırılımı yerelde görülebilir.</li>
                <li><b>Mobil uyum:</b> Mobil uygulama da aynı servis akışı, yerel cache ve değişen kayıt senkron mantığıyla hizalandı.</li>
                <li><b>Mobil veri tasarrufu:</b> Mobil cache dosya tabanlı hale getirildi; cache varsa eski kayıtlar yerelden okunur, buluttan kritik alanlar ve değişen kayıtlar alınır.</li>
                <li><b>Mobil pasif bağlantı:</b> 2 dakika işlem yapılmadığında aktif mobil bağlantı askıya alma kuralı korunur.</li>
                <li><b>Genel arama ve notlar:</b> Arama alanı notları ve not geçmişini kapsar; Türkçe i/İ karakter eşleşmeleri iyileştirildi.</li>
                <li><b>Personel ve kasa:</b> Personel ana paneli, kasa hareketi ekleme yetkisi ve kazanç görünürlüğü ayrımı korunarak daha kullanışlı hale getirildi.</li>
                <li><b>Çıktı ve fiş akışı:</b> 56mm, 80mm, A5 ve basit fiş seçenekleri mevcut QR/fotoğraf/takip akışları korunarak hazırlandı.</li>
                <li><b>OTA paketi:</b> v11.2 mevcut veri, lisans, kamera/fotoğraf, QR takip ve installer akışlarını bozmadan hazırlanmıştır.</li>
            </ul>
        </div>
        """
        dlg = ReadOnlyDialog("Güncelleme Notları", notes_html, self)
        dlg.resize(620, 520)
        dlg.exec()
        self.settings.setValue(key, "true")

    def cleanup_trash(self):
        try:
            trash_raw = db.child("users").child(self.user_id).child("cop_kutusu").get(self.token).val() or {}
            self.record_download_usage("section:cop_kutusu", payload=trash_raw, detail="Cop kutusu kontrolu")
            trash_data = safe_dict_parse(trash_raw)
            if not isinstance(trash_data, dict):
                trash_data = {}
            now = datetime.datetime.now()
            for module, items in trash_data.items():
                items = safe_dict_parse(items)
                if not isinstance(items, dict):
                    continue
                for item_id, item_info in items.items():
                    if not isinstance(item_info, dict):
                        continue
                    del_date_str = item_info.get("deleted_at")
                    if del_date_str:
                        if (now - datetime.datetime.strptime(del_date_str, "%Y-%m-%d")).days > 30:
                            db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).remove(self.token)
        except:
            pass

    def soft_delete(self, module, item_id):
        if module in ("denetim_loglari", "personel_loglari", "audit_logs"):
            QMessageBox.warning(self, "Silme Engellendi", "Denetim ve personel logları uygulama içinden silinemez.")
            return False
        try:
            item_data = db.child("users").child(self.user_id).child(module).child(item_id).get(self.token).val()
            if not item_data:
                QMessageBox.warning(self, "Silme Hatası", "Silinecek kayıt bulunamadı veya daha önce silinmiş.")
                return False
            del_data = {
                "data": safe_dict_parse(item_data) if isinstance(item_data, dict) else item_data,
                "deleted_at": datetime.datetime.now().strftime("%Y-%m-%d")
            }
            db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).set(del_data, self.token)
            db.child("users").child(self.user_id).child(module).child(item_id).remove(self.token)
            if module == "kayitlar" and isinstance(item_data, dict):
                self.remove_public_status(item_data)
                self.remove_record_from_stream(item_id)
                self.touch_record_sync_meta(item_id, "delete")
            self.audit_log(
                "Silme",
                f"{module} kaydı çöp kutusuna taşındı",
                module,
                item_id,
                before=item_data
            )
            return True
        except Exception as e:
            QMessageBox.warning(self, "Silme Hatası", f"Kayıt çöp kutusuna taşınamadı:\n{e}")
            return False

    def log_record_action(self, kid, detail, audit=True):
        record_log = {
            "tarih": datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "detay": detail,
            "kullanici": self.user_email,
            "personel": self.current_staff.get("name", "YÖNETİCİ"),
            "rol": self.current_staff.get("role", "Yönetici")
        }
        try:
            if self.firebase_connection_available(timeout=0.5):
                db.child("users").child(self.user_id).child("kayitlar").child(kid).child("logs").push(record_log, self.token)
                self.touch_record_sync_meta(kid, "upsert")
        except:
            pass
        if audit:
            self.audit_log("Cihaz Kaydı", detail, "kayitlar", kid)

    def audit_safe_value(self, value, depth=0):
        sensitive_keys = {"pin", "pin_hash", "pin_salt", "password", "sifre", "token", "refresh_token"}
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            if depth >= 2:
                return str(value)[:300]
            safe = {}
            for key, val in list(value.items())[:50]:
                key_text = str(key)
                if key_text.lower() in sensitive_keys:
                    safe[key_text] = "[GİZLİ]"
                else:
                    safe[key_text] = self.audit_safe_value(val, depth + 1)
            return safe
        if isinstance(value, (list, tuple, set)):
            if depth >= 2:
                return str(value)[:300]
            return [self.audit_safe_value(item, depth + 1) for item in list(value)[:30]]
        return str(value)[:300]

    def audit_cache_file(self):
        base_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MetaFold", "audit_cache")
        os.makedirs(base_dir, exist_ok=True)
        safe_uid = re.sub(r"[^A-Za-z0-9_-]", "_", str(self.user_id or "local"))
        return os.path.join(base_dir, f"{safe_uid}.json")

    def read_local_audit_cache(self):
        try:
            path = self.audit_cache_file()
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def write_local_audit_cache(self, event_id, payload):
        try:
            data = self.read_local_audit_cache()
            data[str(event_id)] = payload
            # Yerel önbellek sadece emniyet ağı; aşırı büyümesin diye son 2000 kayıt tutulur.
            if len(data) > 2000:
                ordered = sorted(
                    data.items(),
                    key=lambda item: str(item[1].get("ts", "")) if isinstance(item[1], dict) else "",
                    reverse=True
                )[:2000]
                data = dict(ordered)
            with open(self.audit_cache_file(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def audit_log(self, action, detail="", target_type="", target_id="", before=None, after=None, severity="info"):
        any_written = False
        result = {
            "ok": False,
            "protected": False,
            "backup": False,
            "local": False,
            "event_id": "",
            "payload": {},
            "error": ""
        }
        try:
            now = datetime.datetime.now()
            event_id = uuid.uuid4().hex
            payload = {
                "event_id": event_id,
                "tarih": now.strftime("%d.%m.%Y %H:%M:%S"),
                "ts": now.isoformat(timespec="seconds"),
                "islem": str(action or ""),
                "detay": str(detail or ""),
                "hedef_tur": str(target_type or ""),
                "hedef_id": str(target_id or ""),
                "seviye": str(severity or "info"),
                "personel_id": str(self.current_staff.get("id", "")),
                "personel": str(self.current_staff.get("name", "YÖNETİCİ")),
                "rol": str(self.current_staff.get("role", "Yönetici")),
                "hesap": str(self.user_email or ""),
                "surum": str(MEVCUT_SURUM),
            }
            result["event_id"] = event_id
            if before is not None:
                payload["once"] = self.audit_safe_value(before)
            if after is not None:
                payload["sonra"] = self.audit_safe_value(after)
            result["payload"] = dict(payload)

            self.audit_session_logs[event_id] = dict(payload)
            if self.write_local_audit_cache(event_id, payload):
                result["local"] = True
                any_written = True

            if not self.firebase_connection_available(timeout=0.5):
                result["ok"] = any_written
                return result

            def write_backup_log():
                db.child("users").child(self.user_id).child("denetim_loglari").child(event_id).set(payload, self.token)

            ref = db.child("audit_logs").child(self.user_id).child(event_id)
            protected_written = False
            try:
                ref.set(payload, self.token)
                protected_written = True
                any_written = True
                result["protected"] = True
            except Exception as e:
                result["error"] = str(e)
                try:
                    if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                        ref.set(payload, self.token)
                        protected_written = True
                        any_written = True
                        result["protected"] = True
                except Exception:
                    protected_written = False

            # Yönetim ekranı izin/kural değişimlerinden etkilenmesin diye okunabilir yedek kayıt tutulur.
            # Kalıcı, değiştirilemez asıl kayıt protected_written olduğunda audit_logs altında kalır.
            try:
                write_backup_log()
                any_written = True
                result["backup"] = True
            except Exception:
                if not protected_written:
                    raise
        except Exception:
            # Log yazma hatası kullanıcı akışını bozmamalı; ana işlem zaten tamamlanmış olabilir.
            pass
        result["ok"] = any_written
        return result

    def apply_local_record_update(self, kid, payload):
        if not kid or not isinstance(payload, dict):
            return
        try:
            data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
            if not isinstance(data, dict):
                data = {}
            record = data.get(kid)
            if not isinstance(record, dict):
                record = {}
            record.update(payload)
            data[kid] = record
            self.kayitlar_data = data
            self.write_cached_section("kayitlar", data)
        except Exception:
            pass

    def update_record_fields(self, kid, payload, action_label="Cihaz güncelleme", require_connection=True):
        if require_connection and not self.ensure_write_connection(action_label):
            return False
        payload = dict(payload or {})
        sync_ms = self.current_sync_ms()
        payload.setdefault("updated_at", datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
        payload.setdefault("updated_at_ms", sync_ms)
        payload.setdefault("updated_source", "desktop")
        ref = db.child("users").child(self.user_id).child("kayitlar").child(kid)
        try:
            ref.update(payload, self.token)
            self.apply_local_record_update(kid, payload)
            self.touch_record_sync_meta(kid, "upsert", payload.get("updated_at_ms", sync_ms))
            return True
        except Exception as e:
            try:
                if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                    ref.update(payload, self.token)
                    self.apply_local_record_update(kid, payload)
                    self.touch_record_sync_meta(kid, "upsert", payload.get("updated_at_ms", sync_ms))
                    return True
            except Exception as retry_error:
                e = retry_error
            QMessageBox.warning(self, action_label, self.friendly_write_error(action_label, e))
            return False

    def append_note_history(self, kid, text, note_type):
        try:
            db.child("users").child(self.user_id).child("kayitlar").child(kid).child("not_gecmisi").push({
                "zaman": datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "metin": text,
                "tip": note_type,
                "personel": self.current_staff.get("name", "YÖNETİCİ"),
                "rol": self.current_staff.get("role", "Yönetici"),
                "hesap": self.user_email,
                "source": "desktop"
            }, self.token)
            self.touch_record_sync_meta(kid, "upsert")
        except Exception:
            # Notun kendisi kaydedildiyse geçmiş kaydı yüzünden kullanıcı akışını bozmayalım.
            pass

    def format_record_note_text(self, note_text, empty_text="Kayıtlı not bulunamadı."):
        text = str(note_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return empty_text
        if len(lines) == 1:
            return lines[0]
        return "\n\n".join(f"{idx}. {line}" for idx, line in enumerate(lines, start=1))

    def format_note_history_text(self, history):
        history = safe_dict_parse(history)
        if not isinstance(history, dict) or not history:
            return "Not geçmişi bulunamadı."
        rows = []
        for idx, (_key, value) in enumerate(history.items(), start=1):
            if not isinstance(value, dict):
                continue
            note = self.format_record_note_text(value.get("metin", ""), "")
            if not note:
                continue
            tip = str(value.get("tip", "Not") or "Not")
            zaman = str(value.get("zaman", "") or "").strip()
            header = f"{idx}. {tip}" + (f" - {zaman}" if zaman else "")
            rows.append(f"{header}\n{note}")
        return f"\n\n{'-' * 36}\n\n".join(rows) if rows else "Not geçmişi bulunamadı."

    def parse_history_datetime(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        text = text.replace("Z", "").strip()
        for fmt in (
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                return datetime.datetime.strptime(text, fmt)
            except Exception:
                pass
        try:
            return datetime.datetime.fromisoformat(text)
        except Exception:
            return None

    def history_event_ts(self, tarih):
        dt = self.parse_history_datetime(tarih)
        return dt.isoformat(timespec="seconds") if dt else ""

    def compact_history_detail(self, text, limit=280):
        text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        text = re.sub(r"\s+", " ", text)
        if len(text) <= limit:
            return text
        return text[:limit - 3].rstrip() + "..."

    def make_record_history_event(self, kid, source_key, tarih, islem, detail, personel="", rol="", source="kayıt içi"):
        return {
            "event_id": f"record:{kid}:{source_key}",
            "tarih": str(tarih or ""),
            "ts": self.history_event_ts(tarih),
            "islem": str(islem or "Kayıt Hareketi"),
            "hedef_tur": "kayitlar",
            "hedef_id": str(kid or ""),
            "detay": self.compact_history_detail(detail),
            "personel": str(personel or ""),
            "rol": str(rol or ""),
            "kaynak": source,
            "surum": str(MEVCUT_SURUM),
        }

    def record_activity_events(self, kid, record, include_record_logs=True, include_notes=True, include_photos=True, include_creation=True):
        record = safe_dict_parse(record)
        if not isinstance(record, dict):
            return []
        events = []

        if include_creation:
            created = str(record.get("z", "") or "").strip()
            if created:
                detail = f"Kayıt oluşturuldu: {record.get('c_no', '')} / {record.get('m', '')} / {record.get('ci', '')}"
                events.append(self.make_record_history_event(
                    kid,
                    "created",
                    created,
                    "Kayıt Oluşturuldu",
                    detail,
                    record.get("created_by_personel") or record.get("personel") or "",
                    record.get("created_by_role") or record.get("rol") or "",
                    "kayıt"
                ))

        note_history = safe_dict_parse(record.get("not_gecmisi", {}))
        note_history_present = isinstance(note_history, dict) and bool(note_history)
        if include_notes and note_history_present:
            for key, value in note_history.items():
                if not isinstance(value, dict):
                    continue
                note_text = self.format_record_note_text(value.get("metin", ""), "")
                if not note_text:
                    continue
                tip = str(value.get("tip", "Not") or "Not").strip()
                tarih = str(value.get("zaman", "") or "").strip()
                islem = "Not Düzenlendi" if "düzen" in tip.lower() else "Not Eklendi"
                events.append(self.make_record_history_event(
                    kid,
                    f"note:{key}",
                    tarih,
                    islem,
                    f"{tip}: {note_text}",
                    value.get("personel", ""),
                    value.get("rol", ""),
                    "not geçmişi"
                ))

        if include_photos:
            raw_photos = record.get("photos", {})
            photo_items = raw_photos.items() if isinstance(raw_photos, dict) else enumerate(raw_photos) if isinstance(raw_photos, list) else []
            for key, value in photo_items:
                if isinstance(value, dict):
                    url = str(value.get("url", "") or "").strip()
                    if not url:
                        continue
                    tarih = str(value.get("created_at", "") or value.get("zaman", "") or "").strip()
                    provider = str(value.get("provider") or value.get("storage_provider") or "").strip()
                    source = str(value.get("source", "") or "").strip()
                    detail_parts = ["Fotoğraf eklendi"]
                    if source:
                        detail_parts.append(f"kaynak: {source}")
                    if provider:
                        detail_parts.append(f"sağlayıcı: {provider}")
                    events.append(self.make_record_history_event(
                        kid,
                        f"photo:{key}",
                        tarih,
                        "Fotoğraf Eklendi",
                        " | ".join(detail_parts),
                        value.get("personel", ""),
                        value.get("rol", ""),
                        "fotoğraf"
                    ))

            for idx, legacy_key in enumerate(["photo_url", "photo_url_2", "photo_url_3"], start=1):
                if str(record.get(legacy_key, "") or "").strip():
                    events.append(self.make_record_history_event(
                        kid,
                        f"legacy-photo:{legacy_key}",
                        "",
                        "Fotoğraf Eklendi",
                        f"Eski fotoğraf alanı: {idx}. fotoğraf",
                        "",
                        "",
                        "fotoğraf"
                    ))

        if include_record_logs:
            logs = safe_dict_parse(record.get("logs", {}))
            if isinstance(logs, dict):
                for key, value in logs.items():
                    if not isinstance(value, dict):
                        continue
                    detail = str(value.get("detay", "") or "").strip()
                    if not detail:
                        continue
                    folded = detail.lower()
                    if note_history_present and ("not eklendi" in folded or "not düzenlendi" in folded):
                        continue
                    events.append(self.make_record_history_event(
                        kid,
                        f"log:{key}",
                        value.get("tarih", ""),
                        "Kayıt İşlemi",
                        detail,
                        value.get("personel") or value.get("kullanici") or "",
                        value.get("rol", ""),
                        "kayıt logu"
                    ))

        def event_sort_key(item):
            ts = str(item.get("ts", "") or "")
            if ts:
                return ts
            tarih = str(item.get("tarih", "") or "")
            return tarih

        return sorted(events, key=event_sort_key, reverse=True)

    def format_record_activity_text(self, kid, record):
        events = self.record_activity_events(kid, record)
        if not events:
            return "Bu kayıt için işlem geçmişi bulunamadı."
        rows = []
        for idx, event in enumerate(events, start=1):
            tarih = str(event.get("tarih", "") or "Tarih yok")
            islem = str(event.get("islem", "") or "Kayıt Hareketi")
            personel = str(event.get("personel", "") or "").strip()
            rol = str(event.get("rol", "") or "").strip()
            source = str(event.get("kaynak", "") or "").strip()
            actor = f" - {personel}" if personel else ""
            if rol:
                actor += f" ({rol})"
            source_text = f" [{source}]" if source else ""
            rows.append(f"{idx}. [{tarih}] {islem}{actor}{source_text}\n{event.get('detay', '')}")
        return f"\n\n{'-' * 42}\n\n".join(rows)

    def embedded_record_audit_entries(self, limit=1500):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = self.read_cached_section("kayitlar", default={})
        entries = {}
        for kid, record in (data.items() if isinstance(data, dict) else []):
            if not isinstance(record, dict):
                continue
            for event in self.record_activity_events(
                kid,
                record,
                include_record_logs=False,
                include_notes=True,
                include_photos=True,
                include_creation=False,
            ):
                event_id = str(event.get("event_id", "") or f"record:{kid}:{len(entries)}")
                entries[event_id] = event

        def sort_key(item):
            _key, value = item
            return str(value.get("ts", "") or value.get("tarih", "")) if isinstance(value, dict) else ""

        ordered = sorted(entries.items(), key=sort_key, reverse=True)
        return dict(ordered[:limit])

    def public_status_key(self, record):
        code = str(record.get("c_no", "") if isinstance(record, dict) else record).strip().upper()
        for ch in [".", "#", "$", "[", "]", "/"]:
            code = code.replace(ch, "-")
        return code

    def build_public_status_payload(self, kid, record):
        phone = "".join(filter(str.isdigit, str(record.get("t", ""))))
        net = safe_float(record.get("masraf", "0"))
        approx = safe_float(record.get("yaklasik_ucret", "0"))
        price_text = ""
        if net > 0:
            price_text = format_public_money(net)
        elif approx > 0:
            price_text = f"Yaklaşık: {format_public_money(approx)}"
        customer_name = str(record.get("m", "") or "").strip()
        first_name = customer_name.split()[0] if customer_name else ""
        status_text = str(record.get("d", "Bilinmiyor") or "Bilinmiyor")
        delivery_text = str(record.get("teslim_durumu", "") or "")
        status_norm = status_text.replace("İ", "I").replace("ı", "i").lower()
        if "teslim bekliyor" in status_norm:
            delivery_text = "Teslim Bekliyor"
        elif "iade bekliyor" in status_norm or "iade teslimi bekliyor" in status_norm:
            delivery_text = "İade Teslimi Bekliyor"
        elif ("teslim edildi" in status_norm or "iade edildi" in status_norm) and not delivery_text:
            delivery_text = "Müşteriye Teslim Edildi"
        return {
            "record_id": kid,
            "owner_uid": self.user_id,
            "shop_name": self.display_company_name(),
            "system_name": "MetaFold ERP Sistemleri",
            "record_code": str(record.get("c_no", "") or ""),
            "phone_last4": phone[-4:] if len(phone) >= 4 else phone,
            "customer": first_name,
            "device": str(record.get("ci", "") or ""),
            "fault": str(record.get("a", "") or ""),
            "faults_count": len(self.get_faults(record)) if isinstance(record, dict) else 0,
            "status": status_text,
            "delivery_status": delivery_text,
            "operation": str(record.get("yapilan_islem", "") or ""),
            "price_text": price_text,
            "approval_status": str(record.get("approval_status", "") or ""),
            "approval_price": str(record.get("approval_price", "") or ""),
            "approval_requested_at": str(record.get("approval_requested_at", "") or ""),
            "warranty_until": str(record.get("garanti_bitis", "") or ""),
            "created_at": str(record.get("z", "") or ""),
            "updated_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
        }

    def publish_public_status(self, kid, record=None):
        try:
            if not self.firebase_connection_available(timeout=0.5):
                self.set_sync_status("Müşteri takip yayını bağlantı bekliyor", "#f59e0b")
                self.update_connection_badge(False)
                return
            if record is None:
                record = db.child("users").child(self.user_id).child("kayitlar").child(kid).get(self.token).val() or {}
            record = safe_dict_parse(record)
            if not isinstance(record, dict):
                return
            key = self.public_status_key(record)
            if not key:
                return
            db.child("public_status").child(key).set(self.build_public_status_payload(kid, record), self.token)
        except Exception as e:
            self.set_sync_status(f"Müşteri takip yayını bekliyor: {e}", "#f59e0b")

    def remove_public_status(self, record):
        try:
            key = self.public_status_key(record)
            if key:
                db.child("public_status").child(key).remove(self.token)
        except:
            pass

    def show_customer_status_link(self, kid, record):
        code = str(record.get("c_no", "") or "").strip()
        phone = "".join(filter(str.isdigit, str(record.get("t", ""))))
        last4 = phone[-4:] if len(phone) >= 4 else phone
        url = self.customer_status_url(record)
        msg = self.customer_status_message(record)

        dlg = QDialog(self)
        dlg.setWindowTitle("Müşteri Takip Linki")
        dlg.resize(520, 360)
        lay = QVBoxLayout(dlg)
        info = QLabel(
            f"<b>Kayıt No:</b> {code}<br>"
            f"<b>Telefon son 4:</b> {last4 or 'Telefon yok'}<br><br>"
            f"Müşteri bu linkten cihaz durumunu takip edebilir:"
        )
        info.setWordWrap(True)
        link_box = QLineEdit(url)
        link_box.setReadOnly(True)
        msg_box = QTextEdit()
        msg_box.setPlainText(msg)
        msg_box.setMinimumHeight(120)
        btn_row = QHBoxLayout()
        btn_copy = QPushButton("Linki Kopyala")
        btn_wp = QPushButton("WhatsApp Mesajı Olarak Gönder")
        btn_close = QPushButton("Kapat")
        btn_copy.clicked.connect(lambda: QApplication.clipboard().setText(url))
        btn_wp.clicked.connect(lambda: self.send_customer_status_whatsapp(record, msg))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_copy)
        btn_row.addWidget(btn_wp)
        btn_row.addWidget(btn_close)
        lay.addWidget(info)
        lay.addWidget(link_box)
        lay.addWidget(QLabel("Gönderilecek mesaj:"))
        lay.addWidget(msg_box)
        lay.addLayout(btn_row)
        QApplication.clipboard().setText(url)
        dlg.exec()

    def customer_status_message(self, record):
        code = str(record.get("c_no", "") or "").strip()
        name = str(record.get("m", "") or "").strip()
        device = str(record.get("ci", "") or "").strip()
        url = self.customer_status_url(record)
        greeting = f"Merhaba {name}," if name else "Merhaba,"
        device_line = f"{device} cihazınızın" if device else "Cihazınızın"
        return (
            f"{greeting}\n\n"
            f"{device_line} servis durumunu aşağıdaki linkten takip edebilirsiniz.\n\n"
            f"{self.display_company_name()}\n"
            f"MetaFold ERP Sistemleri\n\n"
            f"Kayıt No: {code}\n"
            f"Takip Linki: {url}\n\n"
            f"Sorgulama ekranında telefon numaranızın son 4 hanesini girmeniz yeterlidir.\n\n"
            f"{self.display_company_name()}"
        )

    def send_customer_status_whatsapp(self, record, message=None):
        tel = "".join(filter(str.isdigit, str(record.get("t", ""))))
        if tel.startswith("0"):
            tel = tel[1:]
        if len(tel) != 10:
            QMessageBox.warning(self, "WhatsApp", "Bu kayıt için geçerli 10 haneli telefon numarası bulunamadı.")
            return
        msg = message or self.customer_status_message(record)
        webbrowser.open(f"https://wa.me/90{tel}?text={requests.utils.quote(msg)}")

    def customer_status_url(self, record):
        code = str(record.get("c_no", "") if isinstance(record, dict) else record).strip()
        return f"{NETLIFY_URL.rstrip('/')}/durum.html?kayit={urllib.parse.quote(code)}"

    def receipt_status_qr_base64(self, record):
        if str(self.user_setting_value("receipt_status_qr", "true")) != "true":
            return ""
        code = str(record.get("c_no", "") if isinstance(record, dict) else "").strip()
        if not code:
            return ""
        try:
            import qrcode
            qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_Q, box_size=10, border=3)
            qr.add_data(self.customer_status_url(record))
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            self.set_sync_status(f"Fiş QR oluşturulamadı: {e}", "#f59e0b")
            return ""

    def code39_barcode_image(self, value, height=86, narrow=2, wide=5):
        try:
            from PIL import Image, ImageDraw
            patterns = {
                "0": "nnnwwnwnn", "1": "wnnwnnnnw", "2": "nnwwnnnnw", "3": "wnwwnnnnn",
                "4": "nnnwwnnnw", "5": "wnnwwnnnn", "6": "nnwwwnnnn", "7": "nnnwnnwnw",
                "8": "wnnwnnwnn", "9": "nnwwnnwnn", "A": "wnnnnwnnw", "B": "nnwnnwnnw",
                "C": "wnwnnwnnn", "D": "nnnnwwnnw", "E": "wnnnwwnnn", "F": "nnwnwwnnn",
                "G": "nnnnnwwnw", "H": "wnnnnwwnn", "I": "nnwnnwwnn", "J": "nnnnwwwnn",
                "K": "wnnnnnnww", "L": "nnwnnnnww", "M": "wnwnnnnwn", "N": "nnnnwnnww",
                "O": "wnnnwnnwn", "P": "nnwnwnnwn", "Q": "nnnnnnwww", "R": "wnnnnnwwn",
                "S": "nnwnnnwwn", "T": "nnnnwnwwn", "U": "wwnnnnnnw", "V": "nwwnnnnnw",
                "W": "wwwnnnnnn", "X": "nwnnwnnnw", "Y": "wwnnwnnnn", "Z": "nwwnwnnnn",
                "-": "nwnnnnwnw", ".": "wwnnnnwnn", " ": "nwwnnnwnn", "$": "nwnwnwnnn",
                "/": "nwnwnnnwn", "+": "nwnnnwnwn", "%": "nnnwnwnwn", "*": "nwnnwnwnn",
            }
            raw = self.normalize_upper(value).strip()
            cleaned = "".join(ch for ch in raw if ch in patterns and ch != "*")
            if not cleaned:
                return None
            encoded = f"*{cleaned}*"
            quiet = 14
            gap = narrow
            width = quiet * 2
            for char in encoded:
                width += sum(wide if part == "w" else narrow for part in patterns[char]) + gap
            img = Image.new("RGB", (width, height), "white")
            draw = ImageDraw.Draw(img)
            x = quiet
            for char in encoded:
                for idx, part in enumerate(patterns[char]):
                    part_width = wide if part == "w" else narrow
                    if idx % 2 == 0:
                        draw.rectangle([x, 0, x + part_width - 1, height - 1], fill="black")
                    x += part_width
                x += gap
            return img
        except Exception as e:
            self.set_sync_status(f"Barkod oluşturulamadı: {e}", "#f59e0b")
            return None

    def code39_barcode_base64(self, value):
        try:
            img = self.code39_barcode_image(value)
            if img is None:
                return ""
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            return base64.b64encode(buffer.getvalue()).decode("utf-8")
        except Exception as e:
            self.set_sync_status(f"Barkod oluşturulamadı: {e}", "#f59e0b")
            return ""

    def collect_user_snapshot(self):
        raw = db.child("users").child(self.user_id).get(self.token).val() or {}
        data = safe_dict_parse(raw)
        return data if isinstance(data, dict) else {}

    def collect_public_status_snapshot(self, user_snapshot=None):
        try:
            records = safe_dict_parse((user_snapshot or {}).get("kayitlar", {}) or {})
            if not isinstance(records, dict):
                return {}
            filtered = {}
            for kid, rec in records.items():
                if not isinstance(rec, dict):
                    continue
                key = self.public_status_key(rec)
                if key:
                    filtered[key] = self.build_public_status_payload(kid, rec)
            return filtered
        except Exception as e:
            self.set_sync_status(f"Durum yedeği hazırlanamadı: {e}", "#f59e0b")
            return {}

    def build_backup_manifest(self, snapshot, public_status=None):
        def as_map(value):
            parsed = safe_dict_parse(value or {})
            return parsed if isinstance(parsed, dict) else {}

        records = as_map(snapshot.get("kayitlar"))
        stock = as_map(snapshot.get("stok"))
        dealers = as_map(snapshot.get("sabit_bayiler"))
        suppliers = as_map(snapshot.get("firmalar"))
        supplier_parts = as_map(snapshot.get("toptanci"))
        supplier_payments = as_map(snapshot.get("toptanci_odemeler"))
        cash = as_map(snapshot.get("kasa"))
        audit_logs = as_map(snapshot.get("denetim_loglari"))
        photos_count = 0
        customer_keys = set()
        dealer_record_count = 0
        for rec_id, rec in records.items():
            if not isinstance(rec, dict):
                continue
            photos = as_map(rec.get("photos"))
            photos_count += len(photos)
            if self.is_bayi_record(rec):
                dealer_record_count += 1
                continue
            key = str(rec.get("customer_key", "") or "").strip()
            phone = "".join(filter(str.isdigit, str(rec.get("t", "") or "")))[-10:]
            name = self.normalize_upper(rec.get("m", "")).strip()
            customer_keys.add(
                key
                or (f"PHONE-{phone}" if phone else f"NAME-{name}" if name else f"RECORD-{rec_id}")
            )

        canonical = json.dumps(
            {"users": snapshot, "public_status": public_status or {}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "schema": "metafold-backup-v2",
            "backup_id": uuid.uuid4().hex,
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "app_version": str(MEVCUT_SURUM),
            "user_id": self.user_id,
            "user_email": self.user_email,
            "counts": {
                "records": len(records),
                "customers_estimated": len(customer_keys),
                "dealer_records": dealer_record_count,
                "dealers": len(dealers),
                "stock_items": len(stock),
                "suppliers": len(suppliers),
                "supplier_parts": len(supplier_parts),
                "supplier_payments": len(supplier_payments),
                "cash_entries": len(cash),
                "audit_logs": len(audit_logs),
                "photo_links": photos_count,
                "public_status": len(public_status or {}),
            },
            "sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        }

    def backup_report_text(self, manifest):
        counts = manifest.get("counts", {})
        lines = [
            "MetaFold Yedek Kontrol Raporu",
            f"Yedek ID: {manifest.get('backup_id', '')}",
            f"Tarih: {manifest.get('created_at', '')}",
            f"Sürüm: {manifest.get('app_version', '')}",
            f"Kullanıcı: {manifest.get('user_email', '')}",
            "",
            f"Cihaz kaydı: {counts.get('records', 0)}",
            f"Tahmini müşteri: {counts.get('customers_estimated', 0)}",
            f"Bayi cihaz kaydı: {counts.get('dealer_records', 0)}",
            f"Bayi: {counts.get('dealers', 0)}",
            f"Stok ürünü: {counts.get('stock_items', 0)}",
            f"Toptancı: {counts.get('suppliers', 0)}",
            f"Toptancı parça: {counts.get('supplier_parts', 0)}",
            f"Toptancı ödeme: {counts.get('supplier_payments', 0)}",
            f"Kasa hareketi: {counts.get('cash_entries', 0)}",
            f"Denetim logu: {counts.get('audit_logs', 0)}",
            f"Fotoğraf linki: {counts.get('photo_links', 0)}",
            f"Müşteri takip kaydı: {counts.get('public_status', 0)}",
            "",
            f"SHA256: {manifest.get('sha256', '')}",
            "",
            "Not: Taşıma sonrası bu sayılar ve SHA kontrolü karşılaştırılarak veri eksikliği olup olmadığı anlaşılır.",
        ]
        return "\n".join(lines)

    def default_backup_dir(self):
        base = os.path.join(os.path.expanduser("~"), "Documents", "MetaFold_Yedekler")
        os.makedirs(base, exist_ok=True)
        return base

    def write_backup_zip(self, path):
        snapshot = self.collect_user_snapshot()
        public_status = self.collect_public_status_snapshot(snapshot)
        manifest = self.build_backup_manifest(snapshot, public_status)
        payload = {
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
            "version": str(MEVCUT_SURUM),
            "user_email": self.user_email,
            "data": snapshot,
            "public_status": public_status,
            "manifest": manifest
        }
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("metafold_backup.json", json.dumps(payload, ensure_ascii=False, indent=2))
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            zf.writestr("integrity_report.txt", self.backup_report_text(manifest))
        return path

    def export_backup_zip(self):
        default_name = f"MetaFold_Yedek_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.zip"
        path, _ = QFileDialog.getSaveFileName(self, "MetaFold Yedeği Kaydet", os.path.join(self.default_backup_dir(), default_name), "ZIP Yedek (*.zip)")
        if not path:
            return
        if not path.lower().endswith(".zip"):
            path += ".zip"
        try:
            self.write_backup_zip(path)
            self.set_user_setting("last_backup_at", datetime.datetime.now().strftime("%Y-%m-%d"))
            QMessageBox.information(self, "Yedekleme", "Yedek başarıyla oluşturuldu.")
        except Exception as e:
            QMessageBox.warning(self, "Yedekleme Hatası", f"Yedek alınamadı:\n{e}")

    def verify_support_restore_password(self, password):
        digest = hashlib.sha256(f"metafold-support-restore:{password}".encode("utf-8")).hexdigest()
        return digest == SUPPORT_RESTORE_PASSWORD_HASH

    def open_support_restore_gate(self):
        password, ok = QInputDialog.getText(
            self,
            "Destek Modu",
            "Destek şifresi:",
            QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if not self.verify_support_restore_password(password.strip()):
            QMessageBox.warning(self, "Destek Modu", "Destek şifresi hatalı.")
            self.audit_log("Destek", "Hatalı destek geri yükleme şifresi denemesi", "support_restore", self.user_id)
            return
        self.audit_log("Destek", "Destek geri yükleme ekranı açıldı", "support_restore", self.user_id)
        self.show_support_restore_dialog()

    def open_staff_pin_recovery_gate(self):
        password, ok = QInputDialog.getText(
            self,
            "Personel PIN Kurtarma",
            "Destek şifresi:",
            QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        if not self.verify_support_restore_password(password.strip()):
            QMessageBox.warning(self, "Personel PIN Kurtarma", "Destek şifresi hatalı.")
            self.audit_log("Personel", "Hatalı yönetici PIN kurtarma şifresi denemesi", "personel", self.user_id)
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Yönetici PIN Sıfırla")
        lay = QVBoxLayout(dlg)
        info = QLabel("Yeni yönetici PIN kodunu belirleyin.")
        info.setWordWrap(True)
        pin_1 = QLineEdit()
        pin_1.setPlaceholderText("Yeni yönetici PIN")
        pin_1.setEchoMode(QLineEdit.EchoMode.Password)
        pin_1.setMaxLength(12)
        pin_2 = QLineEdit()
        pin_2.setPlaceholderText("Yeni PIN tekrar")
        pin_2.setEchoMode(QLineEdit.EchoMode.Password)
        pin_2.setMaxLength(12)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(info)
        lay.addWidget(pin_1)
        lay.addWidget(pin_2)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_pin = pin_1.text().strip()
        if len(new_pin) < 4:
            QMessageBox.warning(self, "Personel PIN Kurtarma", "PIN en az 4 haneli olmalı.")
            return
        if new_pin != pin_2.text().strip():
            QMessageBox.warning(self, "Personel PIN Kurtarma", "Girilen PIN'ler eşleşmiyor.")
            return

        accounts = [acc for acc in self.staff_accounts() if isinstance(acc, dict)]
        admin_index = next((idx for idx, acc in enumerate(accounts) if self.is_staff_admin_account(acc)), None)
        if admin_index is None:
            admin_index = next((idx for idx, acc in enumerate(accounts) if self.staff_account_name_key(acc) in {"YONETICI", "ADMIN"}), None)

        all_permissions = sorted(self.all_staff_permission_keys())
        if admin_index is None:
            updated_admin = self.make_staff_account("YÖNETİCİ", "Yönetici", new_pin, permissions=all_permissions)
            accounts.insert(0, updated_admin)
        else:
            existing = accounts[admin_index]
            admin_name = existing.get("name") or "YÖNETİCİ"
            updated_admin = self.make_staff_account(admin_name, "Yönetici", new_pin, existing, all_permissions)
            accounts[admin_index] = updated_admin

        accounts = self.normalized_staff_accounts(accounts)
        updated_admin = next((acc for acc in accounts if acc.get("id") == updated_admin.get("id")), updated_admin)
        self.save_staff_accounts(accounts)
        self.set_user_setting("staff_pin_enabled", "true")
        self.set_current_staff(updated_admin)
        self.log_staff_event("Destek ile yönetici PIN'i sıfırlandı")
        if hasattr(self, "staff_enabled_cb"):
            self.staff_enabled_cb.blockSignals(True)
            self.staff_enabled_cb.setChecked(True)
            self.staff_enabled_cb.blockSignals(False)
        if hasattr(self, "staff_gate_pin"):
            self.staff_gate_pin.clear()
        if hasattr(self, "staff_gate") and self.staff_gate.isVisible():
            self.refresh_staff_gate_accounts()
            self.unlock_staff_gate()
        self.build_sidebar_navigation()
        self.apply_staff_permissions()
        QMessageBox.information(self, "Personel PIN Kurtarma", "Yönetici PIN'i sıfırlandı ve yönetici oturumu açıldı.")

    def load_backup_zip_payload(self, path):
        with zipfile.ZipFile(path, "r") as zf:
            if "metafold_backup.json" not in zf.namelist():
                raise RuntimeError("Seçilen ZIP içinde metafold_backup.json bulunamadı.")
            payload = json.loads(zf.read("metafold_backup.json").decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Yedek dosyası okunamadı.")
        data = safe_dict_parse(payload.get("data", {}) or {})
        if not isinstance(data, dict):
            raise RuntimeError("Yedek içindeki kullanıcı verisi geçersiz.")
        payload["data"] = data
        public_status = safe_dict_parse(payload.get("public_status", {}) or {})
        payload["public_status"] = public_status if isinstance(public_status, dict) else {}
        return payload

    def backup_payload_preview_text(self, payload):
        manifest = safe_dict_parse(payload.get("manifest", {}) or {})
        counts = safe_dict_parse(manifest.get("counts", {}) if isinstance(manifest, dict) else {})
        data = safe_dict_parse(payload.get("data", {}) or {})

        def count_section(name):
            value = safe_dict_parse(data.get(name, {}) or {})
            return len(value) if isinstance(value, dict) else 0

        backup_user_id = str(manifest.get("user_id", "") or "")
        owner_note = "Aynı kullanıcı" if backup_user_id == self.user_id else "Farklı kullanıcı veya eski yedek"
        lines = [
            "MetaFold Destek Geri Yükleme Ön İzleme",
            "",
            f"Yedek tarihi: {manifest.get('created_at', payload.get('created_at', ''))}",
            f"Yedek sürümü: {manifest.get('app_version', payload.get('version', ''))}",
            f"Yedek kullanıcısı: {manifest.get('user_email', payload.get('user_email', ''))}",
            f"Hedef kullanıcı: {self.user_email}",
            f"Kullanıcı kontrolü: {owner_note}",
            "",
            f"Cihaz kaydı: {counts.get('records', count_section('kayitlar'))}",
            f"Bayi: {counts.get('dealers', count_section('sabit_bayiler'))}",
            f"Stok ürünü: {counts.get('stock_items', count_section('stok'))}",
            f"Toptancı: {counts.get('suppliers', count_section('firmalar'))}",
            f"Toptancı parça: {counts.get('supplier_parts', count_section('toptanci'))}",
            f"Toptancı ödeme: {counts.get('supplier_payments', count_section('toptanci_odemeler'))}",
            f"Kasa hareketi: {counts.get('cash_entries', count_section('kasa'))}",
            f"Denetim logu: {counts.get('audit_logs', count_section('denetim_loglari'))}",
            f"Müşteri takip kaydı: {counts.get('public_status', len(payload.get('public_status', {})))}",
            "",
            "Mod: Akıllı Birleştir",
            "- Mevcut canlı veri silinmez.",
            "- Aynı kayıt ID veya aynı kayıt no varsa tekrar eklenmez.",
            "- Sayaçlar ve mevcut ayarlar geriye alınmaz.",
            "- İşlemden önce otomatik geri dönüş yedeği alınır.",
        ]
        return "\n".join(lines)

    def merge_key_value_section(self, section_name, backup_section, current_section, duplicate_signatures=None):
        stats = {"added": 0, "skipped_existing": 0, "skipped_duplicate": 0, "errors": 0}
        if not isinstance(backup_section, dict):
            return stats
        current_section = current_section if isinstance(current_section, dict) else {}
        duplicate_signatures = duplicate_signatures or set()
        for item_id, item_data in backup_section.items():
            item_id = str(item_id)
            if item_id in current_section:
                stats["skipped_existing"] += 1
                continue
            signature = self.restore_item_signature(section_name, item_data)
            if signature and signature in duplicate_signatures:
                stats["skipped_duplicate"] += 1
                continue
            try:
                db.child("users").child(self.user_id).child(section_name).child(item_id).set(item_data, self.token)
                if section_name == "kayitlar":
                    self.touch_record_sync_meta(item_id, "upsert", item_data.get("updated_at_ms") if isinstance(item_data, dict) else None)
                if signature:
                    duplicate_signatures.add(signature)
                stats["added"] += 1
            except Exception:
                stats["errors"] += 1
        return stats

    def restore_item_signature(self, section_name, item_data):
        if not isinstance(item_data, dict):
            return ""
        if section_name == "kayitlar":
            code = str(item_data.get("c_no", "") or "").strip()
            return f"code:{code}" if code else ""
        if section_name == "stok":
            barcode = str(item_data.get("barkod", "") or item_data.get("barcode", "") or "").strip()
            if barcode:
                return f"barcode:{barcode}"
            stock_code = str(item_data.get("stok_kodu", "") or item_data.get("kod", "") or "").strip()
            if stock_code:
                return f"stock:{self.normalize_upper(stock_code)}"
            name = str(item_data.get("ad", "") or "").strip()
            return f"name:{self.normalize_upper(name)}" if name else ""
        if section_name in ("sabit_bayiler", "firmalar"):
            name = self.normalize_upper(item_data.get("ad", "") or item_data.get("isim", "") or "").strip()
            phone = "".join(filter(str.isdigit, str(item_data.get("tel", "") or item_data.get("telefon", "") or "")))[-10:]
            return f"party:{name}:{phone}" if name or phone else ""
        return ""

    def restore_signature_set(self, section_name, current_section):
        signatures = set()
        if not isinstance(current_section, dict):
            return signatures
        for item_data in current_section.values():
            signature = self.restore_item_signature(section_name, item_data)
            if signature:
                signatures.add(signature)
        return signatures

    def smart_merge_backup_payload(self, payload):
        if not self.ensure_firebase_session(force=True):
            raise RuntimeError("Firebase oturumu yenilenemedi.")
        rollback_name = f"MetaFold_GeriYuklemeOncesi_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        rollback_path = os.path.join(self.default_backup_dir(), rollback_name)
        self.write_backup_zip(rollback_path)

        backup_data = safe_dict_parse(payload.get("data", {}) or {})
        current_data = self.collect_user_snapshot()
        if not isinstance(backup_data, dict):
            raise RuntimeError("Yedek verisi geçersiz.")
        if not isinstance(current_data, dict):
            current_data = {}

        sections = [
            "kayitlar", "stok", "sabit_bayiler", "firmalar", "toptanci",
            "toptanci_odemeler", "kasa", "denetim_loglari", "personel_loglari",
            "cop_kutusu", "aktif_cihazlar"
        ]
        result = {"rollback_path": rollback_path, "sections": {}, "public_status": {"added": 0, "skipped_existing": 0, "errors": 0}}
        for section in sections:
            backup_section = safe_dict_parse(backup_data.get(section, {}) or {})
            current_section = safe_dict_parse(current_data.get(section, {}) or {})
            signatures = self.restore_signature_set(section, current_section)
            result["sections"][section] = self.merge_key_value_section(section, backup_section, current_section, signatures)

        backup_settings = safe_dict_parse(backup_data.get("ayarlar", {}) or {})
        current_settings = safe_dict_parse(current_data.get("ayarlar", {}) or {})
        result["sections"]["ayarlar"] = self.merge_key_value_section("ayarlar", backup_settings, current_settings)

        public_backup = safe_dict_parse(payload.get("public_status", {}) or {})
        if isinstance(public_backup, dict) and public_backup:
            for status_key, status_data in public_backup.items():
                status_key = str(status_key)
                try:
                    existing_status = db.child("public_status").child(status_key).get(self.token).val()
                    if isinstance(safe_dict_parse(existing_status), dict) and existing_status:
                        result["public_status"]["skipped_existing"] += 1
                        continue
                except Exception:
                    pass
                try:
                    if isinstance(status_data, dict):
                        status_data = dict(status_data)
                        status_data["owner_uid"] = self.user_id
                    db.child("public_status").child(status_key).set(status_data, self.token)
                    result["public_status"]["added"] += 1
                except Exception:
                    result["public_status"]["errors"] += 1

        self.audit_log("Destek", "Yedekten akıllı birleştirme çalıştırıldı", "support_restore", self.user_id, after=result)
        return result

    def support_restore_result_text(self, result):
        lines = [
            "Akıllı birleştirme tamamlandı.",
            "",
            f"İşlem öncesi geri dönüş yedeği: {result.get('rollback_path', '')}",
            "",
            "Bölüm sonuçları:"
        ]
        for section, stats in result.get("sections", {}).items():
            lines.append(
                f"- {section}: eklenen {stats.get('added', 0)}, "
                f"mevcut {stats.get('skipped_existing', 0)}, "
                f"kopya {stats.get('skipped_duplicate', 0)}, "
                f"hata {stats.get('errors', 0)}"
            )
        public_stats = result.get("public_status", {})
        lines.extend([
            "",
            f"- public_status: eklenen {public_stats.get('added', 0)}, mevcut {public_stats.get('skipped_existing', 0)}, hata {public_stats.get('errors', 0)}",
            "",
            "Tablolar yenilenecek. İşlemden sonra kayıt sayıları kontrol edilmeli."
        ])
        return "\n".join(lines)

    def show_support_restore_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("MetaFold Destek Geri Yükleme")
        dlg.resize(760, 560)
        lay = QVBoxLayout(dlg)
        info = QLabel("<b>Destek Geri Yükleme</b><br>Bu ekran gizlidir. Sadece akıllı birleştirme yapar; canlı veriyi silmez.")
        info.setWordWrap(True)
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText("Yedek ZIP seçin.")
        selected = {"path": "", "payload": None}
        btn_row = QHBoxLayout()
        btn_select = QPushButton("Yedek ZIP Seç")
        btn_restore = QPushButton("Akıllı Birleştir")
        btn_restore.setEnabled(False)
        btn_close = QPushButton("Kapat")

        def select_backup():
            path, _ = QFileDialog.getOpenFileName(self, "MetaFold Yedeği Seç", self.default_backup_dir(), "ZIP Yedek (*.zip)")
            if not path:
                return
            try:
                payload = self.load_backup_zip_payload(path)
                selected["path"] = path
                selected["payload"] = payload
                preview.setPlainText(self.backup_payload_preview_text(payload))
                btn_restore.setEnabled(True)
            except Exception as exc:
                selected["path"] = ""
                selected["payload"] = None
                btn_restore.setEnabled(False)
                QMessageBox.warning(self, "Yedek Okunamadı", str(exc))

        def run_restore():
            payload = selected.get("payload")
            if not isinstance(payload, dict):
                return
            if QMessageBox.question(
                self,
                "Akıllı Birleştir",
                "Seçili yedek hedef kullanıcıya akıllı birleştirme ile yüklenecek.\n\n"
                "Mevcut veriler silinmeyecek. İşlemden önce otomatik geri dönüş yedeği alınacak.\n\n"
                "Devam edilsin mi?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return
            try:
                btn_restore.setEnabled(False)
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
                result = self.smart_merge_backup_payload(payload)
                QApplication.restoreOverrideCursor()
                preview.setPlainText(self.support_restore_result_text(result))
                QMessageBox.information(self, "Geri Yükleme", "Akıllı birleştirme tamamlandı.")
                self.refresh_all_tables()
            except Exception as exc:
                QApplication.restoreOverrideCursor()
                btn_restore.setEnabled(True)
                QMessageBox.warning(self, "Geri Yükleme Hatası", f"İşlem tamamlanamadı:\n{exc}")

        btn_select.clicked.connect(select_backup)
        btn_restore.clicked.connect(run_restore)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_select)
        btn_row.addStretch()
        btn_row.addWidget(btn_restore)
        btn_row.addWidget(btn_close)
        lay.addWidget(info)
        lay.addWidget(preview, 1)
        lay.addLayout(btn_row)
        dlg.exec()

    def run_auto_backup_if_due(self):
        if str(self.user_setting_value("auto_backup_enabled", "true")) != "true":
            return
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        if str(self.user_setting_value("last_backup_at", "")) == today:
            return
        try:
            name = f"MetaFold_OtoYedek_{today}.zip"
            self.write_backup_zip(os.path.join(self.default_backup_dir(), name))
            self.set_user_setting("last_backup_at", today)
            self.set_sync_status("Otomatik yedek alındı", "#22c55e")
        except Exception as e:
            self.set_sync_status(f"Yedek hatası: {e}", "#ef4444")

    def save_message_templates(self):
        self.set_user_setting("tpl_ready", self.tpl_ready.toPlainText().strip())
        self.set_user_setting("tpl_waiting", self.tpl_waiting.toPlainText().strip())
        self.set_user_setting("tpl_part", self.tpl_part.toPlainText().strip())
        QMessageBox.information(self, "Mesaj Şablonları", "WhatsApp mesaj şablonları kaydedildi.")

    def save_default_warranty_days(self):
        days = int(safe_float(self.default_warranty_in.text(), 30))
        self.set_user_setting("default_warranty_days", str(max(0, days)))
        self.f_garanti_gun.setText(str(max(0, days)))
        QMessageBox.information(self, "Garanti", "Varsayılan garanti süresi kaydedildi.")

    def render_message_template(self, template, record):
        return str(template or "").format(
            musteri=record.get("m", ""),
            cihaz=record.get("ci", ""),
            kayit_no=record.get("c_no", ""),
            durum=record.get("d", ""),
            firma=self.firma_adi,
            ucret=format_money(safe_float(record.get("masraf", "0")), "₺")
        )

    def update_management_report(self):
        if not hasattr(self, "lbl_management_report"):
            return
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        total = waiting = active = ready = done = unpaid = warranty_active = approval_waiting = delivery_waiting = iade_waiting = 0
        faults = {}
        for rec in data.values():
            if not isinstance(rec, dict):
                continue
            total += 1
            durum = str(rec.get("d", ""))
            if durum in ["İşlem Bekliyor", "Islem Bekliyor"]:
                waiting += 1
            elif durum in ["Tamirde", "Parça Bekliyor"]:
                active += 1
            elif "Hazır" in durum or "İşlemleri Tamamlandı" in durum or "İade Bekliyor" in durum:
                ready += 1
            elif "Teslim" in durum or "İade Edildi" in durum:
                done += 1
            if rec.get("odeme_durumu", "Ödenmedi") != "Ödendi":
                unpaid += 1
            approval_status = str(rec.get("approval_status", "") or "")
            if approval_status == "Bekliyor":
                approval_waiting += 1
            delivery_text = str(rec.get("teslim_durumu", "") or "")
            if "Teslim Bekliyor" in delivery_text:
                if "İade" in durum or "Iade" in durum:
                    iade_waiting += 1
                else:
                    delivery_waiting += 1
            garanti_bitis = str(rec.get("garanti_bitis", ""))
            try:
                if garanti_bitis and datetime.datetime.strptime(garanti_bitis, "%d.%m.%Y").date() >= datetime.date.today():
                    warranty_active += 1
            except:
                pass
            for fault in self.get_faults(rec):
                faults[fault] = faults.get(fault, 0) + 1
        top_faults = ", ".join([f"{k} ({v})" for k, v in sorted(faults.items(), key=lambda item: item[1], reverse=True)[:5]]) or "Henüz veri yok"
        stok = safe_dict_parse(getattr(self, "stok_data", {}))
        low_stock = 0
        if isinstance(stok, dict):
            for item in stok.values():
                if isinstance(item, dict) and safe_float(item.get("adet", "0")) <= 2:
                    low_stock += 1
        self.lbl_management_report.setText(
            f"<b>Toplam kayıt:</b> {total} &nbsp; "
            f"<b>İşlem bekleyen:</b> {waiting} &nbsp; "
            f"<b>İşlemde:</b> {active} &nbsp; "
            f"<b>Teslim/iade:</b> {ready} &nbsp; "
            f"<b>Tamamlanan:</b> {done} &nbsp; "
            f"<b>Ödenmemiş:</b> {unpaid} &nbsp; "
            f"<b>Onay bekleyen:</b> {approval_waiting} &nbsp; "
            f"<b>Garantisi aktif:</b> {warranty_active} &nbsp; "
            f"<b>Düşük stok:</b> {low_stock}<br>"
            f"<b>Teslim bekleyen:</b> {delivery_waiting} &nbsp; "
            f"<b>İade teslimi bekleyen:</b> {iade_waiting}<br>"
            f"<b>En sık arızalar:</b> {top_faults}"
        )

    def build_smart_management_summary(self):
        today = datetime.date.today()
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}

        today_records = []
        delivered_today = []
        delivery_waiting = []
        iade_waiting = []
        approval_waiting = []
        unpaid = []
        dealer_open = 0
        faults = {}

        for kid, rec in data.items():
            if not isinstance(rec, dict):
                continue
            rec_date = self.parse_date_value(rec.get("z", "")).date()
            delivered_ok, delivered_iade = self.is_delivered_record(rec)
            durum = str(rec.get("d", "") or "")
            delivery_text = str(rec.get("teslim_durumu", "") or "")

            if rec_date == today:
                today_records.append((kid, rec))
                for fault in self.get_faults(rec):
                    faults[fault] = faults.get(fault, 0) + 1
            if delivered_ok and self.parse_date_value(rec.get("teslim_tarihi", rec.get("z", ""))).date() == today:
                delivered_today.append((kid, rec, delivered_iade))
            if rec.get("odeme_durumu", "Ödenmedi") != "Ödendi":
                unpaid.append((kid, rec))
            if str(rec.get("approval_status", "") or "") == "Bekliyor":
                approval_waiting.append((kid, rec))
            if "Teslim Bekliyor" in delivery_text:
                if "İade" in durum or "Iade" in durum:
                    iade_waiting.append((kid, rec))
                else:
                    delivery_waiting.append((kid, rec))
            if rec.get("record_type") == "bayi" or rec.get("bayi_key"):
                if not delivered_ok:
                    dealer_open += 1

        kasa_data = safe_dict_parse(getattr(self, "kasa_data", {}))
        income = expense = 0.0
        if isinstance(kasa_data, dict):
            for item in kasa_data.values():
                if not isinstance(item, dict):
                    continue
                if self.parse_date_value(item.get("t", "")).date() != today:
                    continue
                amount = safe_float(item.get("tutar", "0"))
                tip = str(item.get("tip", "") or "")
                if "Gider" in tip or "Çıkış" in tip or "Cikis" in tip:
                    expense += amount
                else:
                    income += amount

        stok_data = safe_dict_parse(getattr(self, "stok_data", {}))
        low_stock_items = []
        if isinstance(stok_data, dict):
            for sid, item in stok_data.items():
                if isinstance(item, dict) and safe_float(item.get("adet", "0")) <= 2:
                    low_stock_items.append((sid, item))

        top_faults = sorted(faults.items(), key=lambda x: x[1], reverse=True)[:5]
        top_faults_text = ", ".join(f"{html.escape(k)} ({v})" for k, v in top_faults) or "bugün belirgin arıza yoğunluğu yok"
        net_cash = income - expense
        workload = "sakin"
        if len(today_records) >= 15 or len(delivery_waiting) >= 8:
            workload = "yoğun"
        elif len(today_records) >= 7 or len(delivery_waiting) >= 4:
            workload = "orta seviyede"

        priority_items = []
        if delivery_waiting:
            priority_items.append(f"{len(delivery_waiting)} teslim bekleyen cihaz")
        if iade_waiting:
            priority_items.append(f"{len(iade_waiting)} iade teslimi")
        if approval_waiting:
            priority_items.append(f"{len(approval_waiting)} müşteri onayı")
        if low_stock_items:
            priority_items.append(f"{len(low_stock_items)} kritik stok")
        priority_text = ", ".join(priority_items) if priority_items else "acil görünen bir öncelik yok"

        low_stock_names = ", ".join(html.escape(str(item.get("ad", "") or item.get("stok_kodu", "") or "-")) for _, item in low_stock_items[:5])
        if not low_stock_names:
            low_stock_names = "kritik stok görünmüyor"

        return f"""
        <div style='line-height:1.55;'>
            <h2>Akıllı Yönetici Özeti - {today.strftime('%d.%m.%Y')}</h2>
            <p>
                Bugünkü servis trafiği <b>{workload}</b> görünüyor. Bugün <b>{len(today_records)}</b> yeni kayıt açılmış,
                <b>{len(delivered_today)}</b> cihaz teslim/iade teslim edilmiş.
            </p>
            <p>
                Teslim bekleyen <b>{len(delivery_waiting)}</b> cihaz, iade teslimi bekleyen <b>{len(iade_waiting)}</b> cihaz,
                müşteri onayı bekleyen <b>{len(approval_waiting)}</b> kayıt ve ödemesi tamamlanmamış <b>{len(unpaid)}</b> kayıt var.
            </p>
            <p>
                Bugünkü kasa hareketi: giriş <b>{format_money(income, '₺')}</b>, çıkış <b>{format_money(expense, '₺')}</b>,
                net <b>{format_money(net_cash, '₺')}</b>.
            </p>
            <p><b>En sık arızalar:</b> {top_faults_text}</p>
            <p><b>Kritik stok:</b> {len(low_stock_items)} kalem. {low_stock_names}</p>
            <p><b>Açık bayi kayıtları:</b> {dealer_open}</p>
            <p><b>Önerilen öncelik:</b> {priority_text}.</p>
            <p style='color:#64748b; font-size:12px;'>
                Deneme modu: Bu özet AI API kullanmadan, sadece ekranda yüklü mevcut verilerden oluşturuldu. Firebase'e ekstra veri yazmaz.
            </p>
        </div>
        """

    def show_smart_management_summary(self):
        try:
            dlg = ReadOnlyDialog("Akıllı Yönetici Özeti", self.build_smart_management_summary(), self)
            dlg.resize(720, 620)
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Akıllı Özet", f"Özet oluşturulamadı:\n{exc}")

    def filtered_management_priority_items(self, level_filter="Tümü", category_filter="Tümü"):
        items = self.collect_notification_items()
        if level_filter and level_filter != "Tümü":
            items = [item for item in items if item.get("level") == level_filter]
        if category_filter and category_filter != "Tümü":
            items = [item for item in items if item.get("category") == category_filter]
        return items

    def make_priority_stat_label(self, title, count, color):
        label = QLabel(f"<span style='font-size:12px; color:#94a3b8;'>{title}</span><br><b style='font-size:22px; color:{color};'>{count}</b>")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumHeight(62)
        label.setStyleSheet("""
            QLabel {
                background:#111827;
                border:1px solid #273449;
                border-radius:8px;
                padding:8px 12px;
            }
        """)
        return label

    def show_management_priorities(self):
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("Yönetim Öncelikleri")
            dlg.resize(1040, 680)
            lay = QVBoxLayout(dlg)
            title = QLabel("<b>Yönetim Öncelikleri</b>")
            title.setStyleSheet("font-size:18px; color:#60a5fa;")
            subtitle = QLabel("Mevcut yüklü veriden oluşturulur; Firebase'e ekstra okuma/yazma yapmaz.")
            subtitle.setStyleSheet("color:#94a3b8; font-size:12px;")
            stat_row = QHBoxLayout()
            all_items = self.collect_notification_items()
            stat_critical = self.make_priority_stat_label("Kritik", 0, "#ef4444")
            stat_warning = self.make_priority_stat_label("Uyarı", 0, "#f59e0b")
            stat_info = self.make_priority_stat_label("Bilgi", 0, "#38bdf8")
            stat_total = self.make_priority_stat_label("Gösterilen", 0, "#e2e8f0")
            for widget in [stat_critical, stat_warning, stat_info, stat_total]:
                stat_row.addWidget(widget)

            filter_row = QHBoxLayout()
            level_filter = QComboBox()
            level_filter.addItems(["Tümü", "Kritik", "Uyarı", "Bilgi"])
            category_filter = QComboBox()
            categories = sorted({
                str(item.get("category", "") or "Diğer")
                for item in all_items
            })
            category_filter.addItems(["Tümü"] + categories)
            btn_notifications = QPushButton("Bildirim Merkezi")
            btn_close = QPushButton("Kapat")
            table = QTableWidget(0, 5)
            table.setHorizontalHeaderLabels(["Öncelik", "Kategori", "Başlık", "Detay", "Tarih"])
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            table.verticalHeader().setVisible(False)
            table.setShowGrid(False)
            table.setAlternatingRowColors(False)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setWordWrap(True)
            table.setStyleSheet("""
                QTableWidget {
                    background:#0f172a;
                    color:#f8fafc;
                    border:1px solid #334155;
                    border-radius:8px;
                    gridline-color:#1e293b;
                    font-size:13px;
                }
                QTableWidget::item {
                    border-bottom:1px solid #1e293b;
                    padding:8px;
                }
                QTableWidget::item:selected {
                    background:#1d4ed8;
                    color:white;
                }
                QHeaderView::section {
                    background:#111827;
                    color:#cbd5e1;
                    border:0;
                    border-bottom:1px solid #334155;
                    padding:9px 8px;
                    font-weight:bold;
                }
            """)
            level_colors = {"Kritik": "#ef4444", "Uyarı": "#f59e0b", "Bilgi": "#38bdf8"}
            level_bg = {"Kritik": "#1f1219", "Uyarı": "#211b10", "Bilgi": "#0f2130"}
            level_soft = {"Kritik": "#34151d", "Uyarı": "#302513", "Bilgi": "#102a3d"}

            def set_cell(row, col, text, item_data=None, fg="#f8fafc", bg=None, bold=False):
                cell = QTableWidgetItem(str(text or ""))
                cell.setData(Qt.ItemDataRole.UserRole, item_data)
                cell.setForeground(QColor(fg))
                if bg:
                    cell.setBackground(QColor(bg))
                if bold:
                    font = cell.font()
                    font.setBold(True)
                    cell.setFont(font)
                table.setItem(row, col, cell)
                return cell

            def refresh_priorities():
                filtered = self.filtered_management_priority_items(level_filter.currentText(), category_filter.currentText())
                table.setRowCount(0)
                stat_critical.setText(f"<span style='font-size:12px; color:#94a3b8;'>Kritik</span><br><b style='font-size:22px; color:#ef4444;'>{sum(1 for item in all_items if item.get('level') == 'Kritik')}</b>")
                stat_warning.setText(f"<span style='font-size:12px; color:#94a3b8;'>Uyarı</span><br><b style='font-size:22px; color:#f59e0b;'>{sum(1 for item in all_items if item.get('level') == 'Uyarı')}</b>")
                stat_info.setText(f"<span style='font-size:12px; color:#94a3b8;'>Bilgi</span><br><b style='font-size:22px; color:#38bdf8;'>{sum(1 for item in all_items if item.get('level') == 'Bilgi')}</b>")
                stat_total.setText(f"<span style='font-size:12px; color:#94a3b8;'>Gösterilen</span><br><b style='font-size:22px; color:#e2e8f0;'>{len(filtered)}</b>")

                for level in ["Kritik", "Uyarı", "Bilgi"]:
                    group_items = [item for item in filtered if item.get("level") == level]
                    if not group_items:
                        continue
                    header_row = table.rowCount()
                    table.insertRow(header_row)
                    table.setSpan(header_row, 0, 1, 5)
                    header = QTableWidgetItem(f"{level} - {len(group_items)} kayıt")
                    header.setForeground(QColor(level_colors.get(level, "#94a3b8")))
                    header.setBackground(QColor(level_bg.get(level, "#111827")))
                    font = header.font()
                    font.setBold(True)
                    header.setFont(font)
                    header.setData(Qt.ItemDataRole.UserRole, None)
                    table.setItem(header_row, 0, header)
                    table.setRowHeight(header_row, 34)

                    for item_data in group_items:
                        row = table.rowCount()
                        table.insertRow(row)
                        color = level_colors.get(level, "#94a3b8")
                        set_cell(row, 0, f"  {level}  ", item_data, color, level_soft.get(level), True)
                        set_cell(row, 1, item_data.get("category", ""), item_data, "#cbd5e1", None, True)
                        set_cell(row, 2, item_data.get("title", ""), item_data, "#f8fafc", None, True)
                        set_cell(row, 3, item_data.get("detail", ""), item_data, "#cbd5e1")
                        set_cell(row, 4, item_data.get("date", ""), item_data, "#94a3b8")
                        table.setRowHeight(row, 42)

                if not filtered:
                    row = table.rowCount()
                    table.insertRow(row)
                    table.setSpan(row, 0, 1, 5)
                    set_cell(row, 0, "Seçili filtrelerde takip gerektiren kayıt görünmüyor.", None, "#22c55e", "#10251c", True)
                    table.setRowHeight(row, 54)

            level_filter.currentTextChanged.connect(refresh_priorities)
            category_filter.currentTextChanged.connect(refresh_priorities)
            btn_notifications.clicked.connect(lambda: (dlg.accept(), self.show_notification_center()))
            btn_close.clicked.connect(dlg.accept)
            table.cellDoubleClicked.connect(lambda row, col: self.open_notification_item(table.item(row, 0).data(Qt.ItemDataRole.UserRole), dlg) if table.item(row, 0) and table.item(row, 0).data(Qt.ItemDataRole.UserRole) else None)
            filter_row.addWidget(QLabel("Öncelik:"))
            filter_row.addWidget(level_filter)
            filter_row.addWidget(QLabel("Kategori:"))
            filter_row.addWidget(category_filter)
            filter_row.addStretch()
            filter_row.addWidget(btn_notifications)
            filter_row.addWidget(btn_close)
            lay.addWidget(title)
            lay.addWidget(subtitle)
            lay.addLayout(stat_row)
            lay.addLayout(filter_row)
            lay.addWidget(table, 1)
            refresh_priorities()
            dlg.exec()
        except Exception as exc:
            QMessageBox.warning(self, "Yönetim Öncelikleri", f"Öncelikler oluşturulamadı:\n{exc}")

    def on_rates_fetched(self, usd, eur):
        self.usd_rate = usd
        self.eur_rate = eur
        self.update_ticker()

    def is_firebase_auth_error(self, error):
        text = str(error)
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        return (
            status_code in [401, 402, 403]
            or "401 Client Error" in text
            or "402 Client Error" in text
            or "403 Client Error" in text
            or "Permission denied" in text
            or "Unauthorized" in text
            or "auth token" in text.lower()
        )

    def refresh_firebase_token(self):
        if not getattr(self, "refresh_token", ""):
            return False
        try:
            refreshed = auth.refresh(self.refresh_token)
            self.token = refreshed.get("idToken", self.token)
            self.refresh_token = refreshed.get("refreshToken", self.refresh_token)
            self._last_token_refresh = datetime.datetime.now()
            self.set_sync_status(f"Oturum yenilendi - {self._last_token_refresh.strftime('%H:%M:%S')}", "#38bdf8")
            if getattr(self, "stream_worker", None):
                QTimer.singleShot(0, self.restart_firebase_stream)
            return bool(self.token)
        except Exception:
            return False

    def ensure_firebase_session(self, force=False):
        last_refresh = getattr(self, "_last_token_refresh", None)
        if not force and last_refresh and (datetime.datetime.now() - last_refresh).total_seconds() < 45 * 60:
            return True
        ok = self.refresh_firebase_token()
        if not ok:
            self.set_sync_status("Oturum yenilenemedi", "#ef4444")
        return ok

    def handle_refresh_error(self, error, retried=False):
        if self.is_firebase_auth_error(error):
            if not retried and self.refresh_firebase_token():
                self.set_sync_status("Oturum yenilendi, veriler tekrar alınıyor", "#38bdf8")
                QTimer.singleShot(500, lambda: self.refresh_all_tables(retried=True))
            else:
                self.set_sync_status("Oturum yenilenemedi, tekrar giriş gerekebilir", "#ef4444")
                QMessageBox.warning(
                    self,
                    "Bağlantı Hatası",
                    "Firebase oturumu yenilenemedi.\n\n"
                    "İnternet bağlantısını kontrol edin. Devam ederse çıkış yapıp tekrar giriş yapın."
                )
            return
        self.set_sync_status("Bağlantı hatası", "#ef4444")
        QMessageBox.warning(self, "Bağlantı Hatası", describe_connection_error(error))

    def local_cache_dir(self):
        base_dir = (
            os.environ.get("LOCALAPPDATA")
            or os.path.join(os.path.expanduser("~"), "AppData", "Local")
            or tempfile.gettempdir()
        )
        user_hash = hashlib.sha256(str(getattr(self, "user_id", "") or "unknown").encode("utf-8")).hexdigest()[:24]
        return os.path.join(base_dir, "MetaFold", "Servis", "cache", user_hash)

    def local_cache_path(self, section_name):
        clean_section = re.sub(r"[^A-Za-z0-9_-]+", "_", str(section_name or "section")).strip("_") or "section"
        return os.path.join(self.local_cache_dir(), f"{clean_section}.json")

    def data_cache_path(self):
        return os.path.join(self.local_cache_dir(), LOCAL_CACHE_AGGREGATE_FILE)

    def download_usage_path(self):
        return os.path.join(self.local_cache_dir(), DOWNLOAD_USAGE_FILE)

    def format_data_size(self, byte_count):
        size = float(safe_float(byte_count, 0))
        units = ["B", "KB", "MB", "GB", "TB"]
        idx = 0
        while size >= 1024 and idx < len(units) - 1:
            size /= 1024.0
            idx += 1
        if idx == 0:
            return f"{int(size)} {units[idx]}"
        return f"{size:.2f} {units[idx]}"

    def load_download_usage(self):
        try:
            path = self.download_usage_path()
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def save_download_usage(self, payload):
        if not isinstance(payload, dict):
            return
        tmp_path = ""
        try:
            cache_dir = self.local_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            payload.setdefault("schema", 1)
            payload.setdefault("user_id", self.user_id)
            payload["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            fd, tmp_path = tempfile.mkstemp(prefix="download_usage_", suffix=".tmp", dir=cache_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp_path, self.download_usage_path())
        except Exception:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def record_download_usage(self, source, payload=None, bytes_count=None, detail=""):
        try:
            if bytes_count is None:
                bytes_count = estimate_json_bytes(payload)
            bytes_count = int(max(0, safe_float(bytes_count, 0)))
            if bytes_count <= 0:
                return

            self.download_session_bytes = int(getattr(self, "download_session_bytes", 0)) + bytes_count
            usage = self.load_download_usage()
            if not isinstance(usage, dict):
                usage = {}
            now = datetime.datetime.now()
            today_key = now.strftime("%Y-%m-%d")

            usage.setdefault("created_at", now.isoformat(timespec="seconds"))
            usage["user_id"] = self.user_id
            usage["user_email"] = getattr(self, "user_email", "")
            usage["total_bytes"] = int(safe_float(usage.get("total_bytes", 0))) + bytes_count
            usage["last_source"] = str(source or "unknown")
            usage["last_detail"] = str(detail or "")
            usage["last_bytes"] = bytes_count
            usage["last_at"] = now.isoformat(timespec="seconds")

            daily = safe_dict_parse(usage.get("daily", {}))
            if not isinstance(daily, dict):
                daily = {}
            daily[today_key] = int(safe_float(daily.get(today_key, 0))) + bytes_count
            keep_after = (now - datetime.timedelta(days=60)).strftime("%Y-%m-%d")
            usage["daily"] = {k: v for k, v in daily.items() if str(k) >= keep_after}

            sources = safe_dict_parse(usage.get("sources", {}))
            if not isinstance(sources, dict):
                sources = {}
            src_key = re.sub(r"[^A-Za-z0-9:_-]+", "_", str(source or "unknown")).strip("_") or "unknown"
            src = safe_dict_parse(sources.get(src_key, {}))
            if not isinstance(src, dict):
                src = {}
            src["bytes"] = int(safe_float(src.get("bytes", 0))) + bytes_count
            src["count"] = int(safe_float(src.get("count", 0))) + 1
            src["last_at"] = now.isoformat(timespec="seconds")
            src["last_detail"] = str(detail or "")
            sources[src_key] = src
            usage["sources"] = sources

            self.save_download_usage(usage)
        except Exception:
            pass

    def show_download_usage_dialog(self):
        usage = self.load_download_usage()
        if not isinstance(usage, dict):
            usage = {}
        total_bytes = int(safe_float(usage.get("total_bytes", 0)))
        session_bytes = int(getattr(self, "download_session_bytes", 0))
        today_key = datetime.datetime.now().strftime("%Y-%m-%d")
        daily = safe_dict_parse(usage.get("daily", {}))
        if not isinstance(daily, dict):
            daily = {}
        today_bytes = int(safe_float(daily.get(today_key, 0)))
        last_bytes = int(safe_float(usage.get("last_bytes", 0)))
        last_at = html.escape(str(usage.get("last_at", "-") or "-"))
        last_source = html.escape(str(usage.get("last_source", "-") or "-"))
        last_detail = html.escape(str(usage.get("last_detail", "") or ""))
        path_text = html.escape(self.download_usage_path())

        sources = safe_dict_parse(usage.get("sources", {}))
        if not isinstance(sources, dict):
            sources = {}
        rows = []
        for source, info in sorted(sources.items(), key=lambda item: int(safe_float(item[1].get("bytes", 0))) if isinstance(item[1], dict) else 0, reverse=True):
            if not isinstance(info, dict):
                continue
            rows.append(
                "<tr>"
                f"<td>{html.escape(str(source))}</td>"
                f"<td style='text-align:right; font-weight:800;'>{self.format_data_size(info.get('bytes', 0))}</td>"
                f"<td style='text-align:right;'>{int(safe_float(info.get('count', 0)))}</td>"
                f"<td>{html.escape(str(info.get('last_detail', '') or ''))}</td>"
                "</tr>"
            )
        source_rows = "".join(rows) or "<tr><td colspan='4'>Henuz bulut indirme kaydi yok.</td></tr>"

        html_body = f"""
        <div style='font-family:Segoe UI, Arial; line-height:1.45;'>
            <h2>Gizli Veri Indirme Sayaci</h2>
            <p style='color:#94a3b8;'>Bu ekran sadece programin yerel sayacidir. Firebase'e yazmaz, database'e mudahele etmez.</p>
            <table width='100%' cellspacing='0' cellpadding='8' border='1'>
                <tr><th>Olcum</th><th>Deger</th></tr>
                <tr><td>Toplam indirilen</td><td><b>{self.format_data_size(total_bytes)}</b></td></tr>
                <tr><td>Bu oturum</td><td><b>{self.format_data_size(session_bytes)}</b></td></tr>
                <tr><td>Bugun</td><td><b>{self.format_data_size(today_bytes)}</b></td></tr>
                <tr><td>Son indirme</td><td>{self.format_data_size(last_bytes)} - {last_source} {last_detail}</td></tr>
                <tr><td>Son zaman</td><td>{last_at}</td></tr>
            </table>
            <h3>Kaynak kirilimi</h3>
            <table width='100%' cellspacing='0' cellpadding='8' border='1'>
                <tr><th>Kaynak</th><th>Boyut</th><th>Adet</th><th>Detay</th></tr>
                {source_rows}
            </table>
            <p style='font-size:12px; color:#94a3b8;'>Sayaç dosyasi: {path_text}</p>
            <p style='font-size:12px; color:#94a3b8;'>Not: Bu degerler indirilen JSON iceriginin yaklasik boyutudur; Firebase faturasindaki protokol/stream ekleri birebir ayni olmayabilir.</p>
        </div>
        """
        dlg = ReadOnlyDialog("Veri Indirme Sayaci", html_body, self)
        dlg.resize(760, 560)
        dlg.exec()

    def load_data_cache(self):
        try:
            path = self.data_cache_path()
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def save_data_cache(self, payload):
        if not isinstance(payload, dict):
            return
        tmp_path = ""
        try:
            cache_dir = self.local_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            payload.setdefault("schema", LOCAL_CACHE_SCHEMA_VERSION)
            payload.setdefault("app_version", MEVCUT_SURUM)
            payload.setdefault("user_id", self.user_id)
            payload["updated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            fd, tmp_path = tempfile.mkstemp(prefix="data_cache_", suffix=".tmp", dir=cache_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp_path, self.data_cache_path())
        except Exception:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def data_cache_sections(self):
        payload = self.load_data_cache()
        sections = safe_dict_parse(payload.get("sections", {}) if isinstance(payload, dict) else {})
        return sections if isinstance(sections, dict) else {}

    def data_cache_has_any_data(self):
        sections = self.data_cache_sections()
        return any(isinstance(value, dict) and len(value) > 0 for value in sections.values())

    def data_cache_section_exists(self, section_name):
        sections = self.data_cache_sections()
        return section_name in sections and isinstance(sections.get(section_name), dict)

    def read_data_cache_section(self, section_name, default=None):
        default = {} if default is None else default
        sections = self.data_cache_sections()
        data = safe_dict_parse(sections.get(section_name, default))
        return data if isinstance(data, dict) else default

    def write_data_cache_section(self, section_name, data, cloud_synced=False):
        if section_name not in LOCAL_CACHE_SECTIONS or not isinstance(data, dict):
            return
        payload = self.load_data_cache()
        if not isinstance(payload, dict):
            payload = {}
        sections = safe_dict_parse(payload.get("sections", {}))
        if not isinstance(sections, dict):
            sections = {}
        sections[section_name] = data
        payload["sections"] = sections
        if cloud_synced:
            payload["cloud_synced_at_ms"] = self.current_sync_ms()
        else:
            payload.setdefault("cloud_synced_at_ms", int(safe_float(payload.get("cloud_synced_at_ms", 0))))
        self.save_data_cache(payload)

    def current_sync_ms(self):
        return int(time.time() * 1000)

    def read_cached_payload(self, section_name):
        try:
            path = self.local_cache_path(section_name)
            if not os.path.exists(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def cached_section_age_seconds(self, section_name):
        try:
            path = self.local_cache_path(section_name)
            if not os.path.exists(path):
                return None
            return max(0.0, time.time() - os.path.getmtime(path))
        except Exception:
            return None

    def cloud_refresh_due(self, section_name="kayitlar"):
        age = self.cached_section_age_seconds(section_name)
        if age is None:
            return True
        return age >= LOCAL_CACHE_CLOUD_REFRESH_SECONDS

    def schedule_background_cloud_refresh_if_due(self):
        if getattr(self, "_background_cloud_refresh_scheduled", False):
            return
        if not self.cloud_refresh_due("kayitlar"):
            return
        if not self.firebase_connection_available(timeout=0.4):
            return
        self._background_cloud_refresh_scheduled = True
        QTimer.singleShot(12000, self.run_background_cloud_refresh)

    def run_background_cloud_refresh(self):
        self._background_cloud_refresh_scheduled = False
        if getattr(self, "_refreshing_tables", False):
            self._scheduled_refresh_prefer_cache = True
            self._scheduled_refresh_force_cloud = False
            self.refresh_timer.start(2500)
            return
        self.refresh_all_tables(prefer_cache=True)

    def read_cached_section(self, section_name, default=None):
        default = {} if default is None else default
        try:
            if self.data_cache_section_exists(section_name):
                return self.read_data_cache_section(section_name, default=default)
            payload = self.read_cached_payload(section_name)
            if not payload:
                return default
            data = payload.get("data", {}) if isinstance(payload, dict) else {}
            data = safe_dict_parse(data or {})
            if isinstance(data, dict):
                self.write_data_cache_section(section_name, data)
                return data
            return default
        except Exception:
            return default

    def cached_section_cloud_sync_ms(self, section_name):
        aggregate_ms = 0
        try:
            aggregate = self.load_data_cache()
            if isinstance(aggregate, dict):
                aggregate_ms = int(safe_float(aggregate.get("cloud_synced_at_ms", 0)))
        except Exception:
            aggregate_ms = 0
        payload = self.read_cached_payload(section_name)
        try:
            section_ms = int(safe_float(payload.get("cloud_synced_at_ms", 0)))
        except Exception:
            section_ms = 0
        return max(aggregate_ms, section_ms)

    def write_cached_section(self, section_name, data, cloud_synced=False):
        if section_name not in LOCAL_CACHE_SECTIONS or not isinstance(data, dict):
            return
        tmp_path = ""
        try:
            cache_dir = self.local_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            previous = self.read_cached_payload(section_name)
            previous_sync_ms = int(safe_float(previous.get("cloud_synced_at_ms", 0))) if isinstance(previous, dict) else 0
            payload = {
                "schema": LOCAL_CACHE_SCHEMA_VERSION,
                "section": section_name,
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "cloud_synced_at_ms": self.current_sync_ms() if cloud_synced else previous_sync_ms,
                "app_version": MEVCUT_SURUM,
                "data": data,
            }
            fd, tmp_path = tempfile.mkstemp(prefix=f"{section_name}_", suffix=".tmp", dir=cache_dir)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp_path, self.local_cache_path(section_name))
            self.write_data_cache_section(section_name, data, cloud_synced=cloud_synced)
        except Exception:
            try:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def firebase_get_user_section_rest(self, section_name, params=None, retried=False):
        db_url = get_firebase_config().get("databaseURL", "").rstrip("/")
        url = f"{db_url}/users/{self.user_id}/{section_name}.json"
        query = dict(params or {})
        query["auth"] = self.token
        response = requests.get(url, params=query, timeout=10)
        if response.status_code in [401, 402, 403] and not retried and self.refresh_firebase_token():
            return self.firebase_get_user_section_rest(section_name, params=params, retried=True)
        response.raise_for_status()
        self.record_download_usage(f"rest:{section_name}", bytes_count=len(response.content or b""), detail="REST okuma")
        return response.json() or {}

    def read_recent_cloud_records(self):
        try:
            return safe_dict_parse(self.firebase_get_user_section_rest("kayitlar", {
                "orderBy": json.dumps("$key"),
                "limitToLast": LOCAL_CACHE_RECENT_RECORD_LIMIT,
            }) or {})
        except Exception:
            return {}

    def read_changed_cloud_records(self):
        last_sync_ms = self.cached_section_cloud_sync_ms("kayitlar")
        if last_sync_ms <= 0:
            return {}
        start_at = max(0, last_sync_ms - LOCAL_CACHE_SYNC_LOOKBACK_MS)
        try:
            return safe_dict_parse(self.firebase_get_user_section_rest("kayitlar", {
                "orderBy": json.dumps("updated_at_ms"),
                "startAt": start_at,
                "limitToLast": LOCAL_CACHE_CHANGED_RECORD_LIMIT,
            }) or {})
        except Exception:
            return {}

    def merge_cloud_records_into_cache(self, cached_records, cloud_records):
        data = safe_dict_parse(cached_records or {})
        if not isinstance(data, dict):
            data = {}
        incoming = safe_dict_parse(cloud_records or {})
        if not isinstance(incoming, dict):
            return data
        for key, value in incoming.items():
            if value is None:
                data.pop(key, None)
            elif isinstance(value, dict):
                data[key] = value
        return data

    def read_cached_records_with_cloud_delta(self, default=None):
        cached = self.read_cached_section("kayitlar", default=default or {})
        if not isinstance(cached, dict):
            cached = {}
        merged = dict(cached)
        changed = self.read_changed_cloud_records()
        recent = self.read_recent_cloud_records()
        if changed:
            merged = self.merge_cloud_records_into_cache(merged, changed)
        if recent:
            merged = self.merge_cloud_records_into_cache(merged, recent)
        if changed or recent:
            self.write_cached_section("kayitlar", merged, cloud_synced=True)
        return merged

    def read_user_section(self, section_name, default=None, retried=False, prefer_cache=None, force_cloud=None):
        default = {} if default is None else default
        if prefer_cache is None:
            prefer_cache = bool(getattr(self, "_refresh_prefer_cache", False))
        if force_cloud is None:
            force_cloud = bool(getattr(self, "_refresh_force_cloud", False))
        if getattr(self, "_cache_only_refresh", False):
            if self.has_cached_section(section_name):
                cached = self.read_cached_section(section_name, default=default)
                if getattr(self, "_cache_boot_refresh", False):
                    self._cache_preferred_sections.add(section_name)
                    self._read_only_cache_mode = False
                    self.update_connection_badge(True, "Yerel cache kullanılıyor")
                else:
                    self._cache_fallback_sections.add(section_name)
                    self._read_only_cache_mode = True
                    self.update_connection_badge(False)
                return cached
            return default
        cache_first_section = prefer_cache and not force_cloud and section_name in LOCAL_CACHE_SECTIONS and self.has_cached_section(section_name)
        if cache_first_section:
            cached = self.read_cached_section(section_name, default=default)
            self._cache_preferred_sections.add(section_name)
            self.update_connection_badge(True, "Yerel kopya kullanılıyor")
            return cached
        try:
            raw = db.child("users").child(self.user_id).child(section_name).get(self.token).val()
            self.record_download_usage(f"section:{section_name}", payload=raw, detail="Firebase bolum okuma")
            data = safe_dict_parse(raw or {})
            if not isinstance(data, dict):
                data = default
            self.write_cached_section(section_name, data, cloud_synced=True)
            self._read_only_cache_mode = False
            self.update_connection_badge(True, "Firebase bağlantısı aktif")
            return data
        except Exception as error:
            if self.is_firebase_auth_error(error) and not retried and self.refresh_firebase_token():
                return self.read_user_section(section_name, default=default, retried=True)
            if self.has_cached_section(section_name):
                cached = self.read_cached_section(section_name, default=default)
                self._cache_fallback_sections.add(section_name)
                self._read_only_cache_mode = True
                self.update_connection_badge(False)
                return cached
            raise

    def has_cached_section(self, section_name):
        try:
            return self.data_cache_section_exists(section_name) or os.path.exists(self.local_cache_path(section_name))
        except Exception:
            return False

    def firebase_connection_host(self):
        try:
            cfg = get_firebase_config()
            host = urllib.parse.urlparse(str(cfg.get("databaseURL", "") or "")).hostname
            return host or "metafold-teknik-servis-default-rtdb.europe-west1.firebasedatabase.app"
        except Exception:
            return "metafold-teknik-servis-default-rtdb.europe-west1.firebasedatabase.app"

    def firebase_connection_available(self, timeout=1.0):
        try:
            host = self.firebase_connection_host()
            with socket.create_connection((host, 443), timeout=float(timeout or 1.0)):
                return True
        except Exception:
            return False

    def connection_error_message(self, action_label):
        return (
            f"{action_label} yapılamadı çünkü Firebase bağlantısı yok.\n\n"
            "İnternet bağlantısı gelene kadar program son yerel kopyayı görüntüleyebilir, "
            "ancak yeni kayıt, düzenleme, silme, ödeme ve stok işlemleri yapılmaz.\n\n"
            "Bağlantıyı kontrol edip tekrar deneyin."
        )

    def ensure_write_connection(self, action_label="İşlem"):
        if getattr(self, "_read_only_cache_mode", False):
            if self.firebase_connection_available(timeout=0.9):
                self._read_only_cache_mode = False
            else:
                self.set_sync_status("Yerel kopya modu - işlem kapalı", "#f59e0b")
                self.update_connection_badge(False)
                QMessageBox.warning(self, "Bağlantı Yok", self.connection_error_message(action_label))
                return False
        if not self.firebase_connection_available(timeout=0.9):
            self._read_only_cache_mode = True
            self.set_sync_status("Yerel kopya modu - işlem kapalı", "#f59e0b")
            self.update_connection_badge(False)
            QMessageBox.warning(self, "Bağlantı Yok", self.connection_error_message(action_label))
            return False
        self.update_connection_badge(True, "Firebase bağlantısı aktif")
        return True

    def friendly_write_error(self, action_label, error):
        text = str(error)
        lowered = text.lower()
        network_markers = [
            "failed to establish",
            "max retries",
            "getaddrinfo",
            "connection",
            "timeout",
            "network is unreachable",
            "temporary failure",
            "name resolution",
        ]
        if any(marker in lowered for marker in network_markers):
            self._read_only_cache_mode = True
            self.set_sync_status("Yerel kopya modu - işlem kapalı", "#f59e0b")
            self.update_connection_badge(False)
            return self.connection_error_message(action_label)
        if self.is_firebase_auth_error(error):
            return (
                f"{action_label} yapılamadı çünkü Firebase oturumu doğrulanamadı.\n\n"
                "Program oturumu yenilemeyi denedi. Bağlantı geldikten sonra tekrar deneyin."
            )
        return f"{action_label} tamamlanamadı:\n{describe_connection_error(error)}"

    def trigger_debounce_refresh(self): 
        if getattr(self, "_refreshing_tables", False):
            self._refresh_requested = True
            return
        self._scheduled_refresh_force_cloud = False
        self._scheduled_refresh_prefer_cache = True
        self.set_sync_status("Yeni kayıtlar kontrol ediliyor", "#f59e0b")
        self.refresh_timer.start(800)

    def run_scheduled_refresh(self):
        force_cloud = bool(getattr(self, "_scheduled_refresh_force_cloud", False))
        prefer_cache = bool(getattr(self, "_scheduled_refresh_prefer_cache", True)) and not force_cloud
        self._scheduled_refresh_force_cloud = False
        self._scheduled_refresh_prefer_cache = True
        self.refresh_all_tables(prefer_cache=prefer_cache, force_cloud=force_cloud)

    def load_initial_tables_from_cache_or_cloud(self):
        cache_ready = self.data_cache_has_any_data() or self.has_cached_section("kayitlar")
        if cache_ready:
            self._cache_only_refresh = True
            self._cache_boot_refresh = True
            try:
                self.refresh_all_tables(prefer_cache=True, force_cloud=False)
            finally:
                self._cache_only_refresh = False
                self._cache_boot_refresh = False
            return
        self.refresh_all_tables(force_cloud=True)

    def start_firebase_stream(self):
        if getattr(self, "stream_worker", None):
            return
        if not getattr(self, "user_id", "") or not getattr(self, "token", ""):
            return
        worker = FirebaseRecordStreamWorker(self.user_id, self.token, self)
        worker.stream_event.connect(self.update_ui_from_stream)
        worker.stream_status.connect(self.handle_stream_status)
        self.stream_worker = worker
        worker.start()

    def stop_firebase_stream(self):
        worker = getattr(self, "stream_worker", None)
        if not worker:
            return
        try:
            worker.stream_event.disconnect(self.update_ui_from_stream)
        except Exception:
            pass
        try:
            worker.stream_status.disconnect(self.handle_stream_status)
        except Exception:
            pass
        worker.stop()
        worker.quit()
        worker.wait(1500)
        self.stream_worker = None

    def restart_firebase_stream(self):
        self.stop_firebase_stream()
        self.start_firebase_stream()

    def handle_stream_status(self, text, online):
        self.update_connection_badge(bool(online), text)
        if online:
            self.set_sync_status(text or "Canlı dinleyici aktif", "#22c55e")
        else:
            self.set_sync_status("Canlı dinleyici beklemede", "#f59e0b")

    def mark_records_cache_synced(self, sync_ms=None):
        sync_ms = int(safe_float(sync_ms, 0)) or self.current_sync_ms()
        try:
            payload = self.load_data_cache()
            if not isinstance(payload, dict):
                payload = {}
            previous_ms = int(safe_float(payload.get("cloud_synced_at_ms", 0)))
            payload["cloud_synced_at_ms"] = max(previous_ms, sync_ms)
            self.save_data_cache(payload)
        except Exception:
            pass

        try:
            path = self.local_cache_path("kayitlar")
            payload = self.read_cached_payload("kayitlar")
            if not isinstance(payload, dict):
                payload = {}
            data = safe_dict_parse(payload.get("data", {}))
            if not isinstance(data, dict):
                data = self.read_data_cache_section("kayitlar", default={})
            previous_ms = int(safe_float(payload.get("cloud_synced_at_ms", 0)))
            payload.update({
                "schema": LOCAL_CACHE_SCHEMA_VERSION,
                "section": "kayitlar",
                "updated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "cloud_synced_at_ms": max(previous_ms, sync_ms),
                "app_version": MEVCUT_SURUM,
                "data": data if isinstance(data, dict) else {},
            })
            cache_dir = self.local_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(prefix="kayitlar_sync_", suffix=".tmp", dir=cache_dir)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp_path, path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception:
            pass

    def touch_record_sync_meta(self, kid, action="upsert", changed_at_ms=None):
        if not kid or not getattr(self, "user_id", "") or not getattr(self, "token", ""):
            return False
        changed_ms = int(safe_float(changed_at_ms, 0)) or self.current_sync_ms()
        action = "delete" if str(action or "").lower() == "delete" else "upsert"
        latest = {
            "last_changed_at_ms": changed_ms,
            "last_changed_id": str(kid),
            "last_action": action,
            "source": "desktop",
            "source_session": getattr(self, "sync_session_id", ""),
        }
        try:
            meta_ref = db.child("users").child(self.user_id).child("sync_meta").child("kayitlar")
            if action == "delete":
                meta_ref.child("deleted_ids").child(str(kid)).set(changed_ms, self.token)
                try:
                    meta_ref.child("changed_ids").child(str(kid)).remove(self.token)
                except Exception:
                    pass
            else:
                meta_ref.child("changed_ids").child(str(kid)).set(changed_ms, self.token)
            meta_ref.child("latest").set(latest, self.token)
            self.mark_records_cache_synced(changed_ms)
            return True
        except Exception:
            return False

    def handle_sync_meta_event(self, stream_data):
        if not isinstance(stream_data, dict):
            return True
        event = str(stream_data.get("event", "") or "")
        if event not in ("put", "patch"):
            return True

        path = str(stream_data.get("path", "/") or "/")
        payload = stream_data.get("data")
        meta = safe_dict_parse(getattr(self, "_last_sync_meta", {}))
        if not isinstance(meta, dict):
            meta = {}

        if path == "/":
            if payload is None:
                return True
            incoming = safe_dict_parse(payload or {})
            if not isinstance(incoming, dict):
                return True
            meta.update(incoming)
        else:
            key = path.strip("/")
            if key:
                if payload is None:
                    meta.pop(key, None)
                else:
                    meta[key] = payload

        self._last_sync_meta = dict(meta)
        remote_ms = int(safe_float(meta.get("last_changed_at_ms", 0)))
        if remote_ms <= 0 or not meta.get("last_changed_id"):
            return True

        if str(meta.get("source_session", "") or "") == str(getattr(self, "sync_session_id", "") or ""):
            self.mark_records_cache_synced(remote_ms)
            return True

        self.start_delta_fetch_for_meta(meta, latest_only=True)
        return True

    def start_delta_fetch_for_meta(self, latest_meta, latest_only=False):
        if not isinstance(latest_meta, dict):
            return
        remote_ms = int(safe_float(latest_meta.get("last_changed_at_ms", 0)))
        if remote_ms <= 0:
            return
        since_ms = self.cached_section_cloud_sync_ms("kayitlar")
        latest_id = str(latest_meta.get("last_changed_id", "") or "")
        if remote_ms <= since_ms and not (latest_only and latest_id):
            return
        worker_meta = dict(latest_meta)
        if latest_only:
            worker_meta["latest_only"] = True
            if remote_ms <= since_ms:
                signature = "|".join([
                    latest_id,
                    str(remote_ms),
                    str(worker_meta.get("last_action", "upsert") or "upsert"),
                    str(worker_meta.get("source_session", "") or ""),
                ])
                if signature == str(getattr(self, "_last_latest_only_signature", "") or ""):
                    return
                self._last_latest_only_signature = signature
                worker_meta["force_latest"] = True
        worker = getattr(self, "delta_fetch_worker", None)
        if worker and worker.isRunning():
            pending = getattr(self, "_pending_sync_meta", None)
            pending_ms = int(safe_float(pending.get("last_changed_at_ms", 0))) if isinstance(pending, dict) else 0
            if latest_only or remote_ms >= pending_ms:
                self._pending_sync_meta = dict(worker_meta)
            return
        worker = FirebaseDeltaFetchWorker(self.user_id, self.token, since_ms, worker_meta, self)
        worker.delta_fetched.connect(self.apply_delta_fetch_result)
        self.delta_fetch_worker = worker
        self.set_sync_status("Degisen kayitlar aliniyor", "#60a5fa")
        worker.start()

    def apply_delta_fetch_result(self, result):
        self.delta_fetch_worker = None
        if isinstance(result, dict):
            self.record_download_usage("delta:kayitlar", bytes_count=result.get("download_bytes", 0), detail="Degisen kayitlar")
        if not isinstance(result, dict) or not result.get("ok"):
            self.set_sync_status("Canli senkron beklemede", "#f59e0b")
            return

        changed = False
        deleted_ids = result.get("deleted", [])
        if isinstance(deleted_ids, list):
            for kid in deleted_ids:
                self.remove_record_from_stream(str(kid))
                changed = True

        records = safe_dict_parse(result.get("records", {}))
        if isinstance(records, dict):
            for kid, record in records.items():
                if isinstance(record, dict):
                    self.apply_stream_record_change(str(kid), record, replace=True)
                    changed = True

        latest_ms = int(safe_float(result.get("latest_ms", 0)))
        if latest_ms > 0:
            self.mark_records_cache_synced(latest_ms)

        if changed:
            self.refresh_record_views_after_stream()
        self.set_sync_status("Canli senkron aktif", "#22c55e")

        pending = getattr(self, "_pending_sync_meta", None)
        self._pending_sync_meta = None
        if isinstance(pending, dict):
            QTimer.singleShot(
                0,
                lambda meta=dict(pending): self.start_delta_fetch_for_meta(
                    meta,
                    latest_only=bool(meta.get("latest_only")),
                ),
            )

    def update_ui_from_stream(self, stream_data):
        if not isinstance(stream_data, dict):
            return
        self.record_download_usage("stream:sync_meta", payload=stream_data.get("data"), detail=str(stream_data.get("path", "/") or "/"))
        if self.handle_sync_meta_event(stream_data):
            return
        path = str(stream_data.get("path", "/") or "/")
        event = str(stream_data.get("event", "") or "")
        payload = stream_data.get("data")
        if event not in ("put", "patch"):
            return

        changed = False
        if path == "/":
            incoming = safe_dict_parse(payload or {})
            if not isinstance(incoming, dict):
                return
            for kid, record_payload in incoming.items():
                if record_payload is None:
                    self.remove_record_from_stream(str(kid))
                    changed = True
                elif isinstance(record_payload, dict):
                    self.apply_stream_record_change(str(kid), record_payload)
                    changed = True
        else:
            parts = [p for p in path.strip("/").split("/") if p]
            if not parts:
                return
            kid = parts[0]
            if len(parts) == 1:
                if payload is None:
                    self.remove_record_from_stream(kid)
                elif isinstance(payload, dict):
                    self.apply_stream_record_change(kid, payload)
                else:
                    return
            else:
                self.apply_stream_nested_change(kid, parts[1:], payload)
            changed = True

        if changed:
            self.refresh_record_views_after_stream()

    def apply_stream_record_change(self, kid, payload, replace=False):
        if not kid or not isinstance(payload, dict):
            return
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        if replace:
            current = dict(payload)
        else:
            current = safe_dict_parse(data.get(kid, {}))
            if not isinstance(current, dict):
                current = {}
            current.update(payload)
        current.setdefault("record_id", kid)
        data[kid] = current
        self.kayitlar_data = data
        self.write_cached_section("kayitlar", data, cloud_synced=False)
        self.upsert_record_row_from_cache(kid, current)

    def apply_stream_nested_change(self, kid, path_parts, payload):
        if not kid or not path_parts:
            return
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        record = safe_dict_parse(data.get(kid, {}))
        if not isinstance(record, dict):
            record = {}
        cursor = record
        for part in path_parts[:-1]:
            child = safe_dict_parse(cursor.get(part, {}))
            if not isinstance(child, dict):
                child = {}
            cursor[part] = child
            cursor = child
        last = path_parts[-1]
        if payload is None:
            cursor.pop(last, None)
        else:
            cursor[last] = payload
        record.setdefault("record_id", kid)
        data[kid] = record
        self.kayitlar_data = data
        self.write_cached_section("kayitlar", data, cloud_synced=False)
        self.upsert_record_row_from_cache(kid, record)

    def remove_record_from_stream(self, kid):
        if not kid:
            return
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        data.pop(kid, None)
        self.kayitlar_data = data
        self.write_cached_section("kayitlar", data, cloud_synced=False)
        self.remove_record_from_service_tables(kid)

    def find_record_row(self, table, kid):
        if not table or not kid:
            return -1
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and str(item.text()) == str(kid):
                return row
        return -1

    def remove_record_from_table(self, table, kid):
        row = self.find_record_row(table, kid)
        if row >= 0:
            table.removeRow(row)
            return True
        return False

    def remove_record_from_service_tables(self, kid):
        for table in [
            getattr(self, "table_act", None),
            getattr(self, "table_ready", None),
            getattr(self, "table_done", None),
            getattr(self, "table_delivered", None),
        ]:
            self.remove_record_from_table(table, kid)

    def set_table_row_data(self, table, row, row_data, colors=None):
        if row < 0 or not table:
            return
        for col, text in enumerate(row_data):
            item = QTableWidgetItem(str(text if text is not None else ""))
            item.setData(Qt.ItemDataRole.UserRole, str(row_data[0]))
            if colors and col < len(colors) and colors[col]:
                item.setForeground(colors[col])
            table.setItem(row, col, item)

    def apply_table_row_background(self, table, row, color):
        if not table or row < 0 or not color:
            return
        for col in range(table.columnCount()):
            item = table.item(row, col)
            if item:
                item.setBackground(color)

    def record_status_bucket(self, record):
        if not isinstance(record, dict):
            return None
        status = str(record.get("d", "") or "")
        waiting_statuses = ["İşlem Bekliyor", "Islem Bekliyor"]
        active_statuses = ["Tamirde", "Parça Bekliyor"]
        delivery_statuses = [
            "Teslim Bekliyor",
            "İade Bekliyor",
            "Iade Bekliyor",
            "Teslim Edildi",
            "İade Edildi",
            "Iade Edildi",
        ]
        if status in waiting_statuses:
            return "waiting"
        if status in active_statuses:
            return "active"
        if "Hazır" in status or "Hazir" in status or "İşlemleri Tamamlandı" in status or "Islemleri Tamamlandi" in status:
            return "ready"
        delivered_ok, _ = self.is_delivered_record(record)
        if delivered_ok:
            return "delivered"
        if status in delivery_statuses:
            return "done"
        return None

    def service_row_for_record(self, kid, record):
        if not isinstance(record, dict):
            return None
        bucket = self.record_status_bucket(record)
        status = str(record.get("d", "") or "")
        device_text = self.device_display_text(record)
        ucret = safe_float(record.get("masraf", "0"))
        money_plain = "" if ucret == 0 else f"{format_money(ucret, '')}"
        zaman = record.get("z", "")
        odeme = record.get("odeme_durumu", "Ödenmedi")
        odeme_tipi = record.get("odeme_tipi", "Nakit")

        if bucket in ("waiting", "active"):
            yaklasik = safe_float(record.get("yaklasik_ucret", "0"))
            fiyat_text = f"{format_money(ucret, '₺')}" if ucret > 0 else f"Yaklaşık: {format_money(yaklasik, '₺')}" if yaklasik > 0 else ""
            target_table = self.table_ready if bucket == "waiting" else self.table_act
            row_colors = self.party_row_colors(record, 8)
            if bucket == "waiting" and not row_colors:
                row_colors = [QColor("#f59e0b")] * 8
            return {
                "table": target_table,
                "row": [kid, record.get("c_no"), self.party_display_text(record), device_text, self.format_faults(record), fiyat_text, zaman, self.status_display_text(record, status)],
                "colors": row_colors,
                "background": None,
            }

        if bucket == "ready":
            payment_text = f"{odeme} ({odeme_tipi})" if odeme == "Ödendi" else odeme
            base_colors = self.party_row_colors(record, 10) or [QColor("#22c55e")] * 10
            base_colors[8] = QColor("#f97316")
            base_colors[9] = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
            return {
                "table": self.table_done,
                "row": [kid, record.get("c_no"), self.party_display_text(record), device_text, record.get("yapilan_islem", ""), f"{money_plain} ₺" if money_plain else "", zaman, self.status_display_text(record, "İşlemi Tamamlandı"), "Teslim Bekliyor", payment_text],
                "colors": base_colors,
                "background": None,
            }

        if bucket in ("done", "delivered"):
            delivered_ok, delivered_is_iade = self.is_delivered_record(record)
            is_iade = "İade" in status or "Iade" in status or delivered_is_iade
            if bucket == "delivered":
                if not self.delivered_filter_accepts_record(record):
                    return None
                status_text = self.status_display_text(record, "↩ İADE TESLİM EDİLDİ" if is_iade else "TESLİM EDİLDİ")
                pay_color = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
                base_color = QColor("#f97316") if is_iade else QColor("#22c55e")
                payment_text = f"{odeme} ({odeme_tipi})" if odeme == "Ödendi" else odeme
                return {
                    "table": self.table_delivered,
                    "row": [kid, record.get("c_no"), self.party_display_text(record), device_text, record.get("yapilan_islem", ""), f"{format_money(ucret, '₺')}" if ucret > 0 else "", self.delivery_date_for_record(record), status_text, record.get("teslim_durumu") or "Müşteriye Teslim Edildi", payment_text],
                    "colors": self.party_row_colors(record, 10) or [base_color] * 9 + [pay_color],
                    "background": QColor("#fff3e0") if is_iade else None,
                }

            if "Bekliyor" in status:
                durum_goster = "↩ İADE BEKLİYOR" if is_iade else "TESLİM BEKLİYOR"
            else:
                durum_goster = "↩ İADE EDİLDİ" if is_iade else status
            teslim_durumu = record.get("teslim_durumu", "")
            if not teslim_durumu:
                teslim_durumu = "Müşteriye Teslim Edildi" if status == "Teslim Edildi" else "Teslim Bekliyor"
            payment_text = f"{odeme} ({odeme_tipi})" if odeme == "Ödendi" else odeme
            base_colors = self.party_row_colors(record, 10) or [QColor("#2ecc71") if "Teslim" in status else QColor("#f97316")] * 10
            base_colors[8] = QColor("#22c55e") if "Teslim Edildi" in teslim_durumu else QColor("#f97316")
            base_colors[9] = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
            return {
                "table": self.table_done,
                "row": [kid, record.get("c_no"), self.party_display_text(record), device_text, record.get("yapilan_islem", ""), f"{money_plain} ₺" if money_plain else "", zaman, self.status_display_text(record, durum_goster), teslim_durumu, payment_text],
                "colors": base_colors,
                "background": QColor("#fff3e0") if is_iade else None,
            }
        return None

    def delivered_filter_accepts_record(self, record):
        delivered_ok, is_iade = self.is_delivered_record(record)
        if not delivered_ok:
            return False
        status_filter = self.delivered_status_cb.currentText() if hasattr(self, "delivered_status_cb") else "Tümü"
        odeme = str(record.get("odeme_durumu", "Ödenmedi") or "Ödenmedi")
        if status_filter == "Başarılı Teslim" and is_iade:
            return False
        if status_filter == "İade Teslim" and not is_iade:
            return False
        if status_filter == "Ödendi" and odeme != "Ödendi":
            return False
        if status_filter == "Ödenmedi" and odeme == "Ödendi":
            return False
        start, end = self.delivered_period_bounds()
        delivered_dt = self.parse_date_value(self.delivery_date_for_record(record))
        return delivered_dt != datetime.datetime.min and start <= delivered_dt <= end

    def upsert_record_row_from_cache(self, kid, record):
        target = self.service_row_for_record(kid, record)
        target_table = target.get("table") if target else None
        for table in [
            getattr(self, "table_act", None),
            getattr(self, "table_ready", None),
            getattr(self, "table_done", None),
            getattr(self, "table_delivered", None),
        ]:
            if table and table is not target_table:
                self.remove_record_from_table(table, kid)
        if not target or not target_table:
            return
        row = self.find_record_row(target_table, kid)
        if row < 0:
            row = self.add_row_to_table(target_table, target["row"], target.get("colors"), at_top=True)
        else:
            self.set_table_row_data(target_table, row, target["row"], target.get("colors"))
        if target.get("background"):
            self.apply_table_row_background(target_table, row, target["background"])
        self.apply_table_filter(target_table)

    def rebuild_record_lookup_sets(self):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        self.bayi_isimleri.clear()
        self.musteri_listesi.clear()
        self.cihaz_listesi.clear()
        self.ariza_listesi.clear()
        self.operation_listesi.clear()
        sabit = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
        if isinstance(sabit, dict):
            for item in sabit.values():
                if isinstance(item, dict) and item.get("ad"):
                    self.bayi_isimleri.add(item.get("ad"))
        for record in data.values():
            if not isinstance(record, dict):
                continue
            if record.get("m"):
                if self.is_bayi_record(record):
                    self.bayi_isimleri.add(record.get("m"))
                else:
                    self.musteri_listesi.add(self.normalize_upper(record.get("m")))
            if record.get("ci"):
                self.cihaz_listesi.add(self.normalize_upper(record.get("ci")))
            if record.get("yapilan_islem"):
                self.operation_listesi.add(self.normalize_upper(record.get("yapilan_islem")))
            for fault in self.get_faults(record):
                self.ariza_listesi.add(fault)

    def recompute_record_dashboard_from_cache(self):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        kasa_data = safe_dict_parse(getattr(self, "kasa_data", {}))
        if not isinstance(kasa_data, dict):
            kasa_data = {}
        toplam_kazanc = bekleyen_alacak = m_gelir = m_gider = 0.0
        tot_nakit = tot_kart = tot_eft = 0.0
        done_nakit = done_kart = done_eft = 0.0
        delivered_nakit = delivered_kart = delivered_eft = delivered_amount = 0.0
        c_act = c_ready = c_done = c_delivered_visible = 0
        c_teslim_wait = c_iade_wait = 0
        stats = {"g": 0.0, "h": 0.0, "a": 0.0}
        for record in data.values():
            if not isinstance(record, dict):
                continue
            status = str(record.get("d", "") or "")
            bucket = self.record_status_bucket(record)
            ucret = safe_float(record.get("masraf", "0"))
            odeme = record.get("odeme_durumu", "Ödenmedi")
            odeme_tipi = record.get("odeme_tipi", "Nakit")
            if bucket == "waiting":
                c_ready += 1
            elif bucket == "active":
                c_act += 1
            elif bucket == "ready":
                c_done += 1
                c_teslim_wait += 1
            elif bucket == "done":
                c_done += 1
            elif bucket == "delivered" and self.delivered_filter_accepts_record(record):
                c_delivered_visible += 1
                if odeme == "Ödendi":
                    delivered_amount += ucret
                    if "Kart" in odeme_tipi:
                        delivered_kart += ucret
                    elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                        delivered_eft += ucret
                    else:
                        delivered_nakit += ucret
            teslim_durumu = str(record.get("teslim_durumu", "") or "")
            if bucket != "ready" and "Teslim Bekliyor" in teslim_durumu:
                if "İade" in status or "Iade" in status:
                    c_iade_wait += 1
                else:
                    c_teslim_wait += 1
            if "Teslim" in status:
                if odeme == "Ödendi":
                    toplam_kazanc += ucret
                    self.update_income_stats(ucret, record.get("z", ""), stats)
                    if "Kart" in odeme_tipi:
                        tot_kart += ucret
                        done_kart += ucret
                    elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                        tot_eft += ucret
                        done_eft += ucret
                    else:
                        tot_nakit += ucret
                        done_nakit += ucret
                else:
                    bekleyen_alacak += ucret
        for item in kasa_data.values():
            if not isinstance(item, dict) or not self.should_count_cash_record(item):
                continue
            tip = str(item.get("tip", "Gelir") or "Gelir")
            odeme_tipi = str(item.get("odeme_tipi", "") or "Nakit")
            tutar = safe_float(item.get("tutar", "0"))
            if "Gelir" in tip or "Income" in tip:
                m_gelir += tutar
                self.update_income_stats(tutar, item.get("t"), stats)
                if "Kart" in odeme_tipi:
                    tot_kart += tutar
                elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                    tot_eft += tutar
                else:
                    tot_nakit += tutar
            else:
                m_gider += tutar
                self.update_income_stats(-tutar, item.get("t"), stats)
                if "Kart" in odeme_tipi:
                    tot_kart -= tutar
                elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                    tot_eft -= tutar
                else:
                    tot_nakit -= tutar

        net_kasa = (toplam_kazanc + m_gelir) - m_gider
        if hasattr(self, "lbl_gunluk"):
            self.lbl_gunluk.setText(f"{format_money(stats['g'], '₺')}")
            self.lbl_haftalik.setText(f"{format_money(stats['h'], '₺')}")
            self.lbl_aylik.setText(f"{format_money(stats['a'], '₺')}")
            self.lbl_kasa.setText(f"{format_money(net_kasa, '₺')}")
            self.lbl_islemde.setText(str(c_act))
            self.lbl_bekleyen.setText(str(c_ready))
            self.lbl_teslim_bekleyen.setText(str(c_teslim_wait))
            self.lbl_iade_bekleyen.setText(str(c_iade_wait))
            self.lbl_tot_nakit.setText(f"💵 Nakit Kasa: {format_money(tot_nakit, '₺')}")
            self.lbl_tot_kart.setText(f"💳 Kredi Kartı: {format_money(tot_kart, '₺')}")
            self.lbl_tot_eft.setText(f"📱 EFT / Havale: {format_money(tot_eft, '₺')}")
            self.lbl_done_nakit.setText(f"Nakit: {format_money(done_nakit, '₺')}")
            self.lbl_done_kart.setText(f"Kart: {format_money(done_kart, '₺')}")
            self.lbl_done_eft.setText(f"EFT: {format_money(done_eft, '₺')}")
            self.lbl_toplam.setText(f"<b>Cihazlardan Gelen (Net):</b> {format_money(toplam_kazanc, '₺')}")
            self.lbl_alacak.setText(f"<b>Açık Hesap (Bekleyen):</b> {format_money(bekleyen_alacak, '₺')}")
        if hasattr(self, "lbl_delivered_nakit"):
            self.lbl_delivered_nakit.setText(f"Nakit: {format_money(delivered_nakit, '₺')}")
            self.lbl_delivered_kart.setText(f"Kart: {format_money(delivered_kart, '₺')}")
            self.lbl_delivered_eft.setText(f"EFT: {format_money(delivered_eft, '₺')}")
        if hasattr(self, "lbl_delivered_summary"):
            self.lbl_delivered_summary.setText(f"Gösterilen: {c_delivered_visible} | Tutar: {format_money(delivered_amount, '₺')}")
        self.update_main_tab_counts(c_act, c_ready, c_done, c_delivered_visible)

    def refresh_record_views_after_stream(self):
        self.rebuild_record_lookup_sets()
        self.recompute_record_dashboard_from_cache()
        self.refresh_autocomplete_models()
        self.rebuild_party_lists()
        self.update_notification_summary()
        self.update_management_report()
        self.apply_all_table_filters()
        self.set_sync_status(f"Canlı güncellendi - {datetime.datetime.now().strftime('%H:%M:%S')}", "#22c55e")

    def get_local_record(self, record_id):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if isinstance(data, dict):
            record = data.get(record_id)
            if isinstance(record, dict):
                return record
        record = db.child("users").child(self.user_id).child("kayitlar").child(record_id).get(self.token).val()
        return record if isinstance(record, dict) else {}

    def rebuild_party_lists(self):
        if not hasattr(self, "list_bayiler") or not hasattr(self, "list_musteriler"):
            return
        current_bayi = self.list_bayiler.currentItem().text() if self.list_bayiler.currentItem() else None
        current_must_item = self.list_musteriler.currentItem()
        current_must = current_must_item.text() if current_must_item else None
        current_must_data = current_must_item.data(Qt.ItemDataRole.UserRole) if current_must_item else {}
        current_must_key = str(current_must_data.get("key", "") if isinstance(current_must_data, dict) else "")
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        bayi_mode = self.bayi_filter_cb.currentText() if hasattr(self, "bayi_filter_cb") else "Alfabetik"
        must_mode = self.must_filter_cb.currentText() if hasattr(self, "must_filter_cb") else "Alfabetik"
        bayi_names = self.filtered_party_names(list(getattr(self, "bayi_isimleri", [])), data, True, bayi_mode)
        musteri_entries = self.customer_entries_for_list(must_mode)

        self.list_bayiler.blockSignals(True)
        self.list_musteriler.blockSignals(True)
        self.list_bayiler.clear()
        self.list_musteriler.clear()
        self.list_bayiler.addItems(bayi_names)
        for customer in musteri_entries:
            item = QListWidgetItem(customer.get("display", customer.get("name", "")))
            item.setData(Qt.ItemDataRole.UserRole, customer)
            self.list_musteriler.addItem(item)
        if current_bayi:
            items = self.list_bayiler.findItems(current_bayi, Qt.MatchFlag.MatchExactly)
            if items:
                self.list_bayiler.setCurrentItem(items[0])
        if current_must_key:
            for idx in range(self.list_musteriler.count()):
                item = self.list_musteriler.item(idx)
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and str(data.get("key", "")) == current_must_key:
                    self.list_musteriler.setCurrentItem(item)
                    break
        elif current_must:
            items = self.list_musteriler.findItems(current_must, Qt.MatchFlag.MatchExactly)
            if items:
                self.list_musteriler.setCurrentItem(items[0])
        self.list_bayiler.blockSignals(False)
        self.list_musteriler.blockSignals(False)

        if hasattr(self, "combo_bayi"):
            current_combo_bayi = self.combo_bayi.currentText()
            self.combo_bayi.blockSignals(True)
            self.combo_bayi.clear()
            self.combo_bayi.addItems(sorted([name for name in getattr(self, "bayi_isimleri", set()) if name], key=self.normalize_upper))
            if current_combo_bayi and self.combo_bayi.findText(current_combo_bayi) >= 0:
                self.combo_bayi.setCurrentText(current_combo_bayi)
            self.combo_bayi.blockSignals(False)
            self.fill_partner_phone(self.combo_bayi.currentText())
        if hasattr(self, "lbl_bayi_sayac"):
            self.lbl_bayi_sayac.setText(f"{len(bayi_names)} bayi")
        if hasattr(self, "lbl_musteri_sayac"):
            self.lbl_musteri_sayac.setText(f"{len(musteri_entries)} müşteri")
        self.filter_bayi_listesi(self.bayi_search_sol.text() if hasattr(self, "bayi_search_sol") else "")
        self.filter_musteri_listesi(self.must_search.text() if hasattr(self, "must_search") else "")

    def on_main_tab_changed(self, index):
        if index == getattr(self, "_adb_cleaner_tab_index", -1):
            self.ensure_adb_cleaner_loaded()
        self.update_sidebar_selection(index)
        current_tab = self.tabs.widget(index)
        if current_tab == getattr(self, "tab_whl", None):
            self.load_wholesalers()
        if getattr(self, "_dashboard_filter_navigation", False):
            self._dashboard_filter_navigation = False
            return
        if current_tab == getattr(self, "tab_rdy", None):
            self.set_table_filter(self.table_ready, "Tümü")
        elif current_tab == getattr(self, "tab_dne", None):
            self.set_table_filter(self.table_done, "Tümü")
        elif current_tab == getattr(self, "tab_delivered", None):
            self.filter_delivered_table()

    def ensure_adb_cleaner_loaded(self):
        if getattr(self, "is_trial_license", False) or getattr(self, "_adb_cleaner_loaded", False):
            return
        if getattr(self, "_loading_adb_cleaner", False):
            return
        index = self.tabs.indexOf(getattr(self, "tab_adb_cleaner", None))
        if index < 0:
            return
        self._loading_adb_cleaner = True
        old_widget = self.tab_adb_cleaner
        try:
            cleaner = AdbCleanerWidget(self)
            self.tab_adb_cleaner = cleaner
            self._adb_cleaner_loaded = True
            self.tabs.removeTab(index)
            old_widget.deleteLater()
            self.tabs.insertTab(index, cleaner, "Virüs Temizleyici")
            self.tabs.setCurrentIndex(index)
            self.apply_staff_permissions()
            self.update_sidebar_selection(index)
        finally:
            self._loading_adb_cleaner = False

    def sidebar_stylesheet(self):
        theme = str(self.user_setting_value("theme", "Dark") or "Dark")
        palettes = {
            "Light": {
                "bg": "#f8fafc", "border": "#e5e7eb", "brand": "#111827", "muted": "#94a3b8",
                "text": "#334155", "hover": "#eef2f7", "hover_text": "#111827",
                "selected": "#ffffff", "selected_text": "#0f172a", "handle": "#cbd5e1", "active": "#2563eb",
            },
            "Dark": {
                "bg": "#202124", "border": "#343842", "brand": "#f3f6fb", "muted": "#8f98a8",
                "text": "#d8dee8", "hover": "#2a2e35", "hover_text": "#ffffff",
                "selected": "#2b2f38", "selected_text": "#ffffff", "handle": "#4b5563", "active": "#60a5fa",
            },
            "Ocean": {
                "bg": "#06202d", "border": "#155e75", "brand": "#e6fbff", "muted": "#67e8f9",
                "text": "#cffafe", "hover": "#0e374a", "hover_text": "#ffffff",
                "selected": "#0b3a4c", "selected_text": "#ffffff", "handle": "#22d3ee", "active": "#22d3ee",
            },
            "Emerald": {
                "bg": "#ecfdf5", "border": "#bbf7d0", "brand": "#064e3b", "muted": "#059669",
                "text": "#065f46", "hover": "#d1fae5", "hover_text": "#022c22",
                "selected": "#ffffff", "selected_text": "#022c22", "handle": "#34d399", "active": "#059669",
            },
            "Graphite": {
                "bg": "#202124", "border": "#3f3f46", "brand": "#f4f4f5", "muted": "#a1a1aa",
                "text": "#e4e4e7", "hover": "#27272a", "hover_text": "#ffffff",
                "selected": "#2f3034", "selected_text": "#ffffff", "handle": "#71717a", "active": "#a1a1aa",
            },
        }
        p = palettes.get(theme, palettes["Dark"])
        return f"""
            QFrame#AppSidebar {{
                background: {p["bg"]};
                border-right: 1px solid {p["border"]};
            }}
            QScrollArea#SidebarScroll {{
                background: transparent;
                border: 0;
            }}
            QScrollArea#SidebarScroll QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 2px 0 2px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {p["handle"]};
                min-height: 34px;
                border-radius: 3px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QLabel#SidebarBrand {{
                color: {p["brand"]};
                font-size: 18px;
                font-weight: 800;
                padding: 6px 8px 12px 8px;
                border-bottom: 1px solid {p["border"]};
            }}
            QPushButton#SidebarGroupButton {{
                color: {p["muted"]};
                font-size: 12px;
                font-weight: 800;
                border: 0;
                border-radius: 7px;
                padding: 0 8px;
                text-align: left;
                background: transparent;
            }}
            QPushButton#SidebarGroupButton:hover {{
                background: {p["hover"]};
                color: {p["hover_text"]};
            }}
            QPushButton#NavButton {{
                background: transparent;
                color: {p["text"]};
                border: 1px solid transparent;
                border-left: 3px solid transparent;
                border-radius: 9px;
                padding: 0 10px;
                text-align: left;
                font-size: 13px;
                font-weight: 650;
            }}
            QPushButton#NavButton:hover {{
                background: {p["hover"]};
                color: {p["hover_text"]};
            }}
            QPushButton#NavButton:checked {{
                background: {p["selected"]};
                color: {p["selected_text"]};
                border-left: 3px solid {p["active"]};
                border-top: 1px solid {p["border"]};
                border-right: 1px solid {p["border"]};
                border-bottom: 1px solid {p["border"]};
                font-weight: 800;
            }}
        """

    def build_sidebar_navigation(self):
        if not hasattr(self, "sidebar_layout"):
            return
        while self.sidebar_layout.count():
            item = self.sidebar_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        while self.sidebar_nav_layout.count():
            item = self.sidebar_nav_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.nav_buttons = {}
        self.nav_base_labels = {}
        self.sidebar_sections = {}
        self.sidebar.setStyleSheet(self.sidebar_stylesheet())
        brand_row = QWidget()
        brand_row.setObjectName("SidebarBrandRow")
        brand_layout = QHBoxLayout(brand_row)
        brand_layout.setContentsMargins(0, 0, 0, 2)
        brand_layout.setSpacing(8)
        self.sidebar_logo_label = QLabel()
        self.sidebar_logo_label.setFixedSize(30, 30)
        self.sidebar_logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar_brand_label = QLabel(self.display_company_name())
        self.sidebar_brand_label.setObjectName("SidebarBrand")
        self.sidebar_brand_label.setWordWrap(True)
        brand_layout.addWidget(self.sidebar_logo_label)
        brand_layout.addWidget(self.sidebar_brand_label, 1)
        self.sidebar_layout.addWidget(brand_row)
        self.sidebar_staff_label = QLabel(f"{self.current_staff.get('name', '-')} · {self.current_staff.get('role', '-')}")
        self.sidebar_staff_label.setStyleSheet("color:#94a3b8; font-size:11px; padding:0 8px 2px 8px;")
        self.sidebar_staff_label.setWordWrap(True)
        staff_visible = self.should_show_staff_gate()
        self.sidebar_staff_label.setVisible(staff_visible)
        self.sidebar_layout.addWidget(self.sidebar_staff_label)
        self.sidebar_layout.addWidget(self.sidebar_nav, 1)
        self.update_sidebar_logo_label()

        virus_label = (
            self.get_trans("Virus Cleaner (Premium)", "Virüs Temizleyici (Premium)")
            if getattr(self, "is_trial_license", False)
            else self.get_trans("Virus Cleaner", "Virüs Temizleyici")
        )
        sections = [
            (self.get_trans("Service", "Servis"), "#60a5fa", [
                (0, "🏠", self.get_trans("Dashboard", "Ana Panel")),
                (1, "➕", self.get_trans("New Entry", "Yeni Kayıt")),
                (3, "⌛", self.get_trans("Waiting Jobs", "İşlem Bekleyenler")),
                (2, "⏳", self.get_trans("In Progress", "İşlemdekiler")),
                (4, "🔁", self.get_trans("Delivery/Return", "Teslim/İade")),
                (5, "✅", self.get_trans("Delivered", "Teslim Edilenler")),
            ]),
            (self.get_trans("People", "Kişiler"), "#34d399", [
                (6, "👥", self.get_trans("Customers", "Müşteriler")),
                (7, "🏢", self.get_trans("Partners", "Bayiler")),
            ]),
            (self.get_trans("Commerce", "Ticaret"), "#fbbf24", [
                (8, "🧩", self.get_trans("Stock", "Stok")),
                (9, "🏭", self.get_trans("Suppliers", "Toptancı")),
                (10, "📊", self.get_trans("Detailed Report", "Detaylı Döküm")),
            ]),
            (self.get_trans("Tools", "Araçlar"), "#a78bfa", [
                (11, "💱", self.get_trans("Currency", "Döviz")),
                (12, "🗑️", self.get_trans("Trash", "Çöp Kutusu")),
                (16, "🧭", self.get_trans("Management", "Yönetim")),
                (17, "🛡", virus_label),
            ]),
            (self.get_trans("System", "Sistem"), "#f87171", [
                (13, "⚙️", self.get_trans("Settings", "Ayarlar")),
                (14, "🔐", self.get_trans("License", "Lisans")),
                (15, "ℹ️", self.get_trans("About", "Hakkında")),
            ]),
        ]
        for section, accent, items in sections:
            section_button = QPushButton(f"{section}  ▾")
            section_button.setObjectName("SidebarGroupButton")
            section_button.setCheckable(True)
            section_button.setChecked(True)
            section_button.setMinimumHeight(30)
            section_button.setMaximumHeight(30)
            section_button.setCursor(Qt.CursorShape.PointingHandCursor)
            section_button.setStyleSheet(f"QPushButton#SidebarGroupButton {{ color: {accent}; }}")
            self.sidebar_nav_layout.addWidget(section_button)
            section_widgets = []
            for index, icon, label in items:
                btn = QPushButton(self.sidebar_nav_text(icon, label, ""))
                btn.setObjectName("NavButton")
                btn.setCheckable(True)
                btn.setMinimumHeight(34)
                btn.setMaximumHeight(34)
                btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setToolTip(label)
                btn.clicked.connect(lambda checked=False, i=index: self.tabs.setCurrentIndex(i))
                self.sidebar_nav_layout.addWidget(btn)
                self.nav_buttons[index] = btn
                self.nav_base_labels[index] = (icon, label)
                section_widgets.append(btn)
            self.sidebar_sections[section] = {"button": section_button, "widgets": section_widgets}
            section_button.clicked.connect(lambda checked=False, s=section: self.toggle_sidebar_section(s))
        self.sidebar_nav_layout.addStretch()
        self.update_sidebar_selection(self.tabs.currentIndex())
        self.apply_staff_permissions()

    def toggle_sidebar_section(self, section):
        info = getattr(self, "sidebar_sections", {}).get(section)
        if not info:
            return
        expanded = info["button"].isChecked()
        info["button"].setText(f"{section}  {'▾' if expanded else '▸'}")
        for widget in info["widgets"]:
            widget.setVisible(expanded)

    def sidebar_nav_text(self, icon, label, count=""):
        suffix = f"   {count}" if str(count).strip() else ""
        return f"{icon}   {label}{suffix}"

    def update_sidebar_selection(self, index):
        for i, btn in getattr(self, "nav_buttons", {}).items():
            btn.blockSignals(True)
            btn.setChecked(i == index)
            btn.blockSignals(False)

    def update_sidebar_count(self, index, count):
        if not hasattr(self, "nav_buttons") or index not in self.nav_buttons:
            return
        icon, label = self.nav_base_labels.get(index, ("", self.tabs.tabText(index)))
        self.nav_buttons[index].setText(self.sidebar_nav_text(icon, label, count))

    def get_trans(self, en, tr_str): 
        return en if self.current_language() == "English" else tr_str

    def current_language(self):
        raw = str(self.user_setting_value("lang", "Türkçe") or "Türkçe").strip()
        if raw.lower().startswith("eng"):
            return "English"
        return "Türkçe"

    def normalize_language_setting(self):
        normalized = self.current_language()
        raw = str(self.user_setting_value("lang", "Türkçe") or "Türkçe").strip()
        if raw != normalized:
            self.set_user_setting("lang", normalized)
        return normalized

    def suggestion_blocklist(self, kind):
        raw = self.user_setting_value(f"suggestion_blocklist_{kind}", "[]")
        if isinstance(raw, (list, tuple, set)):
            values = list(raw)
        else:
            try:
                values = json.loads(str(raw or "[]"))
            except Exception:
                values = []
        if not isinstance(values, list):
            values = []
        return {self.normalize_upper(value).strip() for value in values if str(value).strip()}

    def set_suggestion_blocklist(self, kind, values):
        cleaned = sorted({self.normalize_upper(value).strip() for value in values if str(value).strip()})
        self.set_user_setting(f"suggestion_blocklist_{kind}", json.dumps(cleaned, ensure_ascii=False))

    def filtered_suggestions(self, kind, values):
        hidden = self.suggestion_blocklist(kind)
        unique = {self.normalize_upper(value).strip() for value in values if str(value).strip()}
        return sorted([value for value in unique if value not in hidden], key=self.normalize_upper)

    def operation_memory_values(self):
        values = set(getattr(self, "operation_listesi", set()))
        raw = self.user_setting_value("operation_suggestions", "[]")
        try:
            saved = json.loads(str(raw or "[]"))
        except Exception:
            saved = []
        if isinstance(saved, list):
            values.update(self.normalize_upper(item).strip() for item in saved if str(item).strip())
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if isinstance(data, dict):
            for record in data.values():
                if isinstance(record, dict) and record.get("yapilan_islem"):
                    values.add(self.normalize_upper(record.get("yapilan_islem")).strip())
        return self.filtered_suggestions("operation", values)

    def remember_operation_text(self, text):
        value = self.normalize_upper(text).strip()
        if not value:
            return ""
        existing = self.operation_memory_values()
        ordered = [value] + [item for item in existing if item != value]
        self.set_user_setting("operation_suggestions", json.dumps(ordered[:80], ensure_ascii=False))
        if hasattr(self, "operation_listesi"):
            self.operation_listesi.add(value)
        return value

    def create_operation_dialog(self, title, default_text=""):
        dlg = CustomEditDialog(title, "Yapılan İşlem:", default_text, self)
        if hasattr(dlg, "inp") and isinstance(dlg.inp, QLineEdit):
            dlg.operation_model = QStringListModel(self.operation_memory_values(), dlg.inp)
            completer = QCompleter(dlg.operation_model, dlg.inp)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
            completer.setMaxVisibleItems(8)
            try:
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
            except Exception:
                pass
            popup = QListView(dlg.inp)
            popup.setObjectName("OperationSuggestionPopup")
            popup.setStyleSheet("""
                QListView#OperationSuggestionPopup {
                    background:#111827;
                    color:#f8fafc;
                    border:1px solid #334155;
                    border-radius:6px;
                    padding:4px;
                    outline:0;
                    selection-background-color:#1d4ed8;
                }
                QListView#OperationSuggestionPopup::item {
                    min-height:28px;
                    padding:6px 8px;
                    border-bottom:1px solid #1f2937;
                }
            """)
            dlg.operation_popup = popup
            dlg.operation_completer = completer
            completer.setPopup(popup)
            dlg.inp.setCompleter(completer)
        return dlg

    def refresh_autocomplete_models(self):
        if hasattr(self, "musteri_completer"):
            self.musteri_completer.setModel(QStringListModel(self.filtered_suggestions("musteri", self.musteri_listesi)))
        if hasattr(self, "cihaz_completer"):
            self.cihaz_completer.setModel(QStringListModel(self.filtered_suggestions("cihaz", self.cihaz_listesi)))
        if hasattr(self, "ariza_completer"):
            self.ariza_completer.setModel(QStringListModel(self.filtered_suggestions("ariza", self.ariza_listesi)))

    def configure_suggestion_completer(self, completer, kind, field, label):
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setMaxVisibleItems(8)
        try:
            completer.setFilterMode(Qt.MatchFlag.MatchContains)
        except Exception:
            pass
        popup = QListView(field)
        popup.setObjectName("SuggestionPopup")
        popup.setMouseTracking(True)
        popup.setUniformItemSizes(False)
        popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup.setStyleSheet("""
            QListView#SuggestionPopup {
                background:#111827;
                color:#f8fafc;
                border:1px solid #334155;
                border-radius:6px;
                padding:3px;
                outline:0;
                selection-background-color:#1d4ed8;
            }
            QListView#SuggestionPopup::item {
                min-height:30px;
                padding:0;
                border-bottom:1px solid #1f2937;
            }
        """)
        popup.setItemDelegate(SuggestionDeleteDelegate(popup))
        completer.setPopup(popup)
        popup.viewport().installEventFilter(self)
        self._suggestion_popup_meta[id(popup.viewport())] = {
            "kind": kind,
            "field": field,
            "label": label,
            "completer": completer,
        }

    def hide_suggestion_value(self, kind, value, label="", clear_field=None):
        value = self.normalize_upper(value).strip()
        if not value:
            return False
        hidden = self.suggestion_blocklist(kind)
        hidden.add(value)
        self.set_suggestion_blocklist(kind, hidden)
        self.refresh_autocomplete_models()
        self.set_sync_status(f"{label or 'Öneri'} gizlendi: {value}", "#38bdf8")
        if clear_field is not None:
            clear_field.clear()
        return True

    def hide_current_suggestion(self, kind, field, label):
        value = self.normalize_upper(field.text()).strip()
        if not value:
            QMessageBox.information(self, "Öneri Gizle", f"Gizlemek için önce {label.lower()} alanına öneriyi yazın veya seçin.")
            return
        self.hide_suggestion_value(kind, value, label, clear_field=field)

    def reopen_suggestion_popup(self, completer, field):
        if field is None or completer is None:
            return
        if not field.hasFocus():
            field.setFocus()
        prefix = field.text()
        if prefix:
            completer.setCompletionPrefix(prefix)
            completer.complete()

    def reset_hidden_suggestions(self):
        if QMessageBox.question(
            self,
            "Önerileri Sıfırla",
            "Gizlenen cihaz, arıza ve müşteri önerileri tekrar görünür yapılacak.\n\nDevam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        for kind in ["musteri", "cihaz", "ariza"]:
            self.set_suggestion_blocklist(kind, [])
        self.refresh_autocomplete_models()
        QMessageBox.information(self, "Öneriler", "Gizlenen öneriler sıfırlandı.")

    def format_quantity(self, value):
        qty = safe_float(value)
        if qty.is_integer():
            return str(int(qty))
        return f"{qty:.2f}".rstrip("0").rstrip(".").replace(".", ",")

    def stock_code_for_item(self, stock_id, item=None, index=None):
        item = item if isinstance(item, dict) else {}
        code = str(item.get("stok_kodu", "") or item.get("kod", "")).strip().upper()
        if code:
            return code
        if isinstance(index, int):
            return f"STK-{index:06d}"
        short_id = str(stock_id or "").replace("-", "").upper()[-6:]
        return f"STK-{short_id or '000000'}"

    def next_stock_code(self):
        data = safe_dict_parse(getattr(self, "stok_data", {}))
        if not isinstance(data, dict):
            data = {}
        max_no = 0
        for idx, item in enumerate(data.values(), 1):
            if not isinstance(item, dict):
                continue
            code = str(item.get("stok_kodu", "") or item.get("kod", ""))
            if code.startswith("STK-"):
                try:
                    max_no = max(max_no, int(code.split("-")[-1]))
                except:
                    pass
            else:
                max_no = max(max_no, idx)
        return f"STK-{max_no + 1:06d}"

    def user_setting_key(self, name):
        return f"users/{self.user_id}/{name}"

    def user_setting_value(self, name, default=None):
        return self.settings.value(self.user_setting_key(name), default)

    def set_user_setting(self, name, value):
        self.settings.setValue(self.user_setting_key(name), value)

    def coerce_staff_accounts(self, raw_accounts):
        if isinstance(raw_accounts, list):
            candidates = raw_accounts
        elif isinstance(raw_accounts, dict):
            items = list(raw_accounts.items())
            if all(str(key).isdigit() for key, _ in items):
                items.sort(key=lambda item: int(str(item[0])))
            candidates = [value for _, value in items]
        else:
            return []
        return [account for account in candidates if isinstance(account, dict)]

    def staff_accounts_have_profiles(self, accounts):
        return any(
            isinstance(account, dict) and str(account.get("name", "") or "").strip()
            for account in accounts
        )

    def cloud_user_settings(self):
        if not getattr(self, "user_id", "") or not getattr(self, "token", ""):
            return {}
        try:
            return safe_dict_parse(db.child("users").child(self.user_id).child("ayarlar").get(self.token).val() or {})
        except Exception as e:
            if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                try:
                    return safe_dict_parse(db.child("users").child(self.user_id).child("ayarlar").get(self.token).val() or {})
                except Exception:
                    return {}
            return {}

    def cloud_user_value(self, name, default=None):
        if not getattr(self, "user_id", "") or not getattr(self, "token", ""):
            return default
        try:
            value = db.child("users").child(self.user_id).child(name).get(self.token).val()
            return default if value is None else value
        except Exception as e:
            if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                try:
                    value = db.child("users").child(self.user_id).child(name).get(self.token).val()
                    return default if value is None else value
                except Exception:
                    return default
            return default

    def ensure_staff_accounts_ready_on_startup(self):
        cloud_settings = self.cloud_user_settings()
        if not isinstance(cloud_settings, dict):
            cloud_settings = {}
        cloud_has_key = isinstance(cloud_settings, dict) and "staff_accounts" in cloud_settings
        raw_cloud_accounts = self.coerce_staff_accounts(cloud_settings.get("staff_accounts"))
        raw_mobile_accounts = self.coerce_staff_accounts(self.cloud_user_value("personel_hesaplari", []))
        raw_root_accounts = self.coerce_staff_accounts(self.cloud_user_value("staff_accounts", []))
        raw_legacy_accounts = self.coerce_staff_accounts(self.cloud_user_value("personel", []))
        raw_local_accounts = self.staff_accounts()
        cloud_accounts = self.normalized_staff_accounts(raw_cloud_accounts)
        mobile_accounts = self.normalized_staff_accounts(raw_mobile_accounts)
        root_accounts = self.normalized_staff_accounts(raw_root_accounts)
        legacy_accounts = self.normalized_staff_accounts(raw_legacy_accounts)
        local_accounts = self.normalized_staff_accounts(raw_local_accounts)

        if self.staff_accounts_have_profiles(cloud_accounts):
            self.set_user_setting("staff_accounts", json.dumps(cloud_accounts, ensure_ascii=False))
            pin_value = str(cloud_settings.get("staff_pin_enabled", "true") or "true").lower()
            self.set_user_setting("staff_pin_enabled", "true" if pin_value in ("true", "1", "yes", "evet") else "false")
            self.sync_staff_accounts_to_cloud(cloud_accounts)
            return

        for fallback_accounts in (mobile_accounts, root_accounts, legacy_accounts):
            if self.staff_accounts_have_profiles(fallback_accounts):
                self.set_user_setting("staff_accounts", json.dumps(fallback_accounts, ensure_ascii=False))
                self.set_user_setting("staff_pin_enabled", "true")
                self.sync_staff_accounts_to_cloud(fallback_accounts)
                return

        if self.staff_accounts_have_profiles(local_accounts):
            self.set_user_setting("staff_accounts", json.dumps(local_accounts, ensure_ascii=False))
            self.sync_staff_accounts_to_cloud(local_accounts)
            return

        if cloud_has_key:
            self.set_user_setting("staff_accounts", json.dumps(cloud_accounts, ensure_ascii=False))
            pin_value = str(cloud_settings.get("staff_pin_enabled", "false") or "false").lower()
            self.set_user_setting("staff_pin_enabled", "true" if pin_value in ("true", "1", "yes", "evet") else "false")
            if cloud_accounts != raw_cloud_accounts:
                self.sync_staff_accounts_to_cloud(cloud_accounts)
            return

    def staff_roles(self):
        return ["Yönetici", "Servis Personeli", "Kasa Kapalı Personel", "Sadece Görüntüleme"]

    def staff_permission_catalog(self):
        return [
            ("view_dashboard", "Ana paneli görebilir"),
            ("new_record", "Yeni cihaz kaydı oluşturabilir"),
            ("view_active", "İşlemdekileri görebilir"),
            ("edit_active", "İşlem bekleyen/işlemdeki kayıtlara müdahale edebilir"),
            ("edit_ready", "İşlem bekleyen kayıtlara müdahale edebilir"),
            ("edit_delivery", "Teslim/iade sürecine müdahale edebilir"),
            ("edit_records", "Cihaz durum/not/işlem bilgisi değiştirebilir"),
            ("view_ready", "İşlem bekleyen kayıtları görebilir"),
            ("view_delivery", "Teslim/iade bekleyenleri görebilir"),
            ("view_delivered", "Teslim edilenleri görebilir"),
            ("view_customers", "Müşterileri görebilir"),
            ("view_dealers", "Bayileri görebilir"),
            ("edit_people", "Müşteri/bayi ekleyip düzenleyebilir"),
            ("view_stock", "Stok listesini görebilir"),
            ("stock_add", "Stok ekleyebilir"),
            ("edit_stock", "Stok düzenleyip stoktan parça kullanabilir"),
            ("view_wholesale", "Toptancı kayıtlarını görebilir"),
            ("wholesale", "Toptancı işlemi/parça ekleyebilir"),
            ("view_reports", "Detaylı döküm ve raporları görebilir"),
            ("finance", "Ücret ve ödeme bilgilerini görebilir/değiştirebilir"),
            ("cash_add", "Kasaya gelir/gider hareketi ekleyebilir"),
            ("finance_dashboard", "Ana panel kazanç/kasa özetlerini görebilir"),
            ("view_currency", "Döviz ekranını görebilir"),
            ("trash", "Çöp kutusu ve kayıt silme işlemlerini yapabilir"),
            ("settings", "Ayarları düzenleyebilir"),
            ("license", "Lisans ekranını görebilir"),
            ("admin", "Yönetim merkezini görebilir"),
            ("manage_staff", "Personel ve yetkileri yönetebilir"),
            ("virus", "Virüs temizleyici aracını kullanabilir"),
            ("view_about", "Hakkında ekranını görebilir"),
        ]

    def staff_permission_groups(self):
        return [
            ("Servis", "🧰", [
                "view_dashboard", "new_record", "view_active", "edit_active",
                "view_ready", "edit_ready", "view_delivery", "edit_delivery",
                "view_delivered", "edit_records",
            ]),
            ("Kişiler", "👥", [
                "view_customers", "view_dealers", "edit_people",
            ]),
            ("Ticaret", "📦", [
                "view_stock", "stock_add", "edit_stock", "view_wholesale", "wholesale",
            ]),
            ("Finans", "💳", [
                "finance", "cash_add", "finance_dashboard",
            ]),
            ("Araçlar", "🛠", [
                "view_reports", "view_currency", "virus",
            ]),
            ("Sistem", "🔐", [
                "trash", "settings", "license", "admin", "manage_staff", "view_about",
            ]),
        ]

    def all_staff_permission_keys(self):
        return {key for key, _ in self.staff_permission_catalog()}

    def staff_default_permissions_for_role(self, role):
        all_permissions = self.all_staff_permission_keys()
        if role == "Yönetici":
            return set(all_permissions)
        if role == "Sadece Görüntüleme":
            return {
                "view_dashboard", "view_active", "view_ready", "view_delivery", "view_delivered",
                "view_customers", "view_dealers", "view_stock", "view_currency", "view_about",
            }
        base = {
            "view_dashboard", "new_record", "view_active", "edit_active", "edit_ready", "edit_delivery", "edit_records", "view_ready",
            "view_delivery", "view_delivered", "view_customers", "view_dealers", "edit_people",
            "view_stock", "stock_add", "edit_stock", "view_currency", "virus", "view_about",
        }
        if role != "Kasa Kapalı Personel":
            base.update({"finance", "cash_add", "finance_dashboard"})
        return base

    def account_permissions(self, account):
        if not isinstance(account, dict):
            return set()
        if self.is_staff_admin_account(account):
            return set(self.all_staff_permission_keys())
        permissions = account.get("permissions")
        valid = self.all_staff_permission_keys()
        if isinstance(permissions, list):
            return {str(p) for p in permissions if str(p) in valid}
        return self.staff_default_permissions_for_role(account.get("role", "Servis Personeli"))

    def set_staff_permission_checks(self, permissions):
        if not hasattr(self, "staff_permission_checks"):
            return
        permissions = set(permissions)
        for key, checkbox in self.staff_permission_checks.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(key in permissions)
            checkbox.blockSignals(False)

    def set_staff_permission_checks_locked(self, locked):
        if not hasattr(self, "staff_permission_checks"):
            return
        for checkbox in self.staff_permission_checks.values():
            checkbox.setEnabled(not locked)
            checkbox.setToolTip("Yönetici rolü her zaman tüm yetkilere sahiptir." if locked else "")

    def selected_staff_permissions(self):
        if not hasattr(self, "staff_permission_checks"):
            return set()
        permissions = {key for key, checkbox in self.staff_permission_checks.items() if checkbox.isChecked()}
        implied = {
            "edit_active": "view_active",
            "edit_ready": "view_ready",
            "edit_delivery": "view_delivery",
            "edit_people": "view_customers",
            "stock_add": "view_stock",
            "edit_stock": "view_stock",
            "wholesale": "view_wholesale",
            "manage_staff": "admin",
            "cash_add": "view_dashboard",
            "finance_dashboard": "view_dashboard",
        }
        for edit_key, view_key in implied.items():
            if edit_key in permissions:
                permissions.add(view_key)
        if "edit_people" in permissions:
            permissions.add("view_dealers")
        return permissions

    def apply_staff_role_defaults_to_checks(self, role):
        is_admin_role = self.staff_role_key(role) == "YONETICI"
        self.set_staff_permission_checks(self.staff_default_permissions_for_role("Yönetici" if is_admin_role else role))
        self.set_staff_permission_checks_locked(is_admin_role)

    def staff_tab_permission_map(self):
        return {
            0: "view_dashboard",
            1: "new_record",
            2: "view_active",
            3: "view_ready",
            4: "view_delivery",
            5: "view_delivered",
            6: "view_customers",
            7: "view_dealers",
            8: "view_stock",
            9: "view_wholesale",
            10: "view_reports",
            11: "view_currency",
            12: "trash",
            13: "settings",
            14: "license",
            15: "view_about",
            16: "admin",
            17: "virus",
        }

    def staff_accounts(self):
        raw = str(self.user_setting_value("staff_accounts", "[]") or "[]")
        try:
            accounts = json.loads(raw)
            return accounts if isinstance(accounts, list) else []
        except Exception:
            return []

    def valid_staff_accounts(self):
        return [account for account in self.staff_accounts() if isinstance(account, dict) and str(account.get("name", "") or "").strip()]

    def should_show_staff_gate(self):
        return len(self.valid_staff_accounts()) > 1

    def auto_select_single_staff_account(self):
        accounts = self.valid_staff_accounts()
        if len(accounts) == 1:
            self.set_current_staff(accounts[0])
            return True
        return False

    def save_staff_accounts(self, accounts):
        self.set_user_setting("staff_accounts", json.dumps(accounts, ensure_ascii=False))
        self.sync_staff_accounts_to_cloud(accounts)

    def sync_staff_accounts_to_cloud(self, accounts=None):
        try:
            if not getattr(self, "user_id", "") or not getattr(self, "token", ""):
                return
            accounts = accounts if isinstance(accounts, list) else self.staff_accounts()
            accounts = self.normalized_staff_accounts(accounts)
            db.child("users").child(self.user_id).child("ayarlar").update({
                "staff_accounts": accounts,
                "staff_pin_enabled": "true" if accounts else "false",
            }, self.token)
            db.child("users").child(self.user_id).child("personel_hesaplari").set(accounts, self.token)
        except Exception:
            pass

    def normalized_staff_accounts(self, accounts):
        normalized = []
        all_permissions = sorted(self.all_staff_permission_keys())
        protected_ids = self.protected_staff_account_ids(accounts)
        for acc in accounts if isinstance(accounts, list) else []:
            if not isinstance(acc, dict):
                continue
            item = dict(acc)
            item_id = str(item.get("id", "") or "")
            if self.is_staff_admin_account(item) or (item_id and item_id in protected_ids):
                item["role"] = "Yönetici"
                item["permissions"] = all_permissions
            normalized.append(item)
        return normalized

    def repair_admin_staff_permissions(self):
        accounts = self.staff_accounts()
        fixed = self.normalized_staff_accounts(accounts)
        if fixed != accounts:
            self.save_staff_accounts(fixed)
        return fixed

    def staff_pin_enabled(self):
        return str(self.user_setting_value("staff_pin_enabled", "false") or "false") == "true"

    def staff_role_key(self, role):
        text = str(role or "").strip()
        try:
            fixed = text.encode("latin1").decode("utf-8")
            if fixed:
                text = fixed
        except Exception:
            pass
        text = self.normalize_upper(text)
        replacements = {
            "Ç": "C",
            "Ğ": "G",
            "İ": "I",
            "Ö": "O",
            "Ş": "S",
            "Ü": "U",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        return text

    def staff_account_name_key(self, account):
        if not isinstance(account, dict):
            return ""
        return self.staff_role_key(account.get("name"))

    def is_staff_admin_account(self, account):
        if not isinstance(account, dict):
            return False
        if str(account.get("id", "") or "") == "owner":
            return True
        if self.staff_role_key(account.get("role")) == "YONETICI":
            return True
        return self.staff_account_name_key(account) in {"YONETICI", "ADMIN", "YONETICI HESABI"}

    def protected_staff_account_ids(self, accounts=None):
        accounts = self.coerce_staff_accounts(accounts) if accounts is not None else self.staff_accounts()
        protected = {
            str(account.get("id", "") or "")
            for account in accounts
            if isinstance(account, dict) and self.is_staff_admin_account(account) and str(account.get("id", "") or "")
        }
        if protected:
            return protected
        for account in accounts:
            if isinstance(account, dict) and str(account.get("name", "") or "").strip():
                account_id = str(account.get("id", "") or "")
                return {account_id} if account_id else set()
        return set()

    def is_protected_staff_account(self, account, accounts=None):
        if not isinstance(account, dict):
            return False
        account_id = str(account.get("id", "") or "")
        return self.is_staff_admin_account(account) or (account_id and account_id in self.protected_staff_account_ids(accounts))

    def hash_staff_pin(self, pin, salt):
        return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()

    def make_staff_account(self, name, role, pin, existing=None, permissions=None):
        existing = existing or {}
        salt = existing.get("salt") or uuid.uuid4().hex
        role = role if role in self.staff_roles() else "Servis Personeli"
        if permissions is None:
            permissions = existing.get("permissions")
        if not isinstance(permissions, list):
            permissions = sorted(self.staff_default_permissions_for_role(role))
        else:
            valid = self.all_staff_permission_keys()
            permissions = sorted({str(p) for p in permissions if str(p) in valid})
        payload = {
            "id": existing.get("id") or uuid.uuid4().hex[:12],
            "name": self.normalize_upper(name).strip(),
            "role": role,
            "permissions": permissions,
            "salt": salt,
            "photo_path": existing.get("photo_path", ""),
            "created_at": existing.get("created_at") or datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        }
        if pin:
            payload["pin_hash"] = self.hash_staff_pin(pin, salt)
        else:
            payload["pin_hash"] = existing.get("pin_hash", "")
        return payload

    def verify_staff_pin(self, account, pin):
        if not isinstance(account, dict):
            return False
        salt = str(account.get("salt", "") or "")
        pin_hash = str(account.get("pin_hash", "") or "")
        return bool(salt and pin_hash and self.hash_staff_pin(pin, salt) == pin_hash)

    def is_admin_staff(self):
        return self.is_staff_admin_account(self.current_staff)

    def staff_can(self, permission):
        if permission == "switch_staff":
            return True
        if self.is_staff_admin_account(self.current_staff):
            return True
        permissions = set(self.current_staff.get("permissions", []))
        if permission == "view":
            return bool(permissions)
        if permission == "admin" and "manage_staff" in permissions:
            return True
        if permission in ("edit_active", "edit_ready", "edit_delivery") and "edit_records" in permissions:
            return True
        if permission == "edit_records" and permissions.intersection({"edit_active", "edit_ready", "edit_delivery"}):
            return True
        return permission in permissions

    def require_staff_permission(self, permission, action_name="Bu işlem"):
        if self.staff_can(permission):
            return True
        QMessageBox.warning(self, "Yetki Yok", f"{action_name} için personel yetkiniz bulunmuyor.\n\nAktif personel: {self.current_staff.get('name', '-')}\nRol: {self.current_staff.get('role', '-')}")
        return False

    def staff_allowed_tabs(self):
        if self.is_staff_admin_account(self.current_staff):
            return set(range(self.tabs.count() if hasattr(self, "tabs") else 18))
        allowed = set()
        for index, permission in self.staff_tab_permission_map().items():
            if permission == "admin":
                visible = self.staff_can("admin") or self.staff_can("manage_staff")
            elif index == 0:
                visible = self.staff_can("view_dashboard") or self.staff_can("cash_add") or self.staff_can("finance_dashboard")
            elif index == 2:
                visible = self.staff_can("view_active") or self.staff_can("edit_active")
            elif index == 3:
                visible = (
                    self.staff_can("view_ready")
                    or self.staff_can("edit_ready")
                    or self.staff_can("view_active")
                    or self.staff_can("edit_active")
                )
            elif index in (4, 5):
                visible = self.staff_can(permission) or self.staff_can("edit_delivery")
            elif index == 8:
                visible = self.staff_can("view_stock") or self.staff_can("stock_add") or self.staff_can("edit_stock")
            elif index == 9:
                visible = self.staff_can("view_wholesale") or self.staff_can("wholesale")
            else:
                visible = self.staff_can(permission)
            if visible:
                allowed.add(index)
        return allowed

    def can_access_tab(self, index):
        return index in self.staff_allowed_tabs()

    def record_edit_permission_for_table(self, table, record=None):
        if table == getattr(self, "table_act", None):
            return "edit_active"
        if table == getattr(self, "table_ready", None):
            return "edit_ready"
        if table == getattr(self, "table_done", None) and isinstance(record, dict) and self.record_status_bucket(record) == "ready":
            return "edit_delivery"
        if table in [getattr(self, "table_done", None), getattr(self, "table_delivered", None)]:
            return "edit_delivery"
        return "edit_records"

    def set_current_staff(self, account):
        role = account.get("role", "Yönetici") if account.get("role", "Yönetici") in self.staff_roles() else "Yönetici"
        self.current_staff = {
            "id": str(account.get("id", "owner") or "owner"),
            "name": self.normalize_upper(account.get("name", "YÖNETİCİ")).strip() or "YÖNETİCİ",
            "role": role,
            "permissions": sorted(self.account_permissions(account)),
        }
        self.apply_staff_permissions()

    def prompt_staff_login_on_start(self):
        if self.should_show_staff_gate():
            self.show_staff_gate(startup=True)

    def prompt_staff_login(self, force=False):
        return self.show_staff_gate(force=force)
        accounts = self.staff_accounts()
        if not accounts:
            if force:
                QMessageBox.information(self, "Personel Girişi", "Personel PIN sistemi açık ama kayıtlı personel bulunamadı.")
            return False
        while True:
            dlg = QDialog(self)
            dlg.setWindowTitle("Personel Girişi")
            dlg.setModal(True)
            lay = QVBoxLayout(dlg)
            lay.addWidget(QLabel("Programa devam etmek için personel seçip PIN girin."))
            account_cb = QComboBox()
        for account in accounts:
            account_cb.addItem(f"{account.get('name', '-')}  |  {account.get('role', '-')}", account)
            pin_input = QLineEdit()
            pin_input.setEchoMode(QLineEdit.EchoMode.Password)
            pin_input.setPlaceholderText("Personel PIN")
            pin_input.setMaxLength(12)
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
            buttons.accepted.connect(dlg.accept)
            buttons.rejected.connect(dlg.reject)
            lay.addWidget(account_cb)
            lay.addWidget(pin_input)
            lay.addWidget(buttons)
            if dlg.exec() != QDialog.DialogCode.Accepted:
                return False
            account = account_cb.currentData()
            if self.verify_staff_pin(account, pin_input.text()):
                self.set_current_staff(account)
                self.log_staff_event(f"Personel girişi: {account.get('name', '')} ({account.get('role', '')})")
                return True
            QMessageBox.warning(self, "Personel Girişi", "PIN hatalı. Lütfen tekrar deneyin.")

    def create_staff_gate_screen(self):
        gate = QWidget()
        gate.setObjectName("StaffGate")
        gate.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        gate.installEventFilter(self)
        root = QVBoxLayout(gate)
        root.setContentsMargins(32, 24, 32, 28)
        root.setSpacing(0)
        root.addStretch(1)

        self.staff_gate_title = QLabel("Personel Girişi")
        self.staff_gate_title.setObjectName("StaffGateTitle")
        self.staff_gate_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_gate_subtitle = QLabel("Profilinizi seçin ve PIN kodunuzla devam edin")
        self.staff_gate_subtitle.setObjectName("StaffGateSubtitle")
        self.staff_gate_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.staff_gate_title)
        root.addWidget(self.staff_gate_subtitle)
        root.addSpacing(16)

        card = QFrame()
        card.setObjectName("StaffGateCard")
        card.setMaximumWidth(820)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(30, 24, 30, 24)
        card_lay.setSpacing(16)

        self.staff_gate_company = QLabel(self.display_company_name())
        self.staff_gate_company.setObjectName("StaffGateCompany")
        self.staff_gate_accounts_layout = QGridLayout()
        self.staff_gate_accounts_layout.setHorizontalSpacing(18)
        self.staff_gate_accounts_layout.setVerticalSpacing(8)
        for col in range(5):
            self.staff_gate_accounts_layout.setColumnStretch(col, 1)
        self.staff_gate_nav_hint = QLabel("← / → yön tuşlarıyla profil değiştirin, Enter ile PIN alanına geçin")
        self.staff_gate_nav_hint.setObjectName("StaffGateNavHint")
        self.staff_gate_nav_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_gate_selected_label = QLabel("Personel seçilmedi")
        self.staff_gate_selected_label.setObjectName("StaffGateSelected")
        self.staff_gate_selected_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_gate_selected_label.hide()
        self.staff_gate_pin = QLineEdit()
        self.staff_gate_pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.staff_gate_pin.setPlaceholderText("PIN kodu")
        self.staff_gate_pin.setMaxLength(12)
        self.staff_gate_pin.setMaximumWidth(280)
        self.staff_gate_pin.setFixedHeight(40)
        self.staff_gate_pin.installEventFilter(self)
        self.staff_gate_pin.returnPressed.connect(self.submit_staff_gate_login)
        self.staff_gate_status = QLabel("")
        self.staff_gate_status.setObjectName("StaffGateStatus")
        self.staff_gate_status.setWordWrap(True)
        self.staff_gate_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.staff_gate_status.setFixedSize(280, 34)
        self.staff_gate_status.hide()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(12)
        btn_enter = QPushButton("Giriş Yap")
        btn_enter.setObjectName("StaffGatePrimary")
        btn_enter.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_enter.setFixedSize(108, 40)
        btn_enter.clicked.connect(self.submit_staff_gate_login)
        btn_back = QPushButton("Geri Dön")
        btn_back.setObjectName("StaffGateSecondary")
        btn_back.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_back.setFixedSize(108, 40)
        btn_back.clicked.connect(self.return_to_login_after_staff_cancel)
        btn_row.addStretch()
        btn_row.addWidget(btn_back)
        btn_row.addWidget(btn_enter)
        btn_row.addStretch()

        self.staff_gate_company.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.staff_gate_company)
        card_lay.addLayout(self.staff_gate_accounts_layout)
        card_lay.addWidget(self.staff_gate_pin, alignment=Qt.AlignmentFlag.AlignCenter)
        card_lay.addWidget(self.staff_gate_status, alignment=Qt.AlignmentFlag.AlignCenter)
        card_lay.addLayout(btn_row)
        root.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)
        root.addStretch(1)
        self.staff_gate_selected_account = None
        self.staff_gate_buttons = []
        self.staff_gate_accounts = []
        self.staff_gate_selected_index = 0
        self.staff_gate_bg_phase = 0
        self.staff_gate_bg_timer = QTimer(self)
        self.staff_gate_bg_timer.timeout.connect(self.tick_staff_gate_background)
        self.staff_gate_bg_timer.start(1800)
        self.apply_staff_gate_style()
        return gate

    def animated_staff_gate_gradient(self, theme):
        theme = str(theme or "Dark")
        if "Light" in theme or "Açık" in theme:
            stops = [
                "stop:0.00 #eef5ff",
                "stop:0.45 #dbeafe",
                "stop:1.00 #f8fafc",
            ]
        elif "Emerald" in theme or "Zümrüt" in theme:
            stops = [
                "stop:0.00 #031712",
                "stop:0.50 #0f2f2a",
                "stop:1.00 #06111f",
            ]
        elif "Ocean" in theme or "Okyanus" in theme:
            stops = [
                "stop:0.00 #061322",
                "stop:0.48 #0b2a45",
                "stop:1.00 #07111f",
            ]
        elif "Graphite" in theme or "Grafit" in theme:
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

    def staff_gate_theme_palette(self):
        theme = str(self.user_setting_value("theme", "Dark") or "Dark")
        aurora = self.animated_staff_gate_gradient(theme)
        if "Light" in theme or "Açık" in theme:
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(255, 255, 255, 0.72)",
                "field_bg": "rgba(255, 255, 255, 0.84)",
                "field_hover": "rgba(255, 255, 255, 0.96)",
                "text": "#0f172a",
                "sub": "#475569",
                "top_text": "#0f172a",
                "border": "rgba(37, 99, 235, 0.24)",
                "accent": "#2563eb",
                "accent_hover": "#0891b2",
                "button_stops": ("#2563eb", "#06b6d4", "#14b8a6", "#84cc16"),
                "avatar_bg": "rgba(255, 255, 255, 0.70)",
                "avatar_text": "#0f172a",
            }
        if "Emerald" in theme or "Zümrüt" in theme:
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(6, 78, 59, 0.46)",
                "field_bg": "rgba(236, 253, 245, 0.10)",
                "field_hover": "rgba(236, 253, 245, 0.16)",
                "text": "#ecfdf5",
                "sub": "#bbf7d0",
                "top_text": "#ecfdf5",
                "border": "rgba(52, 211, 153, 0.35)",
                "accent": "#10b981",
                "accent_hover": "#34d399",
                "button_stops": ("#059669", "#14b8a6", "#22d3ee", "#84cc16"),
                "avatar_bg": "rgba(236, 253, 245, 0.18)",
                "avatar_text": "#ecfdf5",
            }
        if "Ocean" in theme or "Okyanus" in theme:
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(8, 47, 73, 0.50)",
                "field_bg": "rgba(224, 242, 254, 0.10)",
                "field_hover": "rgba(224, 242, 254, 0.16)",
                "text": "#f0f9ff",
                "sub": "#bae6fd",
                "top_text": "#f8fbff",
                "border": "rgba(125, 211, 252, 0.35)",
                "accent": "#0ea5e9",
                "accent_hover": "#22d3ee",
                "button_stops": ("#2563eb", "#06b6d4", "#38bdf8", "#a78bfa"),
                "avatar_bg": "rgba(224, 242, 254, 0.18)",
                "avatar_text": "#f0f9ff",
            }
        if "Graphite" in theme or "Grafit" in theme:
            return {
                "frame_bg": aurora,
                "card_bg": "rgba(15, 23, 42, 0.58)",
                "field_bg": "rgba(255, 255, 255, 0.08)",
                "field_hover": "rgba(255, 255, 255, 0.13)",
                "text": "#f8fafc",
                "sub": "#cbd5e1",
                "top_text": "#f8fafc",
                "border": "rgba(148, 163, 184, 0.30)",
                "accent": "#60a5fa",
                "accent_hover": "#818cf8",
                "button_stops": ("#2563eb", "#06b6d4", "#8b5cf6", "#64748b"),
                "avatar_bg": "rgba(255, 255, 255, 0.14)",
                "avatar_text": "#f8fafc",
            }
        return {
            "frame_bg": aurora,
            "card_bg": "rgba(15, 23, 42, 0.74)",
            "field_bg": "rgba(255, 255, 255, 0.08)",
            "field_hover": "rgba(255, 255, 255, 0.13)",
            "text": "#ffffff",
            "sub": "#cbd5e1",
            "top_text": "#ffffff",
            "border": "rgba(96, 165, 250, 0.32)",
            "accent": "#38bdf8",
            "accent_hover": "#a78bfa",
            "button_stops": ("#1d4ed8", "#2563eb", "#06b6d4", "#38bdf8"),
            "avatar_bg": "rgba(255, 255, 255, 0.14)",
            "avatar_text": "#ffffff",
        }

    def apply_staff_gate_style(self):
        if not hasattr(self, "staff_gate"):
            return
        p = self.staff_gate_theme_palette()
        b0, b1, b2, b3 = p["button_stops"]
        self.staff_gate.setStyleSheet(f"""
            QWidget#StaffGate {{
                background: {p["frame_bg"]};
            }}
            QFrame#StaffGateCard {{
                background-color: {p["card_bg"]};
                border: 1px solid {p["border"]};
                border-radius: 24px;
            }}
            QLabel#StaffGateTitle {{
                color: {p["top_text"]};
                font-size: 28px;
                font-weight: 900;
                letter-spacing: 0px;
                background: transparent;
            }}
            QLabel#StaffGateSubtitle, QLabel#StaffGateSelected, QLabel#StaffGateSection, QLabel#StaffGateNavHint {{
                color: {p["sub"]};
                font-size: 13px;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#StaffGateCompany {{
                color: {p["text"]};
                font-size: 18px;
                font-weight: 900;
                padding: 0 0 8px 0;
                background: transparent;
            }}
            QLabel#StaffProfileName {{
                color: {p["text"]};
                font-size: 13px;
                font-weight: 800;
                padding-top: 8px;
                background: transparent;
            }}
            QLabel#StaffGateStatus {{
                color: #ffffff;
                font-size: 12px;
                font-weight: 900;
                min-height: 30px;
                padding: 4px 10px;
                border-radius: 8px;
                border: 1px solid rgba(248, 113, 113, 0.54);
                background-color: rgba(127, 29, 29, 0.72);
            }}
            QPushButton#StaffAccountButton {{
                text-align: center;
                padding: 0;
                border: none;
                background-color: transparent;
                color: {p["avatar_text"]};
                font-weight: 900;
                font-size: 28px;
            }}
            QPushButton#StaffAccountButton[carouselRole="center"] {{
                border: none;
                background-color: transparent;
            }}
            QPushButton#StaffAccountButton[carouselRole="side"] {{
                border: none;
                background-color: transparent;
            }}
            QPushButton#StaffAccountButton[carouselRole="far"] {{
                color: {p["sub"]};
                border: none;
                background-color: transparent;
            }}
            QPushButton#StaffAccountButton:checked {{
                border: none;
            }}
            QPushButton#StaffAccountButton:hover {{
                border: none;
                background-color: transparent;
            }}
            QLineEdit {{
                background-color: {p["field_bg"]};
                color: {p["text"]};
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 15px;
                font-weight: 800;
                selection-background-color: {p["accent"]};
            }}
            QLineEdit:hover {{
                border: 1px solid rgba(125, 211, 252, 0.45);
                background-color: {p["field_hover"]};
            }}
            QLineEdit:focus {{
                border: 2px solid {p["accent_hover"]};
                padding: 7px 11px;
                background-color: {p["field_hover"]};
            }}
            QPushButton#StaffGatePrimary, QPushButton#StaffGateSecondary {{
                background-color: rgba(15, 23, 42, 0.42);
                color: white;
                border: 1px solid rgba(255, 255, 255, 0.26);
                border-radius: 8px;
                padding: 8px 18px;
                font-weight: 900;
                font-size: 14px;
            }}
            QPushButton#StaffGatePrimary:hover, QPushButton#StaffGateSecondary:hover {{
                background-color: rgba(15, 23, 42, 0.58);
                border: 1px solid {p["accent"]};
            }}
        """)

    def tick_staff_gate_background(self):
        gate = getattr(self, "staff_gate", None)
        if gate is None or not gate.isVisible():
            return
        self.staff_gate_bg_phase = (int(getattr(self, "staff_gate_bg_phase", 0)) + 2) % 360
        self.apply_staff_gate_style()

    def refresh_staff_gate_accounts(self):
        if not hasattr(self, "staff_gate_accounts_layout"):
            return
        self.staff_gate_buttons = []
        previous_id = None
        if isinstance(getattr(self, "staff_gate_selected_account", None), dict):
            previous_id = self.staff_gate_selected_account.get("id")
        accounts = [account for account in self.staff_accounts() if isinstance(account, dict)]
        display_accounts = []
        if not any(self.is_staff_admin_account(account) for account in accounts):
            display_accounts.append({
                "id": "__initial_admin__",
                "name": "YÖNETİCİ",
                "role": "Yönetici",
                "setup_initial_admin": True,
            })
        display_accounts.extend(accounts)
        self.staff_gate_accounts = display_accounts
        if previous_id:
            self.staff_gate_selected_index = next((idx for idx, account in enumerate(display_accounts) if account.get("id") == previous_id), 0)
        else:
            self.staff_gate_selected_index = min(getattr(self, "staff_gate_selected_index", 0), max(len(display_accounts) - 1, 0))
        self.render_staff_gate_carousel()
        if display_accounts:
            self.update_staff_gate_selected_account(clear_pin=True, focus_pin=True)

    def clear_staff_gate_accounts_layout(self):
        while self.staff_gate_accounts_layout.count():
            item = self.staff_gate_accounts_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def set_staff_gate_button_size(self, button, size):
        button.setFixedSize(size)
        button.setProperty("normalSize", size)
        normal_icon = QSize(max(54, size.width() - 18), max(54, size.height() - 18))
        hover_icon = QSize(min(size.width(), normal_icon.width() + 10), min(size.height(), normal_icon.height() + 10))
        button.setProperty("normalIconSize", normal_icon)
        button.setProperty("hoverIconSize", hover_icon)
        button.setIconSize(normal_icon)
        self.apply_staff_avatar_mask(button)

    def apply_staff_avatar_mask(self, button):
        if not isinstance(button, QPushButton):
            return
        button.clearMask()

    def staff_color(self, value, fallback="#ffffff"):
        color = QColor(str(value or ""))
        if not color.isValid():
            color = QColor(fallback)
        return color

    def make_staff_avatar_icon(self, account, initials, size, selected=False):
        p = self.staff_gate_theme_palette()
        dpr = 3
        canvas_size = max(72, int(size)) * dpr
        margin = 7 * dpr
        inner_margin = 10 * dpr
        rounded = QPixmap(canvas_size, canvas_size)
        rounded.fill(Qt.GlobalColor.transparent)

        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        path = str(account.get("photo_path", "") or "") if isinstance(account, dict) else ""
        if path and os.path.exists(path):
            pix = QPixmap(path)
        else:
            pix = QPixmap()

        if not pix.isNull():
            side = min(pix.width(), pix.height())
            source = pix.copy((pix.width() - side) // 2, (pix.height() - side) // 2, side, side)
            inner_size = canvas_size - inner_margin * 2
            source = source.scaled(inner_size, inner_size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)

            base = self.staff_color(p.get("accent", "#38bdf8"), "#38bdf8")
            base.setAlpha(70 if selected else 46)
            painter.setBrush(base)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(margin, margin, canvas_size - margin * 2, canvas_size - margin * 2)

            clipped = QPixmap(canvas_size, canvas_size)
            clipped.fill(Qt.GlobalColor.transparent)
            clip_painter = QPainter(clipped)
            clip_painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            clip_painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            clip_painter.setBrush(QColor(255, 255, 255, 255))
            clip_painter.setPen(Qt.PenStyle.NoPen)
            clip_painter.drawEllipse(inner_margin, inner_margin, inner_size, inner_size)
            clip_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
            clip_painter.drawPixmap(inner_margin, inner_margin, source)
            clip_painter.end()
            painter.drawPixmap(0, 0, clipped)
        else:
            base = self.staff_color(p.get("accent", "#38bdf8"), "#38bdf8")
            base.setAlpha(90 if selected else 58)
            painter.setBrush(base)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(margin, margin, canvas_size - margin * 2, canvas_size - margin * 2)

            glow = self.staff_color(p.get("accent_hover", "#a78bfa"), "#a78bfa")
            glow.setAlpha(42 if selected else 28)
            painter.setPen(QPen(glow, 8 * dpr))
            painter.drawEllipse(margin + 2 * dpr, margin + 2 * dpr, canvas_size - (margin + 2 * dpr) * 2, canvas_size - (margin + 2 * dpr) * 2)

            silhouette = self.staff_color(p.get("avatar_text", "#ffffff"), "#ffffff")
            silhouette.setAlpha(232 if selected else 218)
            painter.setBrush(silhouette)
            painter.setPen(Qt.PenStyle.NoPen)
            head_size = int(canvas_size * 0.25)
            head_x = int((canvas_size - head_size) / 2)
            head_y = int(canvas_size * 0.25)
            painter.drawEllipse(head_x, head_y, head_size, head_size)

            shoulder_w = int(canvas_size * 0.48)
            shoulder_h = int(canvas_size * 0.24)
            shoulder_x = int((canvas_size - shoulder_w) / 2)
            shoulder_y = int(canvas_size * 0.56)
            painter.drawRoundedRect(shoulder_x, shoulder_y, shoulder_w, shoulder_h, int(shoulder_h * 0.58), int(shoulder_h * 0.58))

        track = QColor(255, 255, 255, 58)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(track, 2 * dpr))
        painter.drawEllipse(margin, margin, canvas_size - margin * 2, canvas_size - margin * 2)

        ring = self.staff_color(p.get("accent_hover" if selected else "accent", "#38bdf8"), "#38bdf8")
        ring.setAlpha(240 if selected else 170)
        painter.setPen(QPen(ring, 3 * dpr))
        painter.drawEllipse(margin + dpr, margin + dpr, canvas_size - (margin + dpr) * 2, canvas_size - (margin + dpr) * 2)
        painter.end()
        return QIcon(rounded)

    def staff_photo_icon(self, account, size):
        initials = self.staff_avatar_text(account.get("name", "")) if isinstance(account, dict) else "P"
        return self.make_staff_avatar_icon(account or {}, initials, size, selected=False)

    def render_staff_gate_carousel(self):
        if not hasattr(self, "staff_gate_accounts_layout"):
            return
        self.clear_staff_gate_accounts_layout()
        self.staff_gate_buttons = []
        accounts = getattr(self, "staff_gate_accounts", [])
        if not accounts:
            self.staff_gate_selected_account = None
            return
        selected = getattr(self, "staff_gate_selected_index", 0) % len(accounts)
        self.staff_gate_selected_index = selected
        size_map = {
            "center": QSize(112, 112),
            "side": QSize(112, 112),
            "far": QSize(112, 112),
        }
        columns = min(5, max(1, len(accounts)))
        for idx, account in enumerate(accounts):
            account = accounts[idx]
            name = str(account.get("name", "-") or "-")
            role = str(account.get("role", "-") or "-")
            avatar = self.staff_avatar_text(name)
            carousel_role = "center" if idx == selected else "side"
            if account.get("setup_initial_admin"):
                avatar_text = "Y"
                tooltip = "İlk yönetici PIN'i oluştur"
            else:
                avatar_text = avatar
                tooltip = f"{name} profiliyle giriş yap"
            btn = QPushButton("")
            btn.setObjectName("StaffAccountButton")
            btn.setCheckable(True)
            is_selected = idx == selected
            btn.setChecked(is_selected)
            btn.setProperty("carouselRole", carousel_role)
            btn.setProperty("staffAvatarCard", True)
            self.set_staff_gate_button_size(btn, size_map[carousel_role])
            normal_icon_size = btn.property("normalIconSize")
            icon_side = normal_icon_size.width() if isinstance(normal_icon_size, QSize) else max(54, size_map[carousel_role].width() - 18)
            btn.setIcon(self.make_staff_avatar_icon(account, avatar_text, icon_side, selected=is_selected))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.installEventFilter(self)
            btn.clicked.connect(lambda checked=False, i=idx: self.select_staff_gate_index(i))
            profile = QWidget()
            profile.setObjectName("StaffProfileItem")
            profile.setFixedSize(138, 138)
            profile_lay = QVBoxLayout(profile)
            profile_lay.setContentsMargins(0, 0, 0, 0)
            profile_lay.setSpacing(0)
            shown_name = name if len(name) <= 18 else f"{name[:16]}..."
            label = QLabel(shown_name)
            label.setObjectName("StaffProfileName")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedWidth(126)
            label.setToolTip(f"{name} - {role}")
            profile_lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
            profile_lay.addWidget(label, alignment=Qt.AlignmentFlag.AlignCenter)
            self.staff_gate_accounts_layout.addWidget(profile, idx // columns, idx % columns, alignment=Qt.AlignmentFlag.AlignCenter)
            self.staff_gate_buttons.append(btn)

    def select_staff_gate_index(self, index):
        accounts = getattr(self, "staff_gate_accounts", [])
        if not accounts:
            return
        index = index % len(accounts)
        changed = index != getattr(self, "staff_gate_selected_index", 0)
        self.staff_gate_selected_index = index
        self.render_staff_gate_carousel()
        self.update_staff_gate_selected_account(clear_pin=changed, focus_pin=True)

    def move_staff_gate_selection(self, direction):
        accounts = getattr(self, "staff_gate_accounts", [])
        if not accounts:
            return
        self.select_staff_gate_index(getattr(self, "staff_gate_selected_index", 0) + direction)

    def update_staff_gate_selected_account(self, clear_pin=False, focus_pin=False):
        accounts = getattr(self, "staff_gate_accounts", [])
        if not accounts:
            self.staff_gate_selected_account = None
            self.staff_gate_selected_label.setText("Personel seçilmedi")
            return
        account = accounts[getattr(self, "staff_gate_selected_index", 0) % len(accounts)]
        self.staff_gate_selected_account = account
        if account.get("setup_initial_admin"):
            self.staff_gate_selected_label.setText("<b>YÖNETİCİ</b><br><span style='font-size:12px;'>İlk PIN kurulumu</span>")
            self.staff_gate_pin.setPlaceholderText("Yeni yönetici PIN'i")
        else:
            name = html.escape(str(account.get("name", "-") or "-"))
            role = html.escape(str(account.get("role", "-") or "-"))
            self.staff_gate_selected_label.setText(f"<b>{name}</b><br><span style='font-size:12px;'>{role}</span>")
            self.staff_gate_pin.setPlaceholderText("PIN kodu")
        self.set_staff_gate_status("")
        if clear_pin:
            self.staff_gate_pin.clear()
        if focus_pin:
            self.staff_gate_pin.setFocus()

    def set_staff_gate_status(self, text):
        if not hasattr(self, "staff_gate_status"):
            return
        text = str(text or "")
        self.staff_gate_status.setText(text)
        self.staff_gate_status.setVisible(bool(text.strip()))

    def staff_avatar_text(self, name):
        clean = self.normalize_upper(str(name or "")).strip()
        parts = re.findall(r"[A-Z0-9ÇĞİÖŞÜ]+", clean)
        initials = "".join(part[0] for part in parts[:2])
        return initials or "P"

    def animate_staff_avatar_button(self, button, hovered):
        normal_icon = button.property("normalIconSize")
        hover_icon = button.property("hoverIconSize")
        if not isinstance(normal_icon, QSize):
            normal_icon = QSize(94, 94)
        if not isinstance(hover_icon, QSize):
            hover_icon = QSize(104, 104)
        target = hover_icon if hovered else normal_icon
        if button.iconSize() == target:
            return
        if not hasattr(self, "staff_avatar_animations"):
            self.staff_avatar_animations = {}
        anim_key = id(button)
        old_anim = self.staff_avatar_animations.get(anim_key)
        if old_anim:
            old_anim.stop()
        anim = QPropertyAnimation(button, b"iconSize", self)
        anim.setDuration(145)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(button.iconSize())
        anim.setEndValue(target)
        anim.finished.connect(lambda k=anim_key: self.staff_avatar_animations.pop(k, None))
        self.staff_avatar_animations[anim_key] = anim
        if hovered:
            button.raise_()
        anim.start()

    def select_staff_gate_account(self, account, button):
        accounts = getattr(self, "staff_gate_accounts", [])
        index = next((idx for idx, item in enumerate(accounts) if item.get("id") == account.get("id")), None)
        if index is None:
            self.staff_gate_selected_account = account
            self.update_staff_gate_selected_account(clear_pin=True, focus_pin=True)
            return
        self.select_staff_gate_index(index)

    def show_staff_gate(self, startup=False, force=False):
        if not hasattr(self, "staff_gate"):
            return False
        if startup and hasattr(self.manager, "apply_main_window_geometry"):
            self.manager.apply_main_window_geometry()
        self.staff_gate_required = self.should_show_staff_gate()
        if not self.staff_gate_required:
            self.auto_select_single_staff_account()
            if hasattr(self, "global_search_bar"):
                self.global_search_bar.show()
            if hasattr(self, "main_body"):
                self.main_body.show()
            if force:
                QMessageBox.information(self, "Personel Girişi", "Personel değiştirme ekranı için en az iki kullanıcı profili eklenmiş olmalı.")
            self.update_staff_switch_button_visibility()
            return False
        self.apply_staff_gate_style()
        self.refresh_staff_gate_accounts()
        if hasattr(self, "staff_gate_company"):
            self.staff_gate_company.setText(self.display_company_name())
        if hasattr(self, "main_body"):
            self.main_body.hide()
        if hasattr(self, "global_search_bar"):
            self.global_search_bar.hide()
        self.staff_gate.show()
        self.staff_gate.raise_()
        return True

    def unlock_staff_gate(self):
        if hasattr(self, "staff_gate"):
            self.staff_gate.hide()
        if hasattr(self, "global_search_bar"):
            self.global_search_bar.show()
        if hasattr(self, "main_body"):
            self.main_body.show()
        self.apply_staff_permissions()

    def submit_staff_gate_login(self):
        account = getattr(self, "staff_gate_selected_account", None)
        if not account:
            self.set_staff_gate_status("Lütfen personel seçin.")
            return
        pin = self.staff_gate_pin.text()
        if account.get("setup_initial_admin"):
            if len(pin.strip()) < 4:
                self.set_staff_gate_status("Yönetici PIN'i en az 4 haneli olmalı.")
                self.staff_gate_pin.setFocus()
                return
            admin = self.make_staff_account("YÖNETİCİ", "Yönetici", pin.strip(), permissions=sorted(self.all_staff_permission_keys()))
            accounts = [acc for acc in self.staff_accounts() if isinstance(acc, dict)]
            accounts = [acc for acc in accounts if not self.is_staff_admin_account(acc)]
            accounts.insert(0, admin)
            self.save_staff_accounts(accounts)
            self.set_user_setting("staff_pin_enabled", "true")
            self.set_current_staff(admin)
            self.log_staff_event("İlk yönetici PIN'i oluşturuldu")
            self.staff_gate_pin.clear()
            self.unlock_staff_gate()
            self.build_sidebar_navigation()
            self.apply_staff_permissions()
            return
        if self.verify_staff_pin(account, pin):
            self.set_current_staff(account)
            self.log_staff_event(f"Personel girişi: {account.get('name', '')} ({account.get('role', '')})")
            self.staff_gate_pin.clear()
            self.unlock_staff_gate()
            return
        self.set_staff_gate_status("PIN hatalı. Lütfen tekrar deneyin.")
        self.staff_gate_pin.selectAll()
        self.staff_gate_pin.setFocus()

    def return_to_login_after_staff_cancel(self):
        try:
            for timer_name in ("refresh_timer", "token_refresh_timer", "blink_timer", "ticker_timer"):
                timer = getattr(self, timer_name, None)
                if timer is not None:
                    timer.stop()
            if getattr(self, "stream_worker", None):
                self.stream_worker.stop()
                self.stream_worker.quit()
                self.stream_worker.wait(1000)
            self.manager.setCurrentIndex(0)
            self.manager.setFixedSize(700, 520)
            if hasattr(self.manager, "center_on_active_screen"):
                self.manager.center_on_active_screen(force=True, reset_user_position=True)
            self.manager.removeWidget(self)
            self.deleteLater()
        except Exception:
            self.close()

    def log_staff_event(self, detail):
        try:
            db.child("users").child(self.user_id).child("personel_loglari").push({
                "tarih": datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
                "detay": detail,
                "personel": self.current_staff.get("name", "YÖNETİCİ"),
                "rol": self.current_staff.get("role", "Yönetici"),
                "hesap": self.user_email,
            }, self.token)
            self.audit_log("Personel", detail, "personel", self.current_staff.get("id", ""))
        except Exception:
            pass

    def show_audit_log_dialog(self):
        if not self.require_staff_permission("admin", "Denetim loglarını görüntüleme"):
            return

        read_status = {"text": ""}

        def audit_target_label(log):
            module_names = {
                "kayitlar": "Cihaz Kaydı",
                "stok": "Stok",
                "sabit_bayiler": "Bayi",
                "firmalar": "Toptancı",
                "toptanci": "Toptancı Parça",
                "toptanci_odemeler": "Toptancı Ödemesi",
                "kasa": "Kasa",
                "cop_kutusu": "Çöp Kutusu",
                "personel": "Personel",
                "sistem": "Sistem",
            }
            target_type = str(log.get("hedef_tur", "") or "")
            target_id = str(log.get("hedef_id", "") or "")
            label = module_names.get(target_type, target_type or "Genel")
            if target_type == "kayitlar" and target_id:
                try:
                    rec = self.get_local_record(target_id)
                    if isinstance(rec, dict):
                        code = str(rec.get("c_no", "") or "").strip()
                        device = str(rec.get("ci", "") or "").strip()
                        if code:
                            return f"{label}: {code}" + (f" / {device[:24]}" if device else "")
                except Exception:
                    pass
            if not target_id:
                return label
            short_id = target_id if len(target_id) <= 14 else f"{target_id[:8]}..."
            return f"{label}: {short_id}"

        def load_logs():
            merged = {}
            counts = {"korumali": 0, "yedek": 0, "yerel": 0, "kayit_ici": 0}
            blocked = []
            paths = [
                ("korumali", db.child("audit_logs").child(self.user_id)),
                ("yedek", db.child("users").child(self.user_id).child("denetim_loglari")),
                ("personel", db.child("users").child(self.user_id).child("personel_loglari")),
            ]
            for source, ref in paths:
                try:
                    data = safe_dict_parse(ref.get(self.token).val() or {})
                except Exception as e:
                    if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                        try:
                            data = safe_dict_parse(ref.get(self.token).val() or {})
                        except Exception as retry_error:
                            blocked.append(source)
                            data = {}
                    else:
                        blocked.append(source)
                        data = {}
                if isinstance(data, dict):
                    counts[source] = len(data)
                    for key, value in data.items():
                        if isinstance(value, dict):
                            item = dict(value)
                            item.setdefault("kaynak", source)
                            if source == "personel":
                                item.setdefault("islem", "Personel")
                                item.setdefault("hedef_tur", "personel")
                                item.setdefault("hedef_id", "")
                            event_id = str(item.get("event_id", "") or "")
                            merge_key = event_id if event_id else f"{source}:{key}"
                            if merge_key in merged:
                                continue
                            merged[merge_key] = item

            local_logs = self.read_local_audit_cache()
            if isinstance(local_logs, dict):
                counts["yerel"] = len(local_logs)
                for key, value in local_logs.items():
                    if not isinstance(value, dict):
                        continue
                    item = dict(value)
                    item.setdefault("kaynak", "yerel")
                    event_id = str(item.get("event_id", "") or "")
                    merge_key = event_id if event_id else f"yerel:{key}"
                    if merge_key not in merged:
                        merged[merge_key] = item

            for key, value in getattr(self, "audit_session_logs", {}).items():
                if not isinstance(value, dict):
                    continue
                item = dict(value)
                item.setdefault("kaynak", "oturum")
                event_id = str(item.get("event_id", "") or key)
                if event_id not in merged:
                    merged[event_id] = item

            embedded_logs = self.embedded_record_audit_entries()
            if isinstance(embedded_logs, dict):
                counts["kayit_ici"] = len(embedded_logs)
                for key, value in embedded_logs.items():
                    if not isinstance(value, dict):
                        continue
                    item = dict(value)
                    item.setdefault("kaynak", "kayıt içi")
                    event_id = str(item.get("event_id", "") or key)
                    if event_id not in merged:
                        merged[event_id] = item

            blocked_text = f" | İzin yok: {', '.join(blocked)}" if blocked else ""
            read_status["text"] = f"Okunan kayıt: {len(merged)} | Korumalı: {counts['korumali']} | Yedek: {counts['yedek']} | Yerel: {counts['yerel']} | Kayıt içi: {counts['kayit_ici']}{blocked_text}"
            return merged

        raw_logs = load_logs()
        if not isinstance(raw_logs, dict):
            raw_logs = {}

        dlg = QDialog(self)
        dlg.setWindowTitle("Denetim Logları")
        dlg.resize(1050, 650)
        lay = QVBoxLayout(dlg)

        info = QLabel("Personel işlemleri burada kronolojik olarak saklanır. Bu ekranda silme işlemi bulunmaz.")
        info.setWordWrap(True)
        status_label = QLabel(read_status.get("text", ""))
        status_label.setStyleSheet("color:#38bdf8; font-weight:700; padding:2px 0;")
        search_row = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Personel, işlem, kayıt no veya detay ara...")
        btn_refresh = QPushButton("Yenile")
        btn_test = QPushButton("Test Logu Yaz")
        search_row.addWidget(search, 1)
        search_row.addWidget(btn_test)
        search_row.addWidget(btn_refresh)

        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Tarih", "Personel", "Rol", "İşlem", "Kayıt / Modül", "Detay"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        logs_holder = {"data": raw_logs}

        def sort_key(item):
            key, log = item
            if isinstance(log, dict):
                ts = str(log.get("ts", "") or "")
                if ts:
                    return ts
                tarih = str(log.get("tarih", "") or "")
                try:
                    return datetime.datetime.strptime(tarih, "%d.%m.%Y %H:%M:%S").isoformat()
                except Exception:
                    pass
            return str(key)

        def render():
            query = self.normalize_search_text(search.text())
            entries = []
            for key, log in sorted(logs_holder["data"].items(), key=sort_key, reverse=True):
                if not isinstance(log, dict):
                    continue
                target = audit_target_label(log)
                values = [
                    str(log.get("tarih", "")),
                    str(log.get("personel", "")),
                    str(log.get("rol", "")),
                    str(log.get("islem", "")),
                    target,
                    str(log.get("detay", "")),
                ]
                searchable = self.normalize_search_text(" ".join(values))
                if query and query not in searchable:
                    continue
                entries.append(values)

            table.setRowCount(0)
            for row, values in enumerate(entries):
                table.insertRow(row)
                for col, text in enumerate(values):
                    item = QTableWidgetItem(text)
                    item.setToolTip(text)
                    table.setItem(row, col, item)

        def refresh_logs():
            data = load_logs()
            logs_holder["data"] = data if isinstance(data, dict) else {}
            status_label.setText(read_status.get("text", ""))
            render()

        def write_test_log():
            result = self.audit_log("Denetim Testi", "Denetim log yazma testi", "sistem", "audit-test")
            refresh_logs()
            ok = bool(result.get("ok")) if isinstance(result, dict) else bool(result)
            if ok and isinstance(result, dict) and isinstance(result.get("payload"), dict):
                event_id = result.get("event_id") or result["payload"].get("event_id") or uuid.uuid4().hex
                logs_holder["data"][str(event_id)] = result["payload"]
                render()
                status_label.setText(
                    f"{read_status.get('text', '')} | Son test: korumalı={'OK' if result.get('protected') else 'YOK'}, "
                    f"yedek={'OK' if result.get('backup') else 'YOK'}, yerel={'OK' if result.get('local') else 'YOK'}"
                )
            if ok:
                QMessageBox.information(
                    dlg,
                    "Denetim Logları",
                    "Test logu yazıldı ve ekrana eklendi.\n\n"
                    f"Korumalı alan: {'OK' if isinstance(result, dict) and result.get('protected') else 'YOK'}\n"
                    f"Yedek alan: {'OK' if isinstance(result, dict) and result.get('backup') else 'YOK'}\n"
                    f"Yerel önbellek: {'OK' if isinstance(result, dict) and result.get('local') else 'YOK'}"
                )
            else:
                err = result.get("error", "") if isinstance(result, dict) else ""
                QMessageBox.warning(dlg, "Denetim Logları", f"Test logu yazılamadı. Firebase Rules veya oturum yetkisini kontrol edin.\n\n{err}")

        search.textChanged.connect(render)
        btn_refresh.clicked.connect(refresh_logs)
        btn_test.clicked.connect(write_test_log)
        render()

        lay.addWidget(info)
        lay.addWidget(status_label)
        lay.addLayout(search_row)
        lay.addWidget(table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(dlg.accept)
        lay.addWidget(buttons)
        dlg.exec()

    def apply_dashboard_card_mode(self, compact=False):
        if not hasattr(self, "operational_widgets"):
            return
        max_height = 132 if compact else 16777215
        min_height = 104 if compact else 0
        vertical_policy = QSizePolicy.Policy.Fixed if compact else QSizePolicy.Policy.Expanding
        cards_panel = getattr(self, "dashboard_cards_panel", None)
        if cards_panel is not None:
            cards_panel.setMaximumHeight(152 if compact else 16777215)
            cards_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed if compact else QSizePolicy.Policy.Expanding)
        for widget in getattr(self, "operational_widgets", []):
            widget.setMinimumHeight(min_height)
            widget.setMaximumHeight(max_height)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, vertical_policy)
        cash_panel = getattr(self, "cash_entry_panel", None)
        if cash_panel is not None:
            cash_panel.setMaximumHeight(118 if compact else 136)
            cash_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        bottom_spacer = getattr(self, "dashboard_bottom_spacer", None)
        if bottom_spacer is not None:
            bottom_spacer.setVisible(compact)

    def apply_staff_permissions(self, rebuild_sidebar=False):
        if not hasattr(self, "tabs"):
            return
        allowed_tabs = self.staff_allowed_tabs()
        for idx in range(self.tabs.count()):
            visible = idx in allowed_tabs
            try:
                self.tabs.setTabVisible(idx, visible)
            except Exception:
                self.tabs.setTabEnabled(idx, visible)
            if idx in getattr(self, "nav_buttons", {}):
                self.nav_buttons[idx].setVisible(visible)
                self.nav_buttons[idx].setEnabled(visible)
        if self.tabs.currentIndex() not in allowed_tabs and allowed_tabs:
            self.tabs.setCurrentIndex(min(allowed_tabs))

        finance_allowed = self.staff_can("finance")
        cash_add_allowed = self.staff_can("cash_add")
        finance_dashboard_allowed = self.staff_can("finance_dashboard")
        finance_dashboard_visible = finance_dashboard_allowed and self.user_setting_value("show_finance_dashboard", "false") == "true"
        self.apply_dashboard_card_mode(compact=not finance_dashboard_visible)
        for widget in getattr(self, "finance_widgets", []):
            widget.setVisible(finance_dashboard_visible)
        finance_columns = [
            (getattr(self, "table_act", None), [5]),
            (getattr(self, "table_ready", None), [5]),
            (getattr(self, "table_done", None), [5, 9]),
            (getattr(self, "table_delivered", None), [5, 9]),
            (getattr(self, "table_bayi", None), [4, 6]),
            (getattr(self, "table_dokum", None), [5, 6]),
            (getattr(self, "table_musteri_gecmis", None), [5]),
        ]
        for table, cols in finance_columns:
            if table is None:
                continue
            for col in cols:
                if col < table.columnCount():
                    table.setColumnHidden(col, not finance_allowed)
        if hasattr(self, "table_kasa"):
            self.table_kasa.setVisible(finance_dashboard_allowed)
        cash_panel = getattr(self, "cash_entry_panel", None)
        if cash_panel is not None:
            cash_panel.setVisible(cash_add_allowed or finance_dashboard_allowed)
        title_widget = getattr(self, "lbl_kasa_title", None)
        if title_widget is not None:
            title_widget.setVisible(cash_add_allowed or finance_dashboard_allowed)
        for widget_name in ["k_tip", "k_odeme_tipi", "k_aciklama", "k_tutar", "b_kasa_ekle"]:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setVisible(cash_add_allowed)
        for widget_name in ["kasa_summary_label", "kasa_period_cb", "lbl_kasa_period_summary"]:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setVisible(finance_dashboard_visible)
        for widget_name in ["lbl_toplam", "lbl_alacak", "lbl_done_nakit", "lbl_done_kart", "lbl_done_eft", "lbl_delivered_nakit", "lbl_delivered_kart", "lbl_delivered_eft", "lbl_delivered_summary", "btn_delivered_excel"]:
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setVisible(finance_allowed)
        if hasattr(self, "staff_status_label"):
            self.staff_status_label.setText(f"Aktif personel: {self.current_staff.get('name', '-')} ({self.current_staff.get('role', '-')})")
        if hasattr(self, "sidebar_staff_label"):
            self.sidebar_staff_label.setText(f"{self.current_staff.get('name', '-')} · {self.current_staff.get('role', '-')}")

        self.update_staff_switch_button_visibility()

    def refresh_staff_list(self):
        if not hasattr(self, "staff_list"):
            return
        self.staff_list.clear()
        accounts = [
            account for account in self.repair_admin_staff_permissions()
            if isinstance(account, dict) and str(account.get("name", "") or "").strip()
        ]
        if hasattr(self, "staff_count_label"):
            self.staff_count_label.setText(f"Toplam personel: {len(accounts)}")
        for account in accounts:
            perm_count = len(self.account_permissions(account))
            item = QListWidgetItem(f"{account.get('name', '-')}  |  {account.get('role', '-')}  |  {perm_count} yetki")
            item.setData(Qt.ItemDataRole.UserRole, account)
            self.staff_list.addItem(item)

    def clear_staff_form_for_new_account(self):
        if not hasattr(self, "staff_name_in"):
            return
        if hasattr(self, "staff_list"):
            self.staff_list.clearSelection()
            self.staff_list.setCurrentRow(-1)
        self.staff_name_in.clear()
        self.staff_role_in.blockSignals(True)
        self.staff_role_in.setEnabled(True)
        self.staff_role_in.setToolTip("")
        self.staff_role_in.setCurrentText("Servis Personeli")
        self.staff_role_in.blockSignals(False)
        self.set_staff_permission_checks(self.staff_default_permissions_for_role("Servis Personeli"))
        self.set_staff_permission_checks_locked(False)
        self.staff_pin_in.clear()
        self.staff_pin_in.setPlaceholderText("Yeni personel PIN")
        self.update_staff_delete_button_state(None)
        self.staff_name_in.setFocus()

    def load_staff_form_from_item(self, item):
        if not item:
            return
        account = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account, dict):
            return
        accounts = self.staff_accounts()
        is_protected = self.is_protected_staff_account(account, accounts)
        self.staff_name_in.setText(account.get("name", ""))
        self.staff_role_in.blockSignals(True)
        self.staff_role_in.setCurrentText("Yönetici" if is_protected else account.get("role", "Servis Personeli"))
        self.staff_role_in.blockSignals(False)
        self.staff_role_in.setEnabled(not is_protected)
        self.staff_role_in.setToolTip("Yönetici profili her zaman tam yetkili kalır." if is_protected else "")
        self.set_staff_permission_checks(self.account_permissions(account))
        self.set_staff_permission_checks_locked(is_protected)
        self.staff_pin_in.clear()
        self.staff_pin_in.setPlaceholderText("PIN değiştirmek için yeni PIN yazın")
        self.update_staff_delete_button_state(account)

    def update_staff_delete_button_state(self, account=None):
        btn = getattr(self, "btn_staff_delete", None)
        if btn is None:
            return
        if account is None and hasattr(self, "staff_list") and self.staff_list.currentItem():
            account = self.staff_list.currentItem().data(Qt.ItemDataRole.UserRole)
        if not isinstance(account, dict):
            btn.setEnabled(False)
            btn.setCursor(Qt.CursorShape.ForbiddenCursor)
            btn.setToolTip("Silmek için personel seçin")
            return
        is_admin = self.is_protected_staff_account(account) if isinstance(account, dict) else False
        btn.setEnabled(not is_admin)
        btn.setCursor(Qt.CursorShape.ForbiddenCursor if is_admin else Qt.CursorShape.PointingHandCursor)
        btn.setToolTip("Yönetici profili silinemez." if is_admin else "Seçili personeli sil")

    def save_staff_account_from_form(self):
        if not self.require_staff_permission("manage_staff", "Personel yönetimi"):
            return
        name = self.normalize_upper(self.staff_name_in.text()).strip()
        role = self.staff_role_in.currentText()
        pin = self.staff_pin_in.text().strip()
        selected = self.staff_list.currentItem().data(Qt.ItemDataRole.UserRole) if self.staff_list.currentItem() else None
        if not name:
            QMessageBox.warning(self, "Personel", "Personel adı zorunludur.")
            return
        if not selected and not pin:
            QMessageBox.warning(self, "Personel", "Yeni personel için PIN zorunludur.")
            return
        if pin and len(pin) < 4:
            QMessageBox.warning(self, "Personel", "PIN en az 4 haneli olmalı.")
            return
        accounts = self.staff_accounts()
        selected_is_protected = self.is_protected_staff_account(selected, accounts) if isinstance(selected, dict) else False
        permissions = sorted(self.selected_staff_permissions())
        if selected_is_protected:
            role = "Yönetici"
            permissions = sorted(self.all_staff_permission_keys())
        elif self.staff_role_key(role) == "YONETICI":
            permissions = sorted(self.all_staff_permission_keys())
        elif not permissions:
            QMessageBox.warning(self, "Personel", "Bu personel için en az bir yetki seçmelisiniz.")
            return
        if pin:
            selected_id = selected.get("id") if isinstance(selected, dict) else None
            for acc in accounts:
                if not isinstance(acc, dict) or acc.get("id") == selected_id:
                    continue
                if self.verify_staff_pin(acc, pin):
                    QMessageBox.warning(self, "Personel", "Bu PIN baska bir personelde kullaniliyor. Her personelin PIN'i farkli olmali.")
                    return
        saved_account = None
        if selected:
            selected_id = selected.get("id")
            accounts = [self.make_staff_account(name, role, pin, acc, permissions) if acc.get("id") == selected_id else acc for acc in accounts]
            saved_account = next((acc for acc in accounts if acc.get("id") == selected_id), None)
        else:
            saved_account = self.make_staff_account(name, role, pin, permissions=permissions)
            accounts.append(saved_account)
        accounts = self.normalized_staff_accounts(accounts)
        if isinstance(saved_account, dict):
            saved_account = next((acc for acc in accounts if acc.get("id") == saved_account.get("id")), saved_account)
        if self.staff_pin_enabled() and not any(self.is_staff_admin_account(acc) for acc in accounts):
            QMessageBox.warning(self, "Personel", "PIN sistemi aktifken en az bir Yonetici rolu bulunmali.")
            return
        self.save_staff_accounts(accounts)
        self.set_user_setting("staff_pin_enabled", "true")
        if hasattr(self, "staff_enabled_cb"):
            self.staff_enabled_cb.blockSignals(True)
            self.staff_enabled_cb.setChecked(True)
            self.staff_enabled_cb.blockSignals(False)
        if isinstance(saved_account, dict) and self.current_staff.get("id") == saved_account.get("id"):
            self.set_current_staff(saved_account)
        self.refresh_staff_list()
        self.clear_staff_form_for_new_account()
        if hasattr(self, "staff_gate") and self.staff_gate.isVisible():
            self.refresh_staff_gate_accounts()
        self.update_staff_switch_button_visibility()
        if isinstance(saved_account, dict):
            self.audit_log(
                "Personel Güncelleme" if selected else "Personel Ekleme",
                f"{saved_account.get('name', '')} ({saved_account.get('role', '')})",
                "personel",
                saved_account.get("id", ""),
                after={"name": saved_account.get("name", ""), "role": saved_account.get("role", ""), "permissions": saved_account.get("permissions", [])}
            )
        QMessageBox.information(self, "Personel", "Personel bilgisi kaydedildi.")

    def change_selected_staff_photo(self):
        if not self.require_staff_permission("manage_staff", "Personel fotoğrafı değiştirme"):
            return
        item = self.staff_list.currentItem() if hasattr(self, "staff_list") else None
        if not item:
            QMessageBox.information(self, "Personel", "Fotoğraf değiştirmek için listeden bir personel seçin.")
            return
        account = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account, dict):
            return
        fn, _ = QFileDialog.getOpenFileName(self, "Personel Fotoğrafı Seç", "", "Resim Dosyaları (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not fn:
            return
        pix = QPixmap(fn)
        if pix.isNull():
            QMessageBox.warning(self, "Personel", "Seçilen dosya geçerli bir resim değil.")
            return
        ext = os.path.splitext(fn)[1].lower()
        if ext not in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
            ext = ".png"
        photo_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MetaFold", "staff_photos", str(self.user_id))
        os.makedirs(photo_dir, exist_ok=True)
        target = os.path.join(photo_dir, f"{account.get('id', uuid.uuid4().hex)}{ext}")
        try:
            shutil.copy2(fn, target)
        except Exception:
            if not pix.save(target):
                QMessageBox.warning(self, "Personel", "Fotoğraf kaydedilemedi.")
                return
        accounts = [acc for acc in self.staff_accounts() if isinstance(acc, dict)]
        updated = None
        for acc in accounts:
            if acc.get("id") == account.get("id"):
                acc["photo_path"] = target
                updated = acc
                break
        if not updated:
            QMessageBox.warning(self, "Personel", "Seçili personel bulunamadı.")
            return
        self.save_staff_accounts(accounts)
        if self.current_staff.get("id") == updated.get("id"):
            self.set_current_staff(updated)
        self.log_staff_event(f"Personel fotoğrafı değiştirildi: {updated.get('name', '')}")
        self.refresh_staff_list()
        if hasattr(self, "staff_gate") and self.staff_gate.isVisible():
            self.refresh_staff_gate_accounts()
        QMessageBox.information(self, "Personel", "Personel fotoğrafı güncellendi.")

    def change_selected_staff_pin(self):
        if not self.require_staff_permission("manage_staff", "Personel PIN değiştirme"):
            return
        item = self.staff_list.currentItem() if hasattr(self, "staff_list") else None
        if not item:
            QMessageBox.information(self, "Personel", "PIN değiştirmek için listeden bir personel seçin.")
            return
        account = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account, dict):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Personel PIN Değiştir")
        dlg.setModal(True)
        lay = QVBoxLayout(dlg)
        info = QLabel(f"{account.get('name', '-')} için yeni PIN belirleyin.")
        info.setWordWrap(True)
        pin_1 = QLineEdit()
        pin_1.setEchoMode(QLineEdit.EchoMode.Password)
        pin_1.setPlaceholderText("Yeni PIN")
        pin_1.setMaxLength(12)
        pin_2 = QLineEdit()
        pin_2.setEchoMode(QLineEdit.EchoMode.Password)
        pin_2.setPlaceholderText("Yeni PIN tekrar")
        pin_2.setMaxLength(12)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(info)
        lay.addWidget(pin_1)
        lay.addWidget(pin_2)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_pin = pin_1.text().strip()
        if len(new_pin) < 4:
            QMessageBox.warning(self, "Personel", "PIN en az 4 haneli olmalı.")
            return
        if new_pin != pin_2.text().strip():
            QMessageBox.warning(self, "Personel", "Girilen PIN'ler eşleşmiyor.")
            return

        accounts = [acc for acc in self.staff_accounts() if isinstance(acc, dict)]
        selected_id = account.get("id")
        for acc in accounts:
            if acc.get("id") == selected_id:
                continue
            if self.verify_staff_pin(acc, new_pin):
                QMessageBox.warning(self, "Personel", "Bu PIN başka bir personelde kullanılıyor. Her personelin PIN'i farklı olmalı.")
                return

        updated = None
        new_accounts = []
        for acc in accounts:
            if acc.get("id") == selected_id:
                updated = self.make_staff_account(
                    acc.get("name", account.get("name", "")),
                    acc.get("role", account.get("role", "Servis Personeli")),
                    new_pin,
                    acc,
                    list(self.account_permissions(acc)),
                )
                new_accounts.append(updated)
            else:
                new_accounts.append(acc)
        if not updated:
            QMessageBox.warning(self, "Personel", "Seçili personel bulunamadı.")
            return
        self.save_staff_accounts(new_accounts)
        if self.current_staff.get("id") == updated.get("id"):
            self.set_current_staff(updated)
        self.log_staff_event(f"Personel PIN değiştirildi: {updated.get('name', '')}")
        self.refresh_staff_list()
        if hasattr(self, "staff_gate") and self.staff_gate.isVisible():
            self.refresh_staff_gate_accounts()
        QMessageBox.information(self, "Personel", f"{updated.get('name', '-')} PIN'i değiştirildi.")

    def delete_selected_staff_account(self):
        if not self.require_staff_permission("manage_staff", "Personel silme"):
            return
        item = self.staff_list.currentItem() if hasattr(self, "staff_list") else None
        if not item:
            return
        account = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(account, dict):
            return
        if self.is_protected_staff_account(account):
            QMessageBox.information(self, "Personel", "Yönetici profili silinemez. Önce başka bir personel seçin.")
            return
        if QMessageBox.question(self, "Personel Sil", f"{account.get('name', '')} silinsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        accounts = [acc for acc in self.staff_accounts() if acc.get("id") != account.get("id")]
        if self.staff_pin_enabled() and not any(self.is_staff_admin_account(acc) for acc in accounts):
            QMessageBox.warning(self, "Personel", "PIN sistemi aktifken son Yonetici personel silinemez.")
            return
        self.save_staff_accounts(accounts)
        self.audit_log("Personel Silme", f"{account.get('name', '')} ({account.get('role', '')}) silindi", "personel", account.get("id", ""), before={"name": account.get("name", ""), "role": account.get("role", "")})
        self.refresh_staff_list()
        if hasattr(self, "staff_gate") and self.staff_gate.isVisible():
            self.refresh_staff_gate_accounts()
        self.update_staff_switch_button_visibility()

    def toggle_staff_pin_enabled(self, checked):
        if not checked and self.staff_accounts():
            QMessageBox.information(self, "Personel PIN", "Kayıtlı personel varken personel giriş ekranı kapatılamaz. Önce personel kayıtlarını silmelisiniz.")
            self.staff_enabled_cb.blockSignals(True)
            self.staff_enabled_cb.setChecked(True)
            self.staff_enabled_cb.blockSignals(False)
            self.set_user_setting("staff_pin_enabled", "true")
            return
        if checked and not self.staff_accounts():
            QMessageBox.information(self, "Personel PIN", "Önce en az bir yönetici/personel kaydı oluşturun, sonra PIN girişini aktif edin.")
            self.staff_enabled_cb.blockSignals(True)
            self.staff_enabled_cb.setChecked(False)
            self.staff_enabled_cb.blockSignals(False)
            self.set_user_setting("staff_pin_enabled", "false")
            return
        if checked and not any(self.is_staff_admin_account(acc) for acc in self.staff_accounts() if isinstance(acc, dict)):
            QMessageBox.warning(self, "Personel PIN", "PIN girişini aktif etmeden önce en az bir Yönetici rolünde personel oluşturun.")
            self.staff_enabled_cb.blockSignals(True)
            self.staff_enabled_cb.setChecked(False)
            self.staff_enabled_cb.blockSignals(False)
            self.set_user_setting("staff_pin_enabled", "false")
            return
        self.set_user_setting("staff_pin_enabled", "true" if checked else "false")
        self.sync_staff_accounts_to_cloud()
        self.build_sidebar_navigation()
        self.apply_staff_permissions()
        self.update_staff_switch_button_visibility()

    def set_sync_status(self, text, color="#38bdf8"):
        if hasattr(self, "lbl_sync_status"):
            self.lbl_sync_status.setText(f"Senkron durumu: {text}")
            self.lbl_sync_status.setStyleSheet(f"font-weight:bold; color:{color}; padding:6px;")

    def update_connection_badge(self, online=True, detail=""):
        self._last_connection_online = bool(online)
        badge = getattr(self, "connection_status_badge", None)
        if badge is None:
            return
        if online:
            badge.set_online(True, detail or "Firebase bağlantısı aktif")
        else:
            badge.set_online(False, detail or "İnternet/Firebase bağlantısı yok. Yerel kopya görüntüleniyor; yazma işlemleri kapalı.")

    def start_connection_check(self):
        worker = getattr(self, "_connection_check_worker", None)
        if worker is not None and worker.isRunning():
            return
        worker = ConnectionCheckWorker(self.firebase_connection_host(), timeout=0.8)
        self._connection_check_worker = worker
        worker.result.connect(self.on_connection_checked)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "_connection_check_worker", None))
        worker.start()

    def on_connection_checked(self, online):
        if online:
            if getattr(self, "_read_only_cache_mode", False):
                self._read_only_cache_mode = False
                self.set_sync_status("Bağlantı geri geldi", "#22c55e")
            self.update_connection_badge(True, "Firebase bağlantısı aktif")
        else:
            self._read_only_cache_mode = True
            self.update_connection_badge(False)

    def dialog_html_palette(self):
        theme = str(self.user_setting_value("theme", "Dark") or "Dark")
        is_light = "Light" in theme or "Açık" in theme or "Emerald" in theme or "Zümrüt" in theme
        if is_light:
            return {
                "bg": "#ffffff",
                "panel": "#f8fafc",
                "panel2": "#eef6f2" if ("Emerald" in theme or "Zümrüt" in theme) else "#eef4ff",
                "text": "#0f172a",
                "muted": "#475569",
                "border": "#cbd5e1",
                "accent": "#059669" if ("Emerald" in theme or "Zümrüt" in theme) else "#2563eb",
                "header": "#e2e8f0",
            }
        return {
            "bg": "#1f2329",
            "panel": "#262c35",
            "panel2": "#202733",
            "text": "#f8fafc",
            "muted": "#cbd5e1",
            "border": "#475569",
            "accent": "#60a5fa",
            "header": "#2f3a4a",
        }

    def blocked_license_logout(self):
        QMessageBox.warning(self, "Lisans Kontrolü", self.license_block_reason or "Lisans doğrulanamadı.")
        try:
            if getattr(self, 'stream_worker', None): 
                self.stream_worker.stop()
                self.stream_worker.quit()
                self.stream_worker.wait()
        except:
            pass
        self.settings.setValue("auto_login", "false")
        if hasattr(self.manager, "login_screen"):
            self.manager.login_screen.auto_login_cb.setChecked(False)
            self.manager.login_screen.lbl_status.setText("")
            self.manager.login_screen.update_avatar(use_custom=False)
            self.manager.login_screen.refresh_theme("Dark")
        self.manager.setFixedSize(700, 520)
        if hasattr(self.manager, "center_on_active_screen"):
            self.manager.center_on_active_screen(force=True, reset_user_position=True)
        self.manager.setCurrentIndex(0)
        self.manager.removeWidget(self)
        self.deleteLater()

    def guncelleme_kontrolu(self):
        try:
            sistem = {}
            try:
                sistem = db.child("public_update").child("metafold_servis").get(self.token).val()
                self.record_download_usage("public_update", payload=sistem, detail="Guncelleme kontrolu")
            except:
                sistem = {}
            if not isinstance(sistem, dict):
                sistem = {}
            yeni_surum = sistem.get("guncel_surum") or sistem.get("version")
            if yeni_surum and safe_float(yeni_surum, MEVCUT_SURUM) > MEVCUT_SURUM:
                self.launch_update_installer(sistem, required=True)
        except:
            pass

    def launch_update_installer(self, update_info=None, required=False):
        candidates = []
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
            candidates.append(resource_path("MetaFold Installer.exe"))
            candidates.append(os.path.join(app_dir, "MetaFold Installer Runtime.exe"))
            candidates.append(os.path.join(app_dir, "MetaFold Installer.exe"))
        candidates.extend([
            os.path.join(os.getcwd(), "MetaFold Installer Runtime.exe"),
            os.path.join(os.getcwd(), "MetaFold Installer.exe"),
            os.path.join(os.getcwd(), "dist", "MetaFold Installer Runtime.exe"),
            os.path.join(os.getcwd(), "dist", "MetaFold Installer.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dist", "MetaFold Installer Runtime.exe"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dist", "MetaFold Installer.exe"),
        ])
        for path in candidates:
            path = os.path.abspath(path)
            if os.path.exists(path):
                try:
                    launch_path = path
                    if required:
                        temp_dir = os.path.join(tempfile.gettempdir(), "MetaFoldInstallerRuntime")
                        os.makedirs(temp_dir, exist_ok=True)
                        launch_path = os.path.join(temp_dir, f"MetaFold Installer {int(time.time())}.exe")
                        shutil.copy2(path, launch_path)
                    args = [launch_path]
                    if required:
                        args.append("--update")
                        args.append("--temp-run")
                    subprocess.Popen(args, shell=False, creationflags=subprocess_no_console_flags())
                    QApplication.instance().quit()
                    return
                except Exception as exc:
                    QMessageBox.warning(self, "Güncelleme", f"Installer başlatılamadı:\n{exc}")
                    break

        link = ""
        if isinstance(update_info, dict):
            link = update_info.get("indirme_linki") or update_info.get("download_url") or update_info.get("setup_url") or ""
        if link:
            webbrowser.open(link)
            if required:
                QApplication.instance().quit()
        else:
            QMessageBox.information(self, "Güncelleme", "Installer bulunamadı ve indirme linki alınamadı.")
            if required:
                QApplication.instance().quit()

    def setup_custom_titlebar(self):
        self.title_bar = QWidget()
        self.title_bar.setFixedHeight(48)
        self.title_bar.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
            QPushButton#WindowButton {
                background-color: rgba(255,255,255,0.08);
                color: #5f6f86;
                border: 1px solid rgba(120,135,155,0.22);
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton#WindowButton:hover {
                background-color: rgba(120,135,155,0.16);
                color: #172033;
            }
            QPushButton#StaffSwitchButton {
                background-color: rgba(37,99,235,0.16);
                color: #2563eb;
                border: 1px solid rgba(37,99,235,0.35);
                border-radius: 6px;
                font-size: 14px;
                font-weight: 800;
                padding: 0px;
            }
            QPushButton#StaffSwitchButton:hover {
                background-color: rgba(37,99,235,0.26);
                border-color: #2563eb;
            }
            QLabel#ConnectionBadge {
                background-color: rgba(34,197,94,0.12);
                color: #22c55e;
                border: 1px solid rgba(34,197,94,0.35);
                border-radius: 10px;
                font-size: 15px;
                font-weight: 900;
            }
            QPushButton#CloseWindowButton {
                background-color: rgba(255,255,255,0.08);
                color: #5f6f86;
                border: 1px solid rgba(120,135,155,0.22);
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
                padding: 0px;
            }
            QPushButton#CloseWindowButton:hover {
                background-color: #e81123;
                color: white;
                border-color: #e81123;
            }
        """)
        grid = QGridLayout(self.title_bar)
        grid.setContentsMargins(15, 0, 15, 0)
        
        left_w = QWidget()
        ll = QHBoxLayout(left_w)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)

        self.fixed_brand_icon_label = QLabel()
        icon_pix = QPixmap(resource_path("metafold.ico"))
        if not icon_pix.isNull():
            self.fixed_brand_icon_label.setPixmap(icon_pix.scaled(26, 26, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.fixed_brand_icon_label.setFixedSize(30, 30)
        self.fixed_brand_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.logo_label = QLabel()
        pix = QPixmap(resource_path("banner.png"))
        if pix.isNull():
            pix = QPixmap(resource_path("metafold_banner.png"))
        if not pix.isNull(): 
            self.logo_label.setPixmap(pix.scaled(118, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.logo_label.setFixedHeight(30)

        self.rate_lbl = QLabel("")
        self.rate_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rate_lbl.setToolTip("Döviz çeviriciyi aç")
        self.rate_lbl.setStyleSheet("color: #15803d; margin-left: 10px; font-size: 13px; font-weight: 700; padding:4px 6px; border-radius:6px;")
        self.rate_lbl.mousePressEvent = lambda event: self.show_currency_converter_dialog()
        ll.addWidget(self.fixed_brand_icon_label)
        ll.addWidget(self.logo_label)
        ll.addWidget(self.rate_lbl)
        ll.addStretch()
        
        self.title_company_label = QLabel()
        self.title_company_label.setStyleSheet("font-size: 16px; font-weight: 700; color: #2563eb;")
        self.title_company_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_title_company_name()
        
        right_w = QWidget()
        rl = QHBoxLayout(right_w)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        
        self.connection_status_badge = ConnectionBadge()
        self.connection_status_badge.setObjectName("ConnectionBadge")
        self.connection_status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.connection_status_badge.setToolTip("Bağlantı kontrol ediliyor")

        btn_m = QPushButton("—")
        btn_max = QPushButton("□")
        btn_c = QPushButton("×")
        
        self.title_staff_switch_btn = QPushButton("👤")
        self.title_staff_switch_btn.setFixedSize(40, 28)
        self.title_staff_switch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_staff_switch_btn.setObjectName("StaffSwitchButton")
        self.title_staff_switch_btn.setToolTip("Kullanıcı / personel değiştir")
        self.title_staff_switch_btn.setAccessibleName("Kullanıcı değiştir")
        self.title_staff_switch_btn.clicked.connect(lambda: self.show_staff_gate(force=True))

        for b in [btn_m, btn_max, btn_c]: 
            b.setFixedSize(32, 28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setObjectName("WindowButton")
        btn_c.setObjectName("CloseWindowButton")
        
        btn_m.clicked.connect(self.manager.showMinimized)
        btn_max.clicked.connect(self.toggle_maximize)
        btn_c.clicked.connect(self.manager.handle_close)
        
        rl.addStretch()
        rl.addWidget(self.connection_status_badge)
        rl.addWidget(self.title_staff_switch_btn)
        rl.addWidget(btn_m)
        rl.addWidget(btn_max)
        rl.addWidget(btn_c)
        self.update_staff_switch_button_visibility()
        
        grid.addWidget(left_w, 0, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(self.title_company_label, 0, 1, Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(right_w, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 2)
        grid.setColumnStretch(2, 1)
        
        self.ticker_index = 0
        self.ticker_timer = QTimer(self)
        self.ticker_timer.timeout.connect(self.update_ticker)
        self.ticker_timer.start(3000)
        self.update_ticker()
        self.layout.addWidget(self.title_bar)

    def update_staff_switch_button_visibility(self):
        self.staff_gate_required = self.should_show_staff_gate()
        visible = self.staff_gate_required
        btn = getattr(self, "title_staff_switch_btn", None)
        if btn is not None:
            btn.setVisible(visible)
        sidebar_label = getattr(self, "sidebar_staff_label", None)
        if sidebar_label is not None:
            sidebar_label.setVisible(visible)

    def display_company_name(self):
        return (self.receipt_shop_name or self.firma_adi or "MetaFold Teknik Servis").strip()

    def receipt_display_company_name(self):
        live_name = ""
        if hasattr(self, "shop_name_in"):
            live_name = self.shop_name_in.text().strip()
        saved_name = str(self.user_setting_value("receipt_shop_name", "") or "").strip()
        return (live_name or self.receipt_shop_name or saved_name or self.firma_adi or "MetaFold Teknik Servis").strip()

    def update_title_company_name(self):
        if hasattr(self, "title_company_label"):
            self.title_company_label.setText("MetaFold Teknik Servis ERP")
        if hasattr(self, "sidebar_brand_label"):
            self.sidebar_brand_label.setText(self.display_company_name())
        self.update_sidebar_logo_label()

    def update_sidebar_logo_label(self):
        if not hasattr(self, "sidebar_logo_label"):
            return
        logo_path = str(getattr(self, "session_custom_logo", "") or "")
        pix = QPixmap(logo_path) if logo_path and os.path.exists(logo_path) else QPixmap(resource_path("metafold.ico"))
        if pix.isNull():
            self.sidebar_logo_label.clear()
            self.sidebar_logo_label.setVisible(False)
            return
        self.sidebar_logo_label.setVisible(True)
        self.sidebar_logo_label.setPixmap(pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def setup_global_search_bar(self):
        bar = QWidget()
        self.global_search_bar = bar
        bar.setObjectName("GlobalSearchBar")
        bar.setStyleSheet("""
            QWidget#GlobalSearchBar {
                background: transparent;
            }
            QLineEdit#GlobalSearchInput {
                min-height: 34px;
                border-radius: 8px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton#GlobalSearchButton {
                min-height: 34px;
                padding: 6px 14px;
                border-radius: 8px;
                font-weight: 700;
            }
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 6)
        lay.setSpacing(8)
        self.global_search_label = QLabel(self.get_trans("Search:", "Genel Arama:"))
        self.global_search_label.setStyleSheet("font-weight:700;")
        self.global_search_input = QLineEdit()
        self.global_search_input.setObjectName("GlobalSearchInput")
        self.global_search_input.setPlaceholderText(self.get_trans(
            "Search reg no, customer, phone, device, fault, note, partner, stock or supplier...",
            "Kayıt no, müşteri, telefon, cihaz, arıza, not, bayi, stok veya toptancı ara..."
        ))
        self.global_search_input.returnPressed.connect(self.open_global_search)
        self.global_search_button = QPushButton(self.get_trans("Search", "Ara"))
        self.global_search_button.setObjectName("GlobalSearchButton")
        self.global_search_button.clicked.connect(self.open_global_search)
        lay.addWidget(self.global_search_label)
        lay.addWidget(self.global_search_input, 1)
        lay.addWidget(self.global_search_button)
        self.layout.addWidget(bar)

    def update_ticker(self):
        rates = [f"💵 Dolar: {format_money(self.usd_rate, '₺')}", f"💶 Euro: {format_money(self.eur_rate, '₺')}"]
        self.rate_lbl.setText(rates[self.ticker_index])
        self.ticker_index = (self.ticker_index + 1) % len(rates)

    def show_currency_converter_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Döviz Çevirici")
        dlg.resize(420, 260)
        lay = QVBoxLayout(dlg)
        title = QLabel("<b>Döviz Çevirici</b>")
        title.setStyleSheet("font-size:18px; color:#60a5fa;")
        rates = QLabel(f"Dolar: {format_money(self.usd_rate, '₺')}   |   Euro: {format_money(self.eur_rate, '₺')}")
        rates.setStyleSheet("color:#22c55e; font-weight:bold;")
        grid = QGridLayout()
        amount_in = QLineEdit()
        amount_in.setPlaceholderText("Tutar")
        from_cb = QComboBox()
        from_cb.addItems(["₺ TL", "$ USD", "€ EUR"])
        from_cb.setCurrentIndex(1)
        to_cb = QComboBox()
        to_cb.addItems(["₺ TL", "$ USD", "€ EUR"])
        to_cb.setCurrentIndex(0)
        result = QLabel("Sonuç: 0")
        result.setStyleSheet("font-size:18px; font-weight:bold; color:#f8fafc; padding:10px; background:#111827; border-radius:8px;")
        btn_close = QPushButton("Kapat")
        btn_close.clicked.connect(dlg.accept)

        def currency_rate(label):
            if "USD" in label:
                return safe_float(self.usd_rate, 1)
            if "EUR" in label:
                return safe_float(self.eur_rate, 1)
            return 1.0

        def currency_symbol(label):
            if "USD" in label:
                return "$"
            if "EUR" in label:
                return "€"
            return "₺"

        currencies = ["₺ TL", "$ USD", "€ EUR"]

        def first_other_currency(selected, preferred=None):
            choices = []
            if preferred:
                choices.append(preferred)
            choices.extend(currencies)
            for choice in choices:
                if choice != selected:
                    return choice
            return currencies[0]

        def set_combo_value(combo, value):
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        def keep_currency_pair_distinct(changed_side):
            if from_cb.currentText() != to_cb.currentText():
                refresh()
                return
            selected = from_cb.currentText() if changed_side == "from" else to_cb.currentText()
            if changed_side == "from":
                preferred = "$ USD" if "TL" in selected else "₺ TL"
                to_cb.blockSignals(True)
                set_combo_value(to_cb, first_other_currency(selected, preferred))
                to_cb.blockSignals(False)
            else:
                preferred = "$ USD" if "TL" in selected else "₺ TL"
                from_cb.blockSignals(True)
                set_combo_value(from_cb, first_other_currency(selected, preferred))
                from_cb.blockSignals(False)
            refresh()

        def refresh():
            amount = safe_float(amount_in.text())
            from_rate = currency_rate(from_cb.currentText())
            to_rate = currency_rate(to_cb.currentText())
            value_tl = amount * from_rate
            converted = value_tl / to_rate if to_rate else 0
            result.setText(f"Sonuç: {format_money(converted, currency_symbol(to_cb.currentText()))}")

        amount_in.textChanged.connect(refresh)
        from_cb.currentIndexChanged.connect(lambda: keep_currency_pair_distinct("from"))
        to_cb.currentIndexChanged.connect(lambda: keep_currency_pair_distinct("to"))
        grid.addWidget(QLabel("Tutar:"), 0, 0)
        grid.addWidget(amount_in, 0, 1, 1, 2)
        grid.addWidget(QLabel("Çevir:"), 1, 0)
        grid.addWidget(from_cb, 1, 1)
        grid.addWidget(to_cb, 1, 2)
        lay.addWidget(title)
        lay.addWidget(rates)
        lay.addLayout(grid)
        lay.addWidget(result)
        lay.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)
        amount_in.setFocus()
        refresh()
        dlg.exec()
    
    def toggle_maximize(self):
        self.manager.setMaximumSize(16777215, 16777215)
        self.manager.setMinimumSize(1000, 650)
        if self.manager.isMaximized():
            self.manager.showNormal()
            self.manager.resize(1280, 800)
        else:
            self.manager.showMaximized()
        QTimer.singleShot(0, self.reapply_service_table_columns)
        QTimer.singleShot(250, self.reapply_service_table_columns)

    def create_table(self, col_count):
        t = QTableWidget(0, col_count)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setFixedWidth(0)
        t.setAlternatingRowColors(True)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(lambda p, tbl=t: self.open_menu(p, tbl))
        t.cellDoubleClicked.connect(lambda r, c, tbl=t: self.handle_double_click(r, c, tbl))
        t.installEventFilter(self)
        t.viewport().installEventFilter(self)
        self.collapse_id_column(t)
        return t

    def create_premium_virus_placeholder(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(18)
        layout.addStretch(1)

        card = QFrame()
        card.setObjectName("PremiumVirusCard")
        card.setStyleSheet("""
            QFrame#PremiumVirusCard {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #111827, stop:1 #0b0f18);
                border: 1px solid #f59e0b;
                border-radius: 18px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 28, 32, 28)
        card_layout.setSpacing(14)

        icon = QLabel("🛡")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 54px;")
        title = QLabel("Virüs Temizleyici Premium Özelliktir")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: 900; color: #f59e0b;")
        desc = QLabel(
            "30 günlük deneme sürümünde Android virüs temizleme modülü çalışmaz.\n"
            "Bu özellik tam lisans/premium kullanımda aktif olur."
        )
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 15px; color: #d1d5db;")

        card_layout.addWidget(icon)
        card_layout.addWidget(title)
        card_layout.addWidget(desc)
        layout.addWidget(card)
        layout.addStretch(1)
        return page

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.reapply_service_table_columns)

    def showEvent(self, event):
        super().showEvent(event)
        for delay in (0, 120, 450, 900):
            QTimer.singleShot(delay, self.reapply_service_table_columns)

    def handle_staff_gate_key_event(self, event):
        gate = getattr(self, "staff_gate", None)
        if gate is None or not gate.isVisible():
            return False
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.move_staff_gate_selection(-1)
            return True
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.move_staff_gate_selection(1)
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if getattr(self, "staff_gate_pin", None) is not None and self.staff_gate_pin.text().strip():
                self.submit_staff_gate_login()
            elif getattr(self, "staff_gate_pin", None) is not None:
                self.staff_gate_pin.setFocus()
            return True
        return False

    def keyPressEvent(self, event):
        if self.handle_staff_gate_key_event(event):
            return
        modifiers = event.modifiers()
        if (
            event.key() == Qt.Key.Key_F12
            and modifiers & Qt.KeyboardModifier.ControlModifier
            and modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            self.open_support_restore_gate()
            return
        if (
            event.key() == Qt.Key.Key_F11
            and modifiers & Qt.KeyboardModifier.ControlModifier
            and modifiers & Qt.KeyboardModifier.ShiftModifier
        ):
            self.open_staff_pin_recovery_gate()
            return
        super().keyPressEvent(event)

    def setup_new_record_keyboard_flow(self):
        widgets = [
            self.f_ad,
            self.combo_bayi,
            self.f_tel,
            self.f_cihaz,
            self.f_ariza,
            self.f_not,
            self.f_yaklasik,
            self.cb_garanti_ver,
            self.f_garanti_gun,
            self.sifre_tipi,
            self.f_sifre,
            self.btn_desen,
            self.cb_sim,
            self.cb_sd,
            self.cb_kilif,
            self.b_save,
        ]
        for widget in widgets:
            widget.setProperty("newRecordKeyboardFlow", True)
            widget.installEventFilter(self)
        self.f_not.setTabChangesFocus(True)
        for first, second in zip(widgets, widgets[1:]):
            QWidget.setTabOrder(first, second)

    def new_record_focus_widgets(self):
        widgets = [
            getattr(self, "f_ad", None),
            getattr(self, "combo_bayi", None),
            getattr(self, "f_tel", None),
            getattr(self, "f_cihaz", None),
            getattr(self, "f_ariza", None),
            getattr(self, "f_not", None),
            getattr(self, "f_yaklasik", None),
            getattr(self, "cb_garanti_ver", None),
            getattr(self, "f_garanti_gun", None),
            getattr(self, "sifre_tipi", None),
            getattr(self, "f_sifre", None),
            getattr(self, "btn_desen", None),
            getattr(self, "cb_sim", None),
            getattr(self, "cb_sd", None),
            getattr(self, "cb_kilif", None),
            getattr(self, "b_save", None),
        ]
        return [
            widget for widget in widgets
            if widget is not None and widget.isVisible() and widget.isEnabled()
        ]

    def handle_new_record_keyboard_flow(self, obj, event):
        if not getattr(obj, "property", lambda *_: None)("newRecordKeyboardFlow"):
            return False
        if event.type() != QEvent.Type.KeyPress:
            return False
        key = event.key()
        if key not in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return False
        if event.modifiers() & (
            Qt.KeyboardModifier.AltModifier
            | Qt.KeyboardModifier.MetaModifier
            | Qt.KeyboardModifier.ShiftModifier
        ):
            return False
        if isinstance(obj, QTextEdit) and not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            return False
        if isinstance(obj, QLineEdit):
            completer = obj.completer()
            if completer is not None and completer.popup() is not None and completer.popup().isVisible():
                return False
        if isinstance(obj, QComboBox) and obj.view() is not None and obj.view().isVisible():
            return False
        focus_widgets = self.new_record_focus_widgets()
        if obj not in focus_widgets:
            return False
        current_index = focus_widgets.index(obj)
        if current_index >= len(focus_widgets) - 1:
            return False
        focus_widgets[current_index + 1].setFocus(Qt.FocusReason.TabFocusReason)
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Wheel and isinstance(obj, QComboBox):
            view = obj.view()
            if view is not None and view.isVisible():
                return False
            event.ignore()
            return True
        if event.type() == QEvent.Type.KeyPress and self.handle_staff_gate_key_event(event):
            return True
        if event.type() == QEvent.Type.KeyPress:
            modifiers = event.modifiers()
            if (
                event.key() == Qt.Key.Key_F11
                and modifiers & Qt.KeyboardModifier.ControlModifier
                and modifiers & Qt.KeyboardModifier.ShiftModifier
            ):
                self.open_staff_pin_recovery_gate()
                return True
            if (
                event.key() == Qt.Key.Key_F12
                and modifiers & Qt.KeyboardModifier.ControlModifier
                and modifiers & Qt.KeyboardModifier.ShiftModifier
            ):
                self.open_support_restore_gate()
                return True
            if self.handle_new_record_keyboard_flow(obj, event):
                return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            meta = getattr(self, "_suggestion_popup_meta", {}).get(id(obj))
            if meta and event.button() == Qt.MouseButton.LeftButton:
                popup = meta.get("completer").popup() if meta.get("completer") else None
                if popup is not None:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    index = popup.indexAt(pos)
                    if index.isValid() and pos.x() >= popup.viewport().width() - 34:
                        value = str(index.data(Qt.ItemDataRole.DisplayRole) or "").strip()
                        if self.hide_suggestion_value(meta.get("kind", ""), value, meta.get("label", "")):
                            QTimer.singleShot(
                                0,
                                lambda c=meta.get("completer"), f=meta.get("field"): self.reopen_suggestion_popup(c, f)
                            )
                        return True
        if isinstance(obj, QPushButton) and obj.property("staffAvatarCard"):
            if event.type() == QEvent.Type.Enter:
                self.animate_staff_avatar_button(obj, True)
            elif event.type() == QEvent.Type.Leave:
                self.animate_staff_avatar_button(obj, False)
            elif event.type() == QEvent.Type.Resize:
                self.apply_staff_avatar_mask(obj)
        if event.type() == QEvent.Type.Resize:
            table = obj if isinstance(obj, QTableWidget) else obj.parent()
            if isinstance(table, QTableWidget):
                mode = table.property("serviceTableMode")
                if mode:
                    QTimer.singleShot(0, lambda tbl=table, m=str(mode): self.tune_service_table_columns(tbl, m))
        return super().eventFilter(obj, event)

    def install_no_wheel_combobox_filters(self):
        for combo in self.findChildren(QComboBox):
            if combo.property("noWheelFilterInstalled"):
                continue
            combo.setProperty("noWheelFilterInstalled", True)
            combo.installEventFilter(self)

    def reapply_service_table_columns(self):
        table_modes = [
            (getattr(self, "table_act", None), "active"),
            (getattr(self, "table_ready", None), "ready"),
            (getattr(self, "table_done", None), "done"),
            (getattr(self, "table_delivered", None), "done"),
        ]
        for table, mode in table_modes:
            if table is not None:
                self.tune_service_table_columns(table, mode)

    def collapse_id_column(self, table):
        if table is None or table.columnCount() <= 0:
            return
        header = table.horizontalHeader()
        item = table.horizontalHeaderItem(0)
        if item:
            item.setText("")
        table.setColumnHidden(0, False)
        header.showSection(0)
        header.setMinimumSectionSize(1)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 1)
        header.resizeSection(0, 1)

    def _fit_table_widths(self, table, specs):
        header = table.horizontalHeader()
        self.collapse_id_column(table)
        width_candidates = [
            table.viewport().width(),
            table.width() - table.verticalHeader().width() - 8,
        ]
        if table.parentWidget():
            width_candidates.append(table.parentWidget().width() - 12)
        viewport_width = max(640, max(width_candidates) - 3)
        widths = {col: base for col, minimum, base, maximum, weight in specs}
        total = sum(widths.values())

        if total > viewport_width:
            min_total = sum(minimum for col, minimum, base, maximum, weight in specs)
            if min_total > viewport_width:
                scale = viewport_width / max(1, min_total)
                for col, minimum, base, maximum, weight in specs:
                    widths[col] = max(48, int(minimum * scale))
            shrinkable = sum(max(0, base - minimum) for col, minimum, base, maximum, weight in specs)
            overflow = total - viewport_width
            for col, minimum, base, maximum, weight in specs:
                if min_total <= viewport_width and shrinkable > 0:
                    shrink = overflow * max(0, base - minimum) / shrinkable
                    widths[col] = max(minimum, int(base - shrink))
                elif min_total <= viewport_width:
                    widths[col] = minimum
        elif total < viewport_width:
            extra = viewport_width - total
            weighted = sum(weight for col, minimum, base, maximum, weight in specs if weight > 0)
            for col, minimum, base, maximum, weight in specs:
                if weight > 0 and weighted > 0:
                    widths[col] = int(base + extra * weight / weighted)

        used = sum(widths.values())
        delta = viewport_width - used
        if delta > 0:
            grow_target = max(specs, key=lambda item: item[4])[0]
            widths[grow_target] = max(1, widths.get(grow_target, 1) + delta)
        elif delta < 0:
            overflow = abs(delta)
            shrinkable_cols = [
                (col, max(0, widths.get(col, 0) - max(48, minimum)))
                for col, minimum, base, maximum, weight in specs
            ]
            shrinkable = sum(amount for col, amount in shrinkable_cols)
            if shrinkable:
                for col, amount in shrinkable_cols:
                    widths[col] = max(48, int(widths[col] - overflow * amount / shrinkable))

        for col, width in widths.items():
            if col < table.columnCount():
                table.setColumnWidth(col, max(0, int(width)))
                header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

    def tune_service_table_columns(self, table, mode="active"):
        table.setProperty("serviceTableMode", mode)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        header.setStretchLastSection(False)
        table.setWordWrap(False)
        table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.collapse_id_column(table)
        if mode == "active":
            self._fit_table_widths(table, [
                (1, 90, 110, 135, 1),    # Kayıt No
                (2, 105, 150, 260, 2),   # Müşteri
                (3, 140, 215, 310, 3.2), # Cihaz
                (4, 150, 255, 390, 5),   # Arıza
                (5, 70, 85, 105, 1),     # Fiyat
                (6, 105, 128, 155, 1.2), # Zaman
                (7, 95, 123, 160, 1.2),  # Durum
            ])
        elif mode == "ready":
            self._fit_table_widths(table, [
                (1, 90, 110, 135, 1),    # Kayıt No
                (2, 105, 150, 260, 2),   # Müşteri
                (3, 140, 215, 310, 3.2), # Cihaz
                (4, 140, 240, 370, 5),   # İşlem
                (5, 70, 85, 105, 1),     # Ücret
                (6, 105, 128, 155, 1.2), # Zaman
                (7, 95, 123, 160, 1.2),  # Durum
            ])
        elif mode == "done":
            self._fit_table_widths(table, [
                (1, 90, 105, 130, 1),    # Kayıt No
                (2, 105, 152, 255, 2),   # Müşteri
                (3, 105, 158, 240, 2.2), # Cihaz
                (4, 85, 145, 240, 3),    # İşlem
                (5, 65, 80, 100, 1),     # Ücret
                (6, 105, 128, 160, 1.1), # Tarih
                (7, 85, 113, 155, 1.1),  # Sonuç
                (8, 100, 134, 190, 1.1), # Teslim Durumu
                (9, 100, 129, 185, 1.1), # Ödeme
            ])

    def create_wholesaler_table(self, headers, firm_name):
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(40)
        t.verticalHeader().setMinimumSectionSize(40)
        t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        t.setWordWrap(False)
        t.setAlternatingRowColors(True)
        t.setStyleSheet(t.styleSheet() + """
            QTableWidget::item {
                padding: 2px 8px;
                min-height: 30px;
            }
            QTableWidget::item:selected {
                padding: 2px 8px;
            }
            QTableWidget {
                font-size: 12px;
            }
        """)
        t.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        t.customContextMenuRequested.connect(lambda p, tbl=t, f=firm_name: self.wholesaler_menu(p, tbl, f))
        t.cellDoubleClicked.connect(lambda r, c, tbl=t: self.wholesaler_double_click(r, c, tbl))
        t.setColumnHidden(0, True)
        return t

    def add_row_to_table(self, table, row_data, colors=None, at_top=False):
        r = 0 if at_top else table.rowCount()
        table.insertRow(r)
        for i, text in enumerate(row_data):
            item = QTableWidgetItem(str(text))
            if row_data:
                item.setData(Qt.ItemDataRole.UserRole, str(row_data[0]))
            if colors and i < len(colors) and colors[i]: 
                item.setForeground(colors[i])
            table.setItem(r, i, item)
        return r

    def normalize_search_text(self, value):
        text = str(value or "")
        text = text.replace("İ", "i").replace("I", "i").replace("ı", "i")
        text = unicodedata.normalize("NFKD", text.casefold())
        return "".join(ch for ch in text if not unicodedata.combining(ch))

    def record_search_blob(self, record):
        parts = [
            record.get("c_no", ""),
            record.get("m", ""),
            record.get("t", ""),
            record.get("ci", ""),
            record.get("a", ""),
            record.get("not", ""),
            record.get("d", ""),
            record.get("teslim_durumu", ""),
            record.get("yapilan_islem", ""),
            record.get("odeme_durumu", ""),
            record.get("odeme_tipi", ""),
            record.get("z", ""),
            "BAYI" if record.get("is_bayi") else "MUSTERI",
        ]
        parts.extend(self.get_faults(record))
        note_history = safe_dict_parse(record.get("not_gecmisi", {}) or {})
        if isinstance(note_history, dict):
            for item in note_history.values():
                if isinstance(item, dict):
                    parts.extend([
                        item.get("metin", ""),
                        item.get("detay", ""),
                        item.get("tip", ""),
                        item.get("personel", ""),
                    ])
                else:
                    parts.append(item)
        record_logs = safe_dict_parse(record.get("logs", {}) or {})
        if isinstance(record_logs, dict):
            for item in record_logs.values():
                if isinstance(item, dict):
                    parts.extend([
                        item.get("detay", ""),
                        item.get("islem", ""),
                        item.get("tarih", ""),
                    ])
                else:
                    parts.append(item)
        return self.normalize_search_text(" ".join(map(str, parts)))

    def collect_global_search_results(self, query):
        q = self.normalize_search_text(query)
        results = []
        if not q:
            return results

        records = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if isinstance(records, dict):
            for kid, rec in records.items():
                if not isinstance(rec, dict):
                    continue
                if q in self.record_search_blob(rec):
                    results.append({
                        "kind": "Cihaz",
                        "id": kid,
                        "code": rec.get("c_no", ""),
                        "name": rec.get("m", ""),
                        "item": rec.get("ci", ""),
                        "status": rec.get("d", ""),
                        "date": rec.get("z", ""),
                    })

        stok = safe_dict_parse(getattr(self, "stok_data", {}))
        if isinstance(stok, dict):
            for sid, item in stok.items():
                if not isinstance(item, dict):
                    continue
                stock_code = self.stock_code_for_item(sid, item)
                blob = self.normalize_search_text(f"{stock_code} {item.get('barkod', '')} {item.get('barcode', '')} {item.get('ad', '')} {item.get('adet', '')} {item.get('alis', '')} {item.get('satis', '')}")
                if q in blob:
                    results.append({
                        "kind": "Stok",
                        "id": sid,
                        "code": stock_code,
                        "name": "Stok",
                        "item": item.get("ad", ""),
                        "status": f"Adet: {self.format_quantity(item.get('adet'))}",
                        "date": "",
                    })

        toptanci = safe_dict_parse(getattr(self, "toptanci_data", {}))
        if isinstance(toptanci, dict):
            for pid, item in toptanci.items():
                if not isinstance(item, dict):
                    continue
                blob = self.normalize_search_text(f"{item.get('firma', '')} {item.get('parca', '')} {item.get('durum', '')} {item.get('odeme_durumu', '')} {item.get('zaman', '')}")
                if q in blob:
                    results.append({
                        "kind": "Toptancı",
                        "id": pid,
                        "code": pid,
                        "name": item.get("firma", ""),
                        "item": item.get("parca", ""),
                        "status": item.get("durum", ""),
                        "date": item.get("zaman", ""),
                    })
        return results[:120]

    def open_global_search(self):
        query = self.global_search_input.text().strip() if hasattr(self, "global_search_input") else ""
        if len(query) < 2:
            QMessageBox.information(self, "Genel Arama", "Aramak için en az 2 karakter yazın.")
            return
        results = self.collect_global_search_results(query)
        if not results:
            QMessageBox.information(self, "Genel Arama", "Eşleşen sonuç bulunamadı.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Genel Arama - {query}")
        dlg.resize(900, 520)
        lay = QVBoxLayout(dlg)
        info = QLabel(f"<b>{len(results)}</b> sonuç bulundu. Detay açmak veya ilgili satıra gitmek için çift tıklayın.")
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Tür", "Kayıt/ID", "Müşteri/Firma", "Cihaz/Parça", "Durum", "Tarih"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        for res in results:
            row = table.rowCount()
            table.insertRow(row)
            values = [res["kind"], res["code"], res["name"], res["item"], res["status"], res["date"]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, res)
                table.setItem(row, col, item)
        table.cellDoubleClicked.connect(lambda r, c: self.open_global_search_result(table.item(r, 0).data(Qt.ItemDataRole.UserRole), dlg))
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(info)
        lay.addWidget(table, 1)
        lay.addWidget(close_btn)
        dlg.exec()

    def select_table_row_by_id(self, table, item_id):
        if not table or not hasattr(table, "rowCount"):
            return False
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item and item.text() == item_id:
                table.setRowHidden(row, False)
                table.selectRow(row)
                table.scrollToItem(item)
                return True
        return False

    def open_global_search_result(self, result, dlg=None):
        if not isinstance(result, dict):
            return
        kind = result.get("kind")
        item_id = result.get("id")
        if dlg:
            dlg.accept()
        if kind == "Cihaz":
            record = self.get_local_record(item_id)
            if isinstance(record, dict) and record:
                InfoDialog(record, item_id, self, self).exec()
        elif kind == "Stok":
            self.tabs.setCurrentIndex(8)
            self.select_table_row_by_id(getattr(self, "table_stok", None), item_id)
        elif kind == "Toptancı":
            self.tabs.setCurrentIndex(9)
            self.load_wholesalers()
            if not hasattr(self, "w_tabs"):
                return
            for idx, table in enumerate(getattr(self, "w_tables", [])):
                if self.select_table_row_by_id(table, item_id):
                    self.w_tabs.setCurrentIndex(idx)
                    break

    def collect_notification_items(self):
        items = []
        records = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(records, dict):
            records = {}
        today = datetime.date.today()

        def add(level, category, title, detail, kind="Cihaz", item_id="", date_text=""):
            items.append({
                "level": level,
                "category": category,
                "title": title,
                "detail": detail,
                "kind": kind,
                "id": item_id,
                "date": date_text,
            })

        for kid, rec in records.items():
            if not isinstance(rec, dict):
                continue
            code = str(rec.get("c_no", "") or kid)
            name = str(rec.get("m", "") or "")
            device = str(rec.get("ci", "") or "")
            status = str(rec.get("d", "") or "")
            delivery = str(rec.get("teslim_durumu", "") or "")
            status_plain = self.normalize_upper(f"{status} {delivery}").replace("İ", "I")
            delivered_ok, is_iade = self.is_delivered_record(rec)

            if str(rec.get("approval_status", "") or "") == "Bekliyor":
                add("Kritik", "Müşteri Onayı", f"{code} onay bekliyor", f"{name} / {device} için müşteri onayı henüz sonuçlanmadı.", "Cihaz", kid, rec.get("approval_requested_at", rec.get("z", "")))

            if not delivered_ok and "TESLIM BEKLIYOR" in status_plain:
                add("Uyarı", "Teslim", f"{code} teslim bekliyor", f"{name} / {device} müşteriye teslim edilmeyi bekliyor.", "Cihaz", kid, rec.get("z", ""))
            if not delivered_ok and "IADE BEKLIYOR" in status_plain:
                add("Uyarı", "İade", f"{code} iade teslimi bekliyor", f"{name} / {device} iade teslimi bekliyor.", "Cihaz", kid, rec.get("z", ""))

            if delivered_ok and rec.get("odeme_durumu", "Ödenmedi") != "Ödendi" and safe_float(rec.get("masraf", "0")) > 0:
                add("Kritik", "Ödeme", f"{code} ödeme bekliyor", f"{name} / {device} teslim edilmiş ama {format_money(safe_float(rec.get('masraf', 0)), '₺')} ödenmemiş.", "Cihaz", kid, self.delivery_date_for_record(rec))

            warranty_until = str(rec.get("garanti_bitis", "") or "")
            if warranty_until:
                try:
                    end_date = datetime.datetime.strptime(warranty_until, "%d.%m.%Y").date()
                    left = (end_date - today).days
                    if 0 <= left <= 7:
                        add("Bilgi", "Garanti", f"{code} garanti bitiyor", f"{name} / {device} garanti bitişine {left} gün kaldı.", "Cihaz", kid, warranty_until)
                except:
                    pass

            created_dt = self.parse_date_value(rec.get("z", ""))
            active_statuses = ["IŞLEM BEKLIYOR", "ISLEM BEKLIYOR", "TAMIRDE", "PARÇA BEKLIYOR", "PARCA BEKLIYOR"]
            if created_dt != datetime.datetime.min and any(s in status_plain for s in active_statuses):
                age = (today - created_dt.date()).days
                if age >= 5:
                    add("Uyarı", "Geciken İş", f"{code} {age} gündür işlemde", f"{name} / {device} uzun süredir açık durumda.", "Cihaz", kid, rec.get("z", ""))

        stok = safe_dict_parse(getattr(self, "stok_data", {}))
        if isinstance(stok, dict):
            for sid, item in stok.items():
                if not isinstance(item, dict):
                    continue
                qty = safe_float(item.get("adet", "0"))
                if qty <= 2:
                    stock_code = self.stock_code_for_item(sid, item)
                    add("Uyarı" if qty > 0 else "Kritik", "Stok", f"{stock_code} düşük stok", f"{item.get('ad', '')} stok adedi {self.format_quantity(qty)}.", "Stok", sid, "")

        level_order = {"Kritik": 0, "Uyarı": 1, "Bilgi": 2}
        items.sort(key=lambda item: (level_order.get(item["level"], 9), item["category"], item["title"]))
        return items

    def update_notification_summary(self):
        if not hasattr(self, "btn_notification_center"):
            return
        items = self.collect_notification_items()
        critical = sum(1 for item in items if item.get("level") == "Kritik")
        warning = sum(1 for item in items if item.get("level") == "Uyarı")
        self.btn_notification_center.setText(f"🔔 Bildirim Merkezi ({len(items)})" if items else "🔔 Bildirim Merkezi")
        if not items:
            self.lbl_notification_summary.setText("Kontrol edilecek bildirim yok")
            self.lbl_notification_summary.setStyleSheet("font-size:13px; font-weight:bold; color:#22c55e; padding:6px;")
        else:
            self.lbl_notification_summary.setText(f"Kritik: {critical}  |  Uyarı: {warning}  |  Toplam: {len(items)}")
            self.lbl_notification_summary.setStyleSheet("font-size:13px; font-weight:bold; color:#f59e0b; padding:6px;")

    def show_notification_center(self):
        items = self.collect_notification_items()
        dlg = QDialog(self)
        dlg.setWindowTitle("Bildirim Merkezi")
        dlg.resize(920, 560)
        lay = QVBoxLayout(dlg)
        info = QLabel(f"<b>{len(items)}</b> bildirim bulundu. Bir bildirime çift tıklayınca ilgili kayıt açılır.")
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(["Öncelik", "Kategori", "Başlık", "Detay", "Tarih", "Tür"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        level_colors = {"Kritik": QColor("#ef4444"), "Uyarı": QColor("#f59e0b"), "Bilgi": QColor("#38bdf8")}
        for item_data in items:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                item_data.get("level", ""),
                item_data.get("category", ""),
                item_data.get("title", ""),
                item_data.get("detail", ""),
                item_data.get("date", ""),
                item_data.get("kind", ""),
            ]
            color = level_colors.get(item_data.get("level", ""), QColor("#94a3b8"))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(str(value))
                cell.setData(Qt.ItemDataRole.UserRole, item_data)
                if col in [0, 2]:
                    cell.setForeground(color)
                table.setItem(row, col, cell)

        table.cellDoubleClicked.connect(lambda r, c: self.open_notification_item(table.item(r, 0).data(Qt.ItemDataRole.UserRole), dlg))
        btn_row = QHBoxLayout()
        btn_refresh = QPushButton("Yenile")
        btn_close = QPushButton("Kapat")
        btn_refresh.clicked.connect(lambda: (dlg.accept(), self.refresh_all_tables(), QTimer.singleShot(600, self.show_notification_center)))
        btn_close.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_refresh)
        btn_row.addWidget(btn_close)
        lay.addWidget(info)
        lay.addWidget(table, 1)
        lay.addLayout(btn_row)
        dlg.exec()

    def open_notification_item(self, item_data, dlg=None):
        if not isinstance(item_data, dict):
            return
        if dlg:
            dlg.accept()
        kind = item_data.get("kind")
        item_id = item_data.get("id")
        if kind == "Cihaz":
            self.show_device_dossier(item_id)
        elif kind == "Stok":
            self.tabs.setCurrentIndex(8)
            self.select_table_row_by_id(getattr(self, "table_stok", None), item_id)

    def create_tab_header(self, tab, table, filter_opts, status_col_idx):
        layout_main = QVBoxLayout(tab)
        layout_main.addLayout(self.party_legend_bar())
        h_layout = QHBoxLayout()
        s_box = QLineEdit()
        s_box.setStyleSheet("padding: 8px;")
        
        if not hasattr(self, 'search_boxes'): 
            self.search_boxes = []
            self.filter_labels = []
        if not hasattr(self, 'table_filters'):
            self.table_filters = {}
        if not hasattr(self, 'table_filter_callbacks'):
            self.table_filter_callbacks = {}
        if not hasattr(self, 'table_filter_options'):
            self.table_filter_options = {}
            
        self.search_boxes.append(s_box)
        
        f_box = QComboBox()
        self.populate_filter_combo(f_box, filter_opts)
        f_box.setStyleSheet("padding: 8px;")
        self.table_filters[table] = f_box
        self.table_filter_options[table] = list(filter_opts)
        
        lbl = QLabel()
        self.filter_labels.append(lbl)
        
        h_layout.addWidget(s_box)
        h_layout.addWidget(lbl)
        h_layout.addWidget(f_box)
        
        def do_filter():
            st = self.normalize_search_text(s_box.text())
            ft = self.combo_raw_value(f_box)
            for r in range(table.rowCount()):
                match_s = False
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    if item and st in self.normalize_search_text(item.text()): 
                        match_s = True
                        break
                match_f = True
                if ft not in ["Tümü", "All"]:
                    if table in [self.table_done, getattr(self, "table_delivered", None)]:
                        item_p = table.item(r, table.columnCount() - 1)
                        item_d = table.item(r, table.columnCount() - 2)
                        item_s = table.item(r, table.columnCount() - 3)
                        p_txt = item_p.text() if item_p else ""
                        d_txt = item_d.text() if item_d else ""
                        s_txt = item_s.text() if item_s else ""
                        
                        if ft == "Ödendi" and "Ödendi" in p_txt: match_f = True
                        elif ft == "Ödenmedi" and "Ödenmedi" in p_txt: match_f = True
                        elif ft == "Nakit" and "Nakit" in p_txt: match_f = True
                        elif ft == "Kredi Kartı" and "Kart" in p_txt: match_f = True
                        elif ft == "EFT / Havale" and "EFT" in p_txt: match_f = True
                        elif ft == "Teslim Edildi": match_f = ("Teslim Edildi" in s_txt and "Müşteriye Teslim Edildi" in d_txt)
                        elif ft == "Teslim Bekliyor": match_f = ("Teslim Bekliyor" in d_txt and "İADE" not in s_txt.upper() and "IADE" not in s_txt.upper())
                        elif ft == "İade Edildi": match_f = ("İADE" in s_txt.upper() and "Müşteriye Teslim Edildi" in d_txt)
                        elif ft == "İade Bekliyor": match_f = ("İADE" in s_txt.upper() and "Teslim Bekliyor" in d_txt)
                        elif ft == "Müşteriye Teslim Edildi": match_f = ("Müşteriye Teslim Edildi" in d_txt)
                        elif ft == "İşlemi Tamamlandı": match_f = ("Tamamlandı" in s_txt or "Tamamlandi" in s_txt or "Hazır" in s_txt or "Hazir" in s_txt)
                        else: match_f = False
                    else:
                        item_s = table.item(r, status_col_idx)
                        if item_s: 
                            match_f = (ft in item_s.text())
                table.setRowHidden(r, not (match_s and match_f))
                
        self.table_filter_callbacks[table] = do_filter
        s_box.textChanged.connect(do_filter)
        f_box.currentTextChanged.connect(do_filter)
        layout_main.addLayout(h_layout)
        layout_main.addWidget(table)
        return layout_main

    def party_legend_bar(self):
        lay = QHBoxLayout()
        lay.setContentsMargins(2, 0, 2, 0)
        lay.setSpacing(10)
        if not hasattr(self, "party_legend_labels"):
            self.party_legend_labels = []

        def badge(kind, color):
            lbl = QLabel(self.party_legend_text(kind))
            lbl.setStyleSheet(
                f"color: {color}; font-weight: 800; padding: 4px 9px; "
                f"border: 1px solid {color}; border-radius: 7px; background: rgba(148, 163, 184, 0.08);"
            )
            self.party_legend_labels.append((lbl, kind))
            return lbl

        lay.addWidget(badge("partner_device", "#38bdf8"))
        lay.addWidget(badge("registered_customer", "#a78bfa"))
        lay.addStretch()
        return lay

    def party_legend_text(self, kind):
        if kind == "partner_device":
            return self.get_trans("[PARTNER] Partner device", "[BAYİ] Bayi cihazı")
        if kind == "registered_customer":
            return self.get_trans("[REGISTERED] Registered customer", "[KAYITLI] Kayıtlı müşteri")
        return ""

    def refresh_party_legend_labels(self):
        for label, kind in getattr(self, "party_legend_labels", []):
            if label:
                label.setText(self.party_legend_text(kind))

    def bind_dashboard_cards(self):
        card_routes = [
            (self.gb_isl, 2, self.table_act, "Tümü"),
            (self.gb_bek, 3, self.table_ready, "Tümü"),
            (self.gb_teslim_bek, 4, self.table_done, "Teslim Bekliyor"),
            (self.gb_iade_bek, 4, self.table_done, "İade Bekliyor"),
        ]
        for card, tab_index, table, filter_text in card_routes:
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.mousePressEvent = lambda event, ti=tab_index, tbl=table, ft=filter_text: self.open_dashboard_filtered_tab(ti, tbl, ft)

    def open_dashboard_filtered_tab(self, tab_index, table, filter_text):
        self._dashboard_filter_navigation = True
        self.tabs.setCurrentIndex(tab_index)
        self.set_table_filter(table, filter_text)

    def set_table_filter(self, table, filter_text):
        combo = getattr(self, "table_filters", {}).get(table)
        if combo:
            idx = combo.findData(filter_text)
            if idx < 0:
                idx = combo.findText(filter_text)
            if idx < 0:
                idx = combo.findText(self.filter_option_label(filter_text))
            if idx >= 0:
                combo.setCurrentIndex(idx)
        self.apply_table_filter(table)

    def apply_table_filter(self, table):
        callback = getattr(self, "table_filter_callbacks", {}).get(table)
        if callback:
            callback()

    def apply_all_table_filters(self):
        for table in [getattr(self, "table_act", None), getattr(self, "table_ready", None), getattr(self, "table_done", None)]:
            if table:
                self.apply_table_filter(table)

    def filter_option_label(self, option):
        labels = {
            "Tümü": "All",
            "İşlem Bekliyor": "Waiting",
            "Tamirde": "Repairing",
            "Parça Bekliyor": "Waiting Part",
            "İşlemi Tamamlandı": "Completed",
            "İşlemleri Tamamlandı": "Completed",
            "Teslim Bekliyor": "Waiting Delivery",
            "İade Bekliyor": "Waiting Return",
            "Teslim Edildi": "Delivered",
            "Müşteriye Teslim Edildi": "Delivered to Customer",
            "İade Edildi": "Returned",
            "Ödendi": "Paid",
            "Ödenmedi": "Unpaid",
            "Nakit": "Cash",
            "Kredi Kartı": "Credit Card",
            "EFT / Havale": "Bank Transfer",
        }
        return self.get_trans(labels.get(str(option), str(option)), str(option))

    def populate_filter_combo(self, combo, options):
        combo.clear()
        for option in options:
            combo.addItem(self.filter_option_label(option), option)

    def combo_raw_value(self, combo, default="Tümü"):
        value = combo.currentData()
        return str(value if value is not None else (combo.currentText() or default))

    def refresh_table_filter_labels(self):
        for table, combo in getattr(self, "table_filters", {}).items():
            options = getattr(self, "table_filter_options", {}).get(table)
            if not options:
                continue
            current = self.combo_raw_value(combo)
            combo.blockSignals(True)
            self.populate_filter_combo(combo, options)
            idx = combo.findData(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            combo.blockSignals(False)

    def update_main_tab_counts(self, c_act=None, c_ready=None, c_done=None, c_delivered=None):
        if c_act is not None:
            self._tab_count_act = c_act
        if c_ready is not None:
            self._tab_count_ready = c_ready
        if c_done is not None:
            self._tab_count_done = c_done
        if c_delivered is not None:
            self._tab_count_delivered = c_delivered

        c_act = getattr(self, "_tab_count_act", None)
        c_ready = getattr(self, "_tab_count_ready", None)
        c_done = getattr(self, "_tab_count_done", None)
        c_delivered = getattr(self, "_tab_count_delivered", None)

        if c_act is not None:
            self.tabs.setTabText(2, self.get_trans(f"⏳ In Progress ({c_act})", f"⏳ İşlemdekiler ({c_act})"))
            self.update_sidebar_count(2, c_act)
        if c_ready is not None:
            self.tabs.setTabText(3, self.get_trans(f"⌛ Waiting Jobs ({c_ready})", f"⌛ İşlem Bekleyenler ({c_ready})"))
            self.update_sidebar_count(3, c_ready)
        if c_done is not None:
            self.tabs.setTabText(4, self.get_trans(f"📦 Delivery/Return ({c_done})", f"📦 Teslim/İade ({c_done})"))
            self.update_sidebar_count(4, c_done)
        if c_delivered is not None:
            self.tabs.setTabText(5, self.get_trans(f"✅ Delivered ({c_delivered})", f"✅ Teslim Edilenler ({c_delivered})"))
            self.update_sidebar_count(5, c_delivered)

    def toggle_sifre_input(self, text):
        if "Desen" in text or "Pattern" in text: 
            self.f_sifre.hide()
            self.btn_desen.show()
        else: 
            self.btn_desen.hide()
            self.f_sifre.show()

    def toggle_warranty_fields(self, checked):
        self.f_garanti_gun.setEnabled(checked)
        self.lbl_garanti_suresi.setEnabled(checked)
        self.lbl_garanti_gun.setEnabled(checked)
        self.lbl_garanti_suresi.setVisible(checked)
        self.f_garanti_gun.setVisible(checked)
        self.lbl_garanti_gun.setVisible(checked)
        if checked and not self.f_garanti_gun.text().strip():
            self.f_garanti_gun.setText(str(self.user_setting_value("default_warranty_days", "30")))

    def open_pattern(self):
        dlg = PatternLock(self)
        if dlg.exec() == QDialog.DialogCode.Accepted: 
            self.kayitli_desen = dlg.get_pattern()
            self.btn_desen.setText(self.get_trans("Saved ✓", "Desen Kaydedildi ✓"))
            self.btn_desen.setStyleSheet("background-color: #2ecc71;")

    def init_tabs(self):
        self.tab_dash = QWidget()
        self.tab_new = QWidget()
        self.tab_act = QWidget()
        self.tab_rdy = QWidget()
        self.tab_dne = QWidget()
        self.tab_delivered = QWidget()
        self.tab_musteri = QWidget()
        self.tab_dokum = QWidget()
        self.tab_bayi = QWidget()
        self.tab_stk = QWidget()
        self.tab_whl = QWidget()
        self.tab_cur = QWidget()
        self.tab_trash = QWidget()
        self.tab_set = QWidget()
        self.tab_lic = QWidget()
        self.tab_about = QWidget()
        self.tab_admin = QWidget()
        self._adb_cleaner_loaded = bool(self.is_trial_license)
        self._loading_adb_cleaner = False
        self.tab_adb_cleaner = self.create_premium_virus_placeholder() if self.is_trial_license else QWidget()
        
        self.tabs.addTab(self.tab_dash, "Panel")
        self.tabs.addTab(self.tab_new, "Kayıt")
        self.tabs.addTab(self.tab_act, "İşlem")
        self.tabs.addTab(self.tab_rdy, "Bekleyen")
        self.tabs.addTab(self.tab_dne, "Teslim")
        self.tabs.addTab(self.tab_delivered, "Teslim Edilenler")
        self.tabs.addTab(self.tab_musteri, "Müşteriler") 
        self.tabs.addTab(self.tab_bayi, "Bayiler")
        self.tabs.addTab(self.tab_stk, "Stok")
        self.tabs.addTab(self.tab_whl, "Toptancı")
        self.tabs.addTab(self.tab_dokum, "Detaylı Döküm") 
        self.tabs.addTab(self.tab_cur, "Döviz")
        self.tabs.addTab(self.tab_trash, "Çöp Kutusu")
        self.tabs.addTab(self.tab_set, "Ayarlar")
        self.tabs.addTab(self.tab_lic, "Lisans")
        self.tabs.addTab(self.tab_about, "Hakkında")
        self.tabs.addTab(self.tab_admin, "Yönetim")
        self.tabs.addTab(self.tab_adb_cleaner, "Virüs Temizleyici (Premium)" if self.is_trial_license else "Virüs Temizleyici")
        self._adb_cleaner_tab_index = self.tabs.indexOf(self.tab_adb_cleaner)
        self.tabs.currentChanged.connect(self.on_main_tab_changed)
        self.build_sidebar_navigation()
        
        # --- DASHBOARD TAB ---
        l0 = QVBoxLayout(self.tab_dash)
        l0.setContentsMargins(8, 8, 8, 8)
        l0.setSpacing(10)
        self.dashboard_main_layout = l0
        notification_row = QHBoxLayout()
        notification_row.setContentsMargins(0, 0, 0, 0)
        notification_row.setSpacing(8)
        self.btn_notification_center = QPushButton("🔔 Bildirim Merkezi")
        self.btn_notification_center.setObjectName("SecondaryBtn")
        self.btn_notification_center.setMinimumHeight(38)
        self.btn_notification_center.clicked.connect(self.show_notification_center)
        self.lbl_notification_summary = QLabel("Kontrol edilecek bildirim yok")
        self.lbl_notification_summary.setStyleSheet("font-size:13px; font-weight:bold; color:#94a3b8; padding:6px;")
        notification_row.addWidget(self.btn_notification_center)
        notification_row.addWidget(self.lbl_notification_summary, 1)
        self.dashboard_notification_panel = QWidget()
        self.dashboard_notification_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dashboard_notification_panel.setLayout(notification_row)
        l0.addWidget(self.dashboard_notification_panel)

        dash_grid = QGridLayout()
        dash_grid.setContentsMargins(0, 8, 0, 8)
        dash_grid.setHorizontalSpacing(8)
        dash_grid.setVerticalSpacing(8)
        for col in range(4):
            dash_grid.setColumnStretch(col, 1)
        
        self.lbl_gunluk = QLabel("0 ₺")
        self.lbl_haftalik = QLabel("0 ₺")
        self.lbl_aylik = QLabel("0 ₺")
        self.lbl_kasa = QLabel("0 ₺")
        self.lbl_islemde = QLabel("0")
        self.lbl_bekleyen = QLabel("0")
        self.lbl_teslim_bekleyen = QLabel("0")
        self.lbl_iade_bekleyen = QLabel("0")
        
        self.gb_gun = QGroupBox()
        self.gb_haf = QGroupBox()
        self.gb_ay = QGroupBox()
        self.gb_net = QGroupBox()
        self.gb_isl = QGroupBox()
        self.gb_bek = QGroupBox()
        self.gb_teslim_bek = QGroupBox()
        self.gb_iade_bek = QGroupBox()
        
        def setup_card(gb, lbl, color):
            gb.setStyleSheet(f"QGroupBox {{ background: rgba(15, 23, 42, 0.28); border: 2px solid {color}; border-radius: 8px; margin-top: 10px; font-weight: bold; }} QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px 0 4px; }}")
            lay = QVBoxLayout(gb)
            lay.setContentsMargins(12, 14, 12, 12)
            lay.addWidget(lbl)
            lbl.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {color};")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
        setup_card(self.gb_gun, self.lbl_gunluk, "#3498db")
        setup_card(self.gb_haf, self.lbl_haftalik, "#2ecc71")
        setup_card(self.gb_ay, self.lbl_aylik, "#f1c40f")
        setup_card(self.gb_net, self.lbl_kasa, "#e67e22")
        setup_card(self.gb_isl, self.lbl_islemde, "#9b59b6")
        setup_card(self.gb_bek, self.lbl_bekleyen, "#38bdf8")
        setup_card(self.gb_teslim_bek, self.lbl_teslim_bekleyen, "#22c55e")
        setup_card(self.gb_iade_bek, self.lbl_iade_bekleyen, "#f97316")
        self.finance_widgets = [self.gb_gun, self.gb_haf, self.gb_ay, self.gb_net]
        self.operational_widgets = [self.gb_isl, self.gb_bek, self.gb_teslim_bek, self.gb_iade_bek]
        
        dash_grid.addWidget(self.gb_isl, 0, 0)
        dash_grid.addWidget(self.gb_bek, 0, 1)
        dash_grid.addWidget(self.gb_teslim_bek, 0, 2)
        dash_grid.addWidget(self.gb_iade_bek, 0, 3)
        dash_grid.addWidget(self.gb_gun, 1, 0)
        dash_grid.addWidget(self.gb_haf, 1, 1)
        dash_grid.addWidget(self.gb_ay, 1, 2)
        dash_grid.addWidget(self.gb_net, 1, 3)
        self.dashboard_cards_panel = QWidget()
        self.dashboard_cards_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.dashboard_cards_panel.setLayout(dash_grid)
        l0.addWidget(self.dashboard_cards_panel)
        
        self.gb_odeme_detay = QGroupBox("💰 Ödeme Tipleri Toplam Dağılımı")
        self.gb_odeme_detay.setStyleSheet("QGroupBox { border: 1px solid #555; border-radius: 6px; margin-top: 10px; font-weight: bold; }")
        lay_odeme_detay = QHBoxLayout(self.gb_odeme_detay)
        
        self.lbl_tot_nakit = QLabel("Nakit: 0 ₺")
        self.lbl_tot_nakit.setStyleSheet("font-size: 14px; font-weight: bold; color: #2ecc71;")
        
        self.lbl_tot_kart = QLabel("Kredi Kartı: 0 ₺")
        self.lbl_tot_kart.setStyleSheet("font-size: 14px; font-weight: bold; color: #3498db;")
        
        self.lbl_tot_eft = QLabel("EFT / Havale: 0 ₺")
        self.lbl_tot_eft.setStyleSheet("font-size: 14px; font-weight: bold; color: #9b59b6;")
        
        lay_odeme_detay.setSpacing(18)
        lay_odeme_detay.addWidget(self.lbl_tot_nakit)
        lay_odeme_detay.addWidget(self.lbl_tot_kart)
        lay_odeme_detay.addWidget(self.lbl_tot_eft)
        lay_odeme_detay.addStretch()
        l0.addWidget(self.gb_odeme_detay)
        self.finance_widgets.append(self.gb_odeme_detay)

        kasa_ozet = QHBoxLayout()
        self.kasa_summary_label = QLabel("<b>Kasa Özeti:</b>")
        self.kasa_period_cb = QComboBox()
        self.kasa_period_cb.addItems(["Bugün", "Bu Hafta", "Geçen Hafta", "Bu Ay", "Geçen Ay"])
        self.kasa_period_cb.currentTextChanged.connect(self.update_kasa_period_summary)
        self.lbl_kasa_period_summary = QLabel("")
        self.lbl_kasa_period_summary.setStyleSheet("font-size:13px; font-weight:bold; padding:6px;")
        kasa_ozet.addWidget(self.kasa_summary_label)
        kasa_ozet.addWidget(self.kasa_period_cb)
        kasa_ozet.addWidget(self.lbl_kasa_period_summary, 1)
        l0.addLayout(kasa_ozet)
        self.finance_widgets.extend([self.kasa_summary_label, self.kasa_period_cb, self.lbl_kasa_period_summary])
        self.apply_finance_visibility()

        self.cash_entry_panel = QFrame()
        self.cash_entry_panel.setObjectName("CashEntryPanel")
        self.cash_entry_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.cash_entry_panel.setStyleSheet("""
            QFrame#CashEntryPanel {
                background: rgba(15, 23, 42, 0.34);
                border: 1px solid rgba(96, 165, 250, 0.24);
                border-radius: 8px;
            }
            QFrame#CashEntryPanel QLabel#CashEntryTitle {
                color: #f8fafc;
                font-size: 15px;
                font-weight: 800;
            }
        """)
        cash_entry_layout = QVBoxLayout(self.cash_entry_panel)
        cash_entry_layout.setContentsMargins(12, 10, 12, 12)
        cash_entry_layout.setSpacing(8)
        self.lbl_kasa_title = QLabel("Manuel Kasa İşlemleri")
        self.lbl_kasa_title.setObjectName("CashEntryTitle")
        cash_entry_layout.addWidget(self.lbl_kasa_title)

        h_kasa = QHBoxLayout()
        h_kasa.setContentsMargins(0, 0, 0, 0)
        h_kasa.setSpacing(8)
        self.k_tip = QComboBox()
        self.k_tip.addItems(["Gelir", "Gider"])
        self.k_tip.setFixedWidth(92)
        self.k_odeme_tipi = QComboBox()
        self.populate_payment_method_combo(self.k_odeme_tipi)
        self.k_odeme_tipi.setFixedWidth(128)
        
        self.k_aciklama = QLineEdit()
        self.k_aciklama.setPlaceholderText("Açıklama...")
        
        self.k_tutar = QLineEdit()
        self.k_tutar.setPlaceholderText("Tutar (₺)")
        self.k_tutar.setFixedWidth(138)
        
        self.b_kasa_ekle = QPushButton("Ekle")
        self.b_kasa_ekle.setFixedWidth(120)
        self.b_kasa_ekle.clicked.connect(self.add_kasa)
        
        h_kasa.addWidget(self.k_tip)
        h_kasa.addWidget(self.k_odeme_tipi)
        h_kasa.addWidget(self.k_aciklama)
        h_kasa.addWidget(self.k_tutar)
        h_kasa.addWidget(self.b_kasa_ekle)
        cash_entry_layout.addLayout(h_kasa)
        l0.addWidget(self.cash_entry_panel)
        
        self.table_kasa = self.create_table(6)
        l0.addWidget(self.table_kasa)
        self.dashboard_bottom_spacer = QWidget()
        self.dashboard_bottom_spacer.setMinimumHeight(0)
        self.dashboard_bottom_spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.dashboard_bottom_spacer.setVisible(False)
        l0.addWidget(self.dashboard_bottom_spacer, 1)

        # --- YENİ KAYIT TAB ---
        l1 = QVBoxLayout(self.tab_new)
        l1.setSpacing(6)
        
        self.cb_registered_customer = QPushButton("Kayıtlı müşteri seç")
        self.cb_registered_customer.setCheckable(True)
        self.cb_bayi_kayit = QPushButton("Bayi seç")
        self.cb_bayi_kayit.setCheckable(True)
        self.record_mode_panel = QFrame()
        self.record_mode_panel.setObjectName("RecordModePanel")
        self.record_mode_panel.setStyleSheet("""
            QFrame#RecordModePanel {
                border: 1px solid rgba(148, 163, 184, 0.45);
                border-radius: 8px;
                background: rgba(148, 163, 184, 0.08);
                padding: 6px;
            }
            QLabel#RecordModeTitle { font-size: 13px; font-weight: 700; color: #94a3b8; }
            QLabel#RecordModeText { font-size: 13px; font-weight: 800; }
            QFrame#RecordModePanel QPushButton {
                font-weight: 800;
                min-height: 30px;
                max-height: 30px;
                padding: 4px 10px;
                border-radius: 8px;
            }
            QFrame#RecordModePanel QPushButton:checked {
                background: #2563eb;
                color: white;
                border: 1px solid #60a5fa;
            }
        """)
        self.record_mode_panel.setMinimumHeight(50)
        record_mode_lay = QHBoxLayout(self.record_mode_panel)
        record_mode_lay.setContentsMargins(12, 6, 12, 6)
        record_mode_lay.setSpacing(10)
        self.lbl_record_mode_title = QLabel("Kayıt Türü:")
        self.lbl_record_mode_title.setObjectName("RecordModeTitle")
        self.lbl_record_mode_state = QLabel("Yeni müşteri kaydı")
        self.lbl_record_mode_state.setObjectName("RecordModeText")
        self.lbl_record_mode_title.setMinimumHeight(28)
        self.lbl_record_mode_state.setMinimumHeight(28)
        self.cb_registered_customer.setFixedSize(132, 30)
        self.cb_bayi_kayit.setFixedSize(78, 30)
        self.cb_registered_customer.toggled.connect(self.toggle_registered_customer_mode)
        record_mode_lay.addWidget(self.lbl_record_mode_title)
        record_mode_lay.addWidget(self.lbl_record_mode_state, 1)
        record_mode_lay.addWidget(self.cb_registered_customer)
        record_mode_lay.addWidget(self.cb_bayi_kayit)
        record_mode_lay.setAlignment(self.cb_registered_customer, Qt.AlignmentFlag.AlignVCenter)
        record_mode_lay.setAlignment(self.cb_bayi_kayit, Qt.AlignmentFlag.AlignVCenter)
        
        self.f_ad = QLineEdit()
        self.musteri_completer = QCompleter()
        self.musteri_model = QStringListModel(self.filtered_suggestions("musteri", self.musteri_listesi))
        self.musteri_completer.setModel(self.musteri_model)
        self.f_ad.setCompleter(self.musteri_completer)
        self.configure_suggestion_completer(self.musteri_completer, "musteri", self.f_ad, "Müşteri")
        self.btn_musteri_sec = QPushButton("Kayıtlı Müşteri Seç")
        self.btn_musteri_sec.setObjectName("SecondaryBtn")
        self.btn_musteri_sec.clicked.connect(self.open_customer_picker)
        self.btn_musteri_sec.hide()
        self.lbl_musteri_uyari = QLabel("")
        self.lbl_musteri_uyari.setStyleSheet("color:#f59e0b; font-weight:600; padding: 2px 0;")
        self.lbl_musteri_uyari.hide()
        self.customer_suggestions = QListWidget()
        self.customer_suggestions.setMaximumHeight(118)
        self.customer_suggestions.setVisible(False)
        self.customer_suggestions.itemDoubleClicked.connect(self.apply_customer_suggestion)
        
        self.combo_bayi = QComboBox()
        self.combo_bayi.hide()
        self.combo_bayi.currentTextChanged.connect(self.fill_partner_phone)
        self.cb_bayi_kayit.toggled.connect(self.toggle_bayi_mode)
        
        self.f_tel = QLineEdit()
        self.f_tel.setMaxLength(10)
        self.f_tel.setPlaceholderText("Telefon (opsiyonel)")
        self.f_ad.textChanged.connect(self.update_customer_hint)
        self.f_tel.textChanged.connect(self.update_customer_hint)
        self.f_ad.textEdited.connect(self.clear_selected_customer_selection)
        self.f_tel.textEdited.connect(self.clear_selected_customer_selection)
        
        self.f_cihaz = QLineEdit()
        self.cihaz_completer = QCompleter()
        self.cihaz_model = QStringListModel(self.filtered_suggestions("cihaz", self.cihaz_listesi))
        self.cihaz_completer.setModel(self.cihaz_model)
        self.f_cihaz.setCompleter(self.cihaz_completer)
        self.configure_suggestion_completer(self.cihaz_completer, "cihaz", self.f_cihaz, "Cihaz")
        
        self.f_ariza = QLineEdit()
        self.ariza_completer = QCompleter()
        self.ariza_model = QStringListModel(self.filtered_suggestions("ariza", self.ariza_listesi))
        self.ariza_completer.setModel(self.ariza_model)
        self.f_ariza.setCompleter(self.ariza_completer)
        self.configure_suggestion_completer(self.ariza_completer, "ariza", self.f_ariza, "Arıza")
        for field in [self.f_ad, self.f_cihaz, self.f_ariza]:
            field.textEdited.connect(lambda text, w=field: self.force_uppercase(w, text))
        self.extra_faults = []
        self.btn_ariza_ekle = QPushButton("+ Ek Arıza")
        self.btn_ariza_ekle.setToolTip("Aynı cihaz için ikinci/üçüncü arıza ekle")
        self.btn_ariza_ekle.clicked.connect(self.add_extra_fault_from_form)
        self.lbl_ariza_ozet = QLabel("")
        self.lbl_ariza_ozet.setWordWrap(True)
        self.lbl_ariza_ozet.setStyleSheet("color:#94a3b8; font-size:11px;")
        self.f_not = QTextEdit()
        self.f_not.setAcceptRichText(False)
        self.f_not.setFixedHeight(72)
        self.f_not.setPlaceholderText("Müşteri notu (opsiyonel)")
        self.f_yaklasik = QLineEdit()
        self.f_yaklasik.setPlaceholderText("Yaklaşık ücret (opsiyonel ₺)")
        self.warranty_panel = QFrame()
        self.warranty_panel.setObjectName("WarrantyPanel")
        self.warranty_panel.setStyleSheet("""
            QFrame#WarrantyPanel {
                border: 1px solid rgba(148, 163, 184, 0.35);
                border-radius: 8px;
                background: rgba(148, 163, 184, 0.06);
                padding: 6px;
            }
            QLabel { font-weight: 700; }
        """)
        warranty_lay = QHBoxLayout(self.warranty_panel)
        warranty_lay.setContentsMargins(8, 4, 8, 4)
        self.cb_garanti_ver = QCheckBox("Garanti ver")
        self.cb_garanti_ver.setToolTip("Bu cihaz için servis garantisi tanımla")
        self.lbl_garanti_suresi = QLabel("Garanti süresi:")
        self.f_garanti_gun = QLineEdit()
        self.f_garanti_gun.setPlaceholderText("Gün")
        self.f_garanti_gun.setText(str(self.user_setting_value("default_warranty_days", "30")))
        self.f_garanti_gun.setFixedSize(96, 34)
        self.f_garanti_gun.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.f_garanti_gun.setStyleSheet("padding: 4px 10px; font-size: 13px;")
        self.lbl_garanti_gun = QLabel("gün")
        self.f_garanti_gun.setEnabled(False)
        self.lbl_garanti_suresi.setEnabled(False)
        self.lbl_garanti_gun.setEnabled(False)
        self.lbl_garanti_suresi.hide()
        self.f_garanti_gun.hide()
        self.lbl_garanti_gun.hide()
        self.cb_garanti_ver.toggled.connect(self.toggle_warranty_fields)
        warranty_lay.addWidget(self.cb_garanti_ver)
        warranty_lay.addSpacing(12)
        warranty_lay.addWidget(self.lbl_garanti_suresi)
        warranty_lay.addWidget(self.f_garanti_gun)
        warranty_lay.addWidget(self.lbl_garanti_gun)
        warranty_lay.addStretch()
        
        s_lay = QHBoxLayout()
        self.sifre_tipi = QComboBox()
        self.sifre_tipi.addItems(["Metin", "Desen"])
        self.f_sifre = QLineEdit()
        self.f_sifre.setObjectName("device_password_input")
        self.f_sifre.setProperty("allow_lowercase", True)
        self.btn_desen = QPushButton("Desen")
        self.btn_desen.hide()
        self.btn_desen.clicked.connect(self.open_pattern)
        self.sifre_tipi.currentTextChanged.connect(self.toggle_sifre_input)
        self.kayitli_desen = ""
        
        s_lay.addWidget(self.sifre_tipi)
        s_lay.addWidget(self.f_sifre)
        s_lay.addWidget(self.btn_desen)
        
        acc_lay = QHBoxLayout()
        self.cb_sim = QCheckBox("SIM")
        self.cb_sd = QCheckBox("SD")
        self.cb_kilif = QCheckBox("Kılıf")
        acc_lay.addWidget(self.cb_sim)
        acc_lay.addWidget(self.cb_sd)
        acc_lay.addWidget(self.cb_kilif)
        acc_lay.addStretch()
        
        self.b_save = QPushButton("Kaydet")
        self.b_save.setStyleSheet("padding:15px; font-size:14px; background-color:#2ecc71;")
        self.b_save.clicked.connect(self.save_device)
        self.setup_new_record_keyboard_flow()
        
        self.lbl_yeni_title = QLabel("<h2>Kayıt</h2>")
        self.lbl_guv_title = QLabel("<b>Aksesuarlar:</b>")
        
        l1.addWidget(self.lbl_yeni_title)
        l1.addWidget(self.record_mode_panel)
        l1.addWidget(self.btn_musteri_sec)
        l1.addWidget(self.f_ad)
        l1.addWidget(self.lbl_musteri_uyari)
        l1.addWidget(self.customer_suggestions)
        l1.addWidget(self.combo_bayi)
        l1.addWidget(self.f_tel)
        l1.addWidget(self.f_cihaz)
        l1.addWidget(self.f_ariza)
        l1.addWidget(self.btn_ariza_ekle)
        l1.addWidget(self.lbl_ariza_ozet)
        l1.addWidget(self.f_not)
        l1.addWidget(self.f_yaklasik)
        l1.addWidget(self.warranty_panel)
        l1.addWidget(self.lbl_guv_title)
        l1.addLayout(s_lay)
        l1.addLayout(acc_lay)
        l1.addWidget(self.b_save)
        l1.addStretch()
        
        self.table_act = self.create_table(8)
        self.create_tab_header(self.tab_act, self.table_act, ["Tümü", "Tamirde", "Parça Bekliyor"], 7)
        self.tune_service_table_columns(self.table_act, "active")
        
        self.table_ready = self.create_table(8)
        self.create_tab_header(self.tab_rdy, self.table_ready, ["Tümü", "İşlem Bekliyor"], 7) 
        self.tune_service_table_columns(self.table_ready, "ready")
        
        self.table_done = self.create_table(10)
        lay_done = self.create_tab_header(self.tab_dne, self.table_done, ["Tümü", "İşlemi Tamamlandı", "Ödendi", "Ödenmedi", "Nakit", "Kredi Kartı", "EFT / Havale", "Teslim Bekliyor", "İade Bekliyor"], 7)
        self.tune_service_table_columns(self.table_done, "done")
        self.bind_dashboard_cards()
        
        finans_panel = QHBoxLayout()
        self.lbl_toplam = QLabel("")
        self.lbl_alacak = QLabel("")
        self.lbl_toplam.setStyleSheet("font-size: 14px; color: #2ecc71;")
        self.lbl_alacak.setStyleSheet("font-size: 14px; color: #ef4444;")
        finans_panel.addWidget(self.lbl_toplam)
        finans_panel.addStretch()
        finans_panel.addWidget(self.lbl_alacak)
        lay_done.addLayout(finans_panel)
        teslim_odeme_panel = QHBoxLayout()
        self.lbl_done_nakit = QLabel("")
        self.lbl_done_kart = QLabel("")
        self.lbl_done_eft = QLabel("")
        self.lbl_done_nakit.setStyleSheet("font-size:13px; font-weight:bold; color:#22c55e;")
        self.lbl_done_kart.setStyleSheet("font-size:13px; font-weight:bold; color:#38bdf8;")
        self.lbl_done_eft.setStyleSheet("font-size:13px; font-weight:bold; color:#f59e0b;")
        teslim_odeme_panel.setSpacing(18)
        teslim_odeme_panel.addWidget(self.lbl_done_nakit)
        teslim_odeme_panel.addWidget(self.lbl_done_kart)
        teslim_odeme_panel.addWidget(self.lbl_done_eft)
        teslim_odeme_panel.addStretch()
        lay_done.addLayout(teslim_odeme_panel)

        # --- TESLIM EDILENLER GECMISI ---
        l_delivered = QVBoxLayout(self.tab_delivered)
        l_delivered.addLayout(self.party_legend_bar())
        delivered_top = QHBoxLayout()
        delivered_top.addWidget(QLabel("<b>Teslim Geçmişi:</b>"))

        self.delivered_period_cb = QComboBox()
        self.delivered_period_cb.addItems(["Tümü", "Bugün", "Bu Hafta", "Bu Ay", "Tarih Aralığı"])
        self.delivered_period_cb.setFixedWidth(130)

        self.delivered_status_cb = QComboBox()
        self.delivered_status_cb.addItems(["Tümü", "Başarılı Teslim", "İade Teslim", "Ödendi", "Ödenmedi"])
        self.delivered_status_cb.setFixedWidth(170)

        self.delivered_date_start = QDateEdit()
        self.delivered_date_end = QDateEdit()
        self.setup_calendar_date_edit(self.delivered_date_start)
        self.setup_calendar_date_edit(self.delivered_date_end)
        today_qdate = QDate.currentDate()
        self.delivered_date_start.setDate(today_qdate)
        self.delivered_date_end.setDate(today_qdate)

        self.btn_delivered_excel = QPushButton("📊 Excel'e Aktar")
        self.btn_delivered_excel.clicked.connect(lambda: self.export_table_to_excel_csv(self.table_delivered, "Teslim_Edilenler_Raporu"))

        for w in [
            self.delivered_period_cb,
            QLabel("Başlangıç:"),
            self.delivered_date_start,
            QLabel("Bitiş:"),
            self.delivered_date_end,
            QLabel("Filtre:"),
            self.delivered_status_cb,
            self.btn_delivered_excel,
        ]:
            delivered_top.addWidget(w)
        delivered_top.addStretch()
        l_delivered.addLayout(delivered_top)

        self.table_delivered = self.create_table(10)
        self.tune_service_table_columns(self.table_delivered, "done")
        l_delivered.addWidget(self.table_delivered)

        delivered_payment_panel = QHBoxLayout()
        self.lbl_delivered_nakit = QLabel("")
        self.lbl_delivered_kart = QLabel("")
        self.lbl_delivered_eft = QLabel("")
        self.lbl_delivered_nakit.setStyleSheet("font-size:13px; font-weight:bold; color:#22c55e;")
        self.lbl_delivered_kart.setStyleSheet("font-size:13px; font-weight:bold; color:#38bdf8;")
        self.lbl_delivered_eft.setStyleSheet("font-size:13px; font-weight:bold; color:#f59e0b;")
        delivered_payment_panel.setSpacing(18)
        delivered_payment_panel.addWidget(self.lbl_delivered_nakit)
        delivered_payment_panel.addWidget(self.lbl_delivered_kart)
        delivered_payment_panel.addWidget(self.lbl_delivered_eft)
        delivered_payment_panel.addStretch()
        l_delivered.addLayout(delivered_payment_panel)

        self.lbl_delivered_summary = QLabel("")
        self.lbl_delivered_summary.setStyleSheet("font-weight:bold; color:#38bdf8;")
        l_delivered.addWidget(self.lbl_delivered_summary)

        self.delivered_period_cb.currentTextChanged.connect(self.on_delivered_period_changed)
        self.delivered_period_cb.activated.connect(lambda _: self.on_delivered_period_changed(self.delivered_period_cb.currentText()))
        self.delivered_status_cb.currentTextChanged.connect(self.on_delivered_status_changed)
        self.delivered_status_cb.activated.connect(lambda _: self.on_delivered_status_changed(self.delivered_status_cb.currentText()))
        self.delivered_date_start.dateChanged.connect(lambda _: self.on_delivered_date_changed())
        self.delivered_date_end.dateChanged.connect(lambda _: self.on_delivered_date_changed())
        self.on_delivered_period_changed("Tümü")
        
        # --- MÜŞTERİ GEÇMİŞİ SEKMESİ ---
        l_must_main = QHBoxLayout(self.tab_musteri)
        must_sol = QVBoxLayout()
        must_sol.addWidget(QLabel("<b>Müşteri Listesi</b>"))
        
        self.must_search = QLineEdit()
        self.must_search.setPlaceholderText("🔍 Müşteri Adı Ara...")
        self.must_search.setFixedWidth(220)
        self.must_search.textChanged.connect(self.filter_musteri_listesi)
        self.must_filter_cb = QComboBox()
        self.must_filter_cb.addItems(["Alfabetik", "Son Kayıt", "Ödeme Yapanlar", "Ödeme Yapmayanlar"])
        self.must_filter_cb.setFixedWidth(220)
        self.must_filter_cb.currentTextChanged.connect(self.rebuild_party_lists)
        self.lbl_musteri_sayac = QLabel("")
        self.lbl_musteri_sayac.setStyleSheet("color:#94a3b8; font-weight:bold;")
        must_sol.addWidget(self.must_search)
        must_sol.addWidget(self.must_filter_cb)
        must_sol.addWidget(self.lbl_musteri_sayac)
        
        self.list_musteriler = QListWidget()
        self.list_musteriler.setFixedWidth(220)
        self.list_musteriler.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_musteriler.itemClicked.connect(self.load_musteri_cihaz_gecmisi)
        self.list_musteriler.itemDoubleClicked.connect(self.show_customer_detail)
        self.list_musteriler.customContextMenuRequested.connect(self.open_musteri_list_menu)
        must_sol.addWidget(self.list_musteriler)
        l_must_main.addLayout(must_sol, 0)
        
        must_sag = QVBoxLayout()
        self.lbl_secili_musteri = QLabel("<h2>Müşteri Seçin</h2>")
        must_sag.addWidget(self.lbl_secili_musteri)
        
        self.table_musteri_gecmis = self.create_table(7)
        self.table_musteri_gecmis.setHorizontalHeaderLabels(["ID", "Kayıt No", "Cihaz", "Arıza", "İşlem", "Ücret", "Zaman"])
        must_sag.addWidget(self.table_musteri_gecmis)
        l_must_main.addLayout(must_sag, 1)

        # --- DETAYLI DÖKÜM VE TAKVİMLİ FİLTRELEME SEKMESİ ---
        l_dokum = QVBoxLayout(self.tab_dokum)
        h_dokum_ust = QHBoxLayout()
        
        self.date_basla = QDateEdit()
        self.date_basla.setCalendarPopup(True)
        self.date_basla.setDisplayFormat("dd.MM.yyyy")
        self.date_basla.setDate(QDate.currentDate().addMonths(-3))
        
        self.date_bitis = QDateEdit()
        self.date_bitis.setCalendarPopup(True)
        self.date_bitis.setDisplayFormat("dd.MM.yyyy")
        self.date_bitis.setDate(QDate.currentDate())

        for date_edit in (self.date_basla, self.date_bitis):
            self.setup_calendar_date_edit(date_edit)
        
        btn_dokum_listele = QPushButton("🔍 Seçili Tarih Aralığını Dök")
        btn_dokum_listele.setStyleSheet("background-color:#3584e4; font-weight:bold; padding:8px;")
        btn_dokum_listele.clicked.connect(self.filter_dokum_by_date)
        self.btn_dokum_excel = QPushButton("Excel'e Aktar")
        self.btn_dokum_excel.clicked.connect(lambda: self.export_table_to_excel_csv(self.table_dokum, "Detayli_Dokum_Raporu"))
        
        h_dokum_ust.addWidget(QLabel("Başlangıç:"))
        h_dokum_ust.addWidget(self.date_basla)
        h_dokum_ust.addWidget(QLabel("📅"))
        h_dokum_ust.addWidget(QLabel("Bitiş:"))
        h_dokum_ust.addWidget(self.date_bitis)
        h_dokum_ust.addWidget(QLabel("📅"))
        h_dokum_ust.addWidget(btn_dokum_listele)
        h_dokum_ust.addWidget(self.btn_dokum_excel)
        h_dokum_ust.addStretch()
        l_dokum.addLayout(h_dokum_ust)
        
        self.table_dokum = self.create_table(8)
        self.table_dokum.setHorizontalHeaderLabels(["ID", "Kayıt No", "Müşteri", "Cihaz", "İşlem", "Ücret", "Ödeme Tipi", "Zaman"])
        l_dokum.addWidget(self.table_dokum)
        
        self.lbl_dokum_alt_toplam = QLabel("")
        self.lbl_dokum_alt_toplam.setStyleSheet("font-size: 13px; font-weight: bold; color: #f1c40f; padding: 5px; background: #2d2d2d; border-radius: 4px;")
        l_dokum.addWidget(self.lbl_dokum_alt_toplam)
        self.date_basla.dateChanged.connect(self.filter_dokum_by_date)
        self.date_bitis.dateChanged.connect(self.filter_dokum_by_date)

        # --- BAYİLER TAB ---
        l_bayi_main = QHBoxLayout(self.tab_bayi)
        l_bayi_main.setContentsMargins(8, 8, 8, 8)
        l_bayi_main.setSpacing(12)
        bayi_sol_panel = QWidget()
        bayi_sol_panel.setFixedWidth(220)
        bayi_sol = QVBoxLayout()
        bayi_sol.setContentsMargins(0, 0, 0, 0)
        bayi_sol.setSpacing(8)
        
        self.lbl_kayitli_bayiler = QLabel("<b>Kayıtlı Bayiler</b>")
        self.bayi_search_sol = QLineEdit()
        self.bayi_search_sol.setPlaceholderText("🔍 Bayi Ara...")
        self.bayi_search_sol.setFixedWidth(220)
        self.bayi_search_sol.textChanged.connect(self.filter_bayi_listesi)
        self.bayi_filter_cb = QComboBox()
        self.bayi_filter_cb.addItems(["Alfabetik", "Son Kayıt", "Ödeme Yapanlar", "Ödeme Yapmayanlar"])
        self.bayi_filter_cb.setFixedWidth(220)
        self.bayi_filter_cb.currentTextChanged.connect(self.rebuild_party_lists)
        self.lbl_bayi_sayac = QLabel("")
        self.lbl_bayi_sayac.setStyleSheet("color:#94a3b8; font-weight:bold;")
        
        bayi_sol.addWidget(self.lbl_kayitli_bayiler)
        bayi_sol.addWidget(self.bayi_search_sol)
        bayi_sol.addWidget(self.bayi_filter_cb)
        bayi_sol.addWidget(self.lbl_bayi_sayac)
        
        self.list_bayiler = QListWidget()
        self.list_bayiler.setFixedWidth(220)
        self.list_bayiler.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_bayiler.itemClicked.connect(self.load_bayi_detay)
        self.list_bayiler.customContextMenuRequested.connect(self.open_bayi_list_menu)
        bayi_sol.addWidget(self.list_bayiler, 1)
        
        h_bayi_btn = QHBoxLayout()
        h_bayi_btn.setSpacing(6)
        self.btn_bayi_ekle = QPushButton("Ekle")
        self.btn_bayi_sil = QPushButton("Sil")
        self.btn_bayi_ekle.setFixedWidth(70)
        self.btn_bayi_sil.setFixedWidth(70)
        self.btn_bayi_ekle.setFixedHeight(32)
        self.btn_bayi_sil.setFixedHeight(32)
        self.btn_bayi_ekle.setToolTip("Bayi ekle")
        self.btn_bayi_sil.setToolTip("Seçili bayiyi sil")
        self.btn_bayi_sil.setStyleSheet("background-color: #ef4444;")
        self.btn_bayi_ekle.clicked.connect(self.manuel_bayi_ekle)
        self.btn_bayi_sil.clicked.connect(self.manuel_bayi_sil)
        
        h_bayi_btn.addWidget(self.btn_bayi_ekle)
        h_bayi_btn.addWidget(self.btn_bayi_sil)
        h_bayi_btn.addStretch()
        bayi_sol.addLayout(h_bayi_btn)
        bayi_sol_panel.setLayout(bayi_sol)
        l_bayi_main.addWidget(bayi_sol_panel, 0)
        
        bayi_sag = QVBoxLayout()
        bayi_sag.setSpacing(8)
        self.lbl_secili_bayi = QLabel("<h2>Seç</h2>")
        self.bayi_search_sag = QLineEdit()
        self.bayi_search_sag.setPlaceholderText("🔍 Cihaz, Arıza veya İşlem Ara...")
        self.bayi_search_sag.textChanged.connect(self.filter_bayi_tablosu)
        self.btn_bayi_excel = QPushButton("Excel'e Aktar")
        self.btn_bayi_excel.clicked.connect(lambda: self.export_table_to_excel_csv(self.table_bayi, "Bayi_Raporu"))
        self.table_bayi = self.create_table(8)
        
        bayi_sag.addWidget(self.lbl_secili_bayi)
        bayi_sag.addWidget(self.bayi_search_sag)
        bayi_sag.addWidget(self.btn_bayi_excel)
        bayi_sag.addWidget(self.table_bayi)
        
        bayi_finans = QHBoxLayout()
        self.lbl_bayi_adet = QLabel("")
        self.lbl_bayi_total = QLabel("")
        self.lbl_bayi_odenen = QLabel("")
        self.lbl_bayi_kalan = QLabel("")
        
        self.lbl_bayi_adet.setStyleSheet("color:#aaaaaa;")
        self.lbl_bayi_total.setStyleSheet("color:#3498db;")
        self.lbl_bayi_odenen.setStyleSheet("color:#2ecc71;")
        self.lbl_bayi_kalan.setStyleSheet("color:#ef4444;")
        
        bayi_finans.addStretch()
        bayi_finans.addWidget(self.lbl_bayi_adet)
        bayi_finans.addSpacing(15)
        bayi_finans.addWidget(self.lbl_bayi_total)
        bayi_finans.addSpacing(15)
        bayi_finans.addWidget(self.lbl_bayi_odenen)
        bayi_finans.addSpacing(15)
        bayi_finans.addWidget(self.lbl_bayi_kalan)
        bayi_sag.addLayout(bayi_finans)
        l_bayi_main.addLayout(bayi_sag, 1)

        # --- STOK TAB ---
        l_stk = QVBoxLayout(self.tab_stk)
        stk_top_panel = QHBoxLayout()
        self.lbl_stok_deger = QLabel("")
        self.lbl_stok_deger.setStyleSheet("font-size: 16px; color: #f1c40f;")
        self.btn_stok_excel = QPushButton("Excel'e Aktar")
        self.btn_stok_excel.clicked.connect(lambda: self.export_table_to_excel_csv(self.table_stok, "Stok_Raporu"))
        stk_top_panel.addWidget(self.lbl_stok_deger)
        stk_top_panel.addStretch()
        stk_top_panel.addWidget(self.btn_stok_excel)
        l_stk.addLayout(stk_top_panel)

        barcode_panel = QHBoxLayout()
        self.stk_barcode_mode = QComboBox()
        self.stk_barcode_mode.addItem("Stok Girişi +1", "in")
        self.stk_barcode_mode.addItem("Stok Çıkışı -1", "out")
        self.stk_barcode_mode.addItem("Ürün Sorgula / Fiyat Kontrolü", "query")
        self.stk_barcode_mode.currentIndexChanged.connect(self.update_stock_barcode_button)
        self.stk_barcode_input = QLineEdit()
        self.stk_barcode_input.setPlaceholderText("Barkod okut veya yaz...")
        self.stk_barcode_input.returnPressed.connect(self.process_stock_barcode)
        self.btn_stk_barcode = QPushButton("Barkodu İşle")
        self.btn_stk_barcode.clicked.connect(self.process_stock_barcode)
        barcode_panel.addWidget(QLabel("<b>Barkod İşlemi:</b>"))
        barcode_panel.addWidget(self.stk_barcode_mode)
        barcode_panel.addWidget(self.stk_barcode_input, 1)
        barcode_panel.addWidget(self.btn_stk_barcode)
        l_stk.addLayout(barcode_panel)
        
        h_stk = QHBoxLayout()
        self.stk_barkod = QLineEdit()
        self.stk_barkod.setPlaceholderText("Barkod (opsiyonel)")
        self.stk_ad = QLineEdit()
        self.stk_ad.setPlaceholderText("Parça Adı (Örn: Ekran)")
        self.stk_ad.textEdited.connect(lambda text, w=self.stk_ad: self.force_uppercase(w, text))
        
        self.stk_alis = QLineEdit()
        self.stk_alis.setPlaceholderText("Alış Fiyatı")
        
        self.stk_birim = QComboBox()
        self.stk_birim.addItems(["₺", "$"])
        
        self.stk_kar = QLineEdit()
        self.stk_kar.setPlaceholderText("Kar (%)")
        
        self.stk_satis = QLineEdit()
        self.stk_satis.setPlaceholderText("Satış Fiyatı")
        
        self.stk_adet = QLineEdit()
        self.stk_adet.setPlaceholderText("Adet")
        
        self.b_stk = QPushButton("Ekle")
        self.b_stk.clicked.connect(self.add_stok)
        
        self.stk_alis.textChanged.connect(self.hesapla_stok_satis)
        self.stk_kar.textChanged.connect(self.hesapla_stok_satis)
        
        h_stk.addWidget(self.stk_barkod)
        h_stk.addWidget(self.stk_ad)
        h_stk.addWidget(self.stk_alis)
        h_stk.addWidget(self.stk_birim)
        h_stk.addWidget(self.stk_kar)
        h_stk.addWidget(self.stk_satis)
        h_stk.addWidget(self.stk_adet)
        h_stk.addWidget(self.b_stk)
        l_stk.addLayout(h_stk)
        
        self.table_stok = self.create_table(7)
        l_stk.addWidget(self.table_stok)

        # --- TOPTANCI TAB ---
        l5 = QVBoxLayout(self.tab_whl)
        h5 = QHBoxLayout()
        self.firm_in = QLineEdit()
        self.firm_in.setPlaceholderText("Firma Adı...")
        
        self.b_f = QPushButton("Ekle")
        self.b_f.clicked.connect(self.add_wholesaler)
        
        h5.addWidget(self.firm_in)
        h5.addWidget(self.b_f)
        l5.addLayout(h5)
        whl_filter = QHBoxLayout()
        self.whl_date_start = QDateEdit()
        self.setup_calendar_date_edit(self.whl_date_start)
        self.whl_date_start.setDate(QDate.currentDate().addMonths(-1))
        self.whl_date_end = QDateEdit()
        self.setup_calendar_date_edit(self.whl_date_end)
        self.whl_date_end.setDate(QDate.currentDate())
        self.whl_date_start.dateChanged.connect(self.load_wholesalers)
        self.whl_date_end.dateChanged.connect(self.load_wholesalers)
        self.btn_whl_date_apply = QPushButton("Tarih Aralığını Uygula")
        self.btn_whl_date_apply.clicked.connect(self.load_wholesalers)
        whl_filter.addWidget(QLabel("Başlangıç:"))
        whl_filter.addWidget(self.whl_date_start)
        whl_filter.addWidget(QLabel("📅"))
        whl_filter.addWidget(QLabel("Bitiş:"))
        whl_filter.addWidget(self.whl_date_end)
        whl_filter.addWidget(QLabel("📅"))
        whl_filter.addWidget(self.btn_whl_date_apply)
        whl_filter.addStretch()
        l5.addLayout(whl_filter)
        
        self.w_tabs = QTabWidget()
        l5.addWidget(self.w_tabs)

        # --- DÖVİZ TAB ---
        l_cur = QVBoxLayout(self.tab_cur)
        l_cur.setAlignment(Qt.AlignmentFlag.AlignTop)
        l_cur.setSpacing(10)
        grid = QGridLayout()
        
        grid.addWidget(QLabel("<b>Dolar ($):</b>"), 0,0)
        self.u_in = QLineEdit()
        self.u_in.textChanged.connect(lambda t: self.live_calc(t, self.usd_rate, self.u_out))
        grid.addWidget(self.u_in, 0,1)
        self.u_out = QLabel("0 ₺")
        grid.addWidget(self.u_out, 0,2)
        
        grid.addWidget(QLabel("<b>Euro (€):</b>"), 1,0)
        self.e_in = QLineEdit()
        self.e_in.textChanged.connect(lambda t: self.live_calc(t, self.eur_rate, self.e_out))
        grid.addWidget(self.e_in, 1,1)
        self.e_out = QLabel("0 ₺")
        grid.addWidget(self.e_out, 1,2)
        
        grid.addWidget(QLabel("<hr>"), 2, 0, 1, 3)
        grid.addWidget(QLabel("<b>TL'den Dolara:</b>"), 3,0)
        self.t_in = QLineEdit()
        self.t_in.textChanged.connect(lambda t: self.live_calc_rev(t, self.usd_rate, self.t_out))
        grid.addWidget(self.t_in, 3,1)
        self.t_out = QLabel("0 $")
        grid.addWidget(self.t_out, 3,2)
        
        self.lbl_cur_title = QLabel("<h2>Döviz</h2>")
        self.lbl_cur_desc = QLabel("")
        l_cur.addWidget(self.lbl_cur_title)
        l_cur.addWidget(self.lbl_cur_desc)
        l_cur.addLayout(grid)
        l_cur.addStretch()

        # --- ÇÖP KUTUSU TAB ---
        l_trash = QVBoxLayout(self.tab_trash)
        self.lbl_trash_title = QLabel("<h2>🗑️ Çöp Kutusu (Son 30 Gün)</h2>")
        self.lbl_trash_desc = QLabel("Silinen veriler burada 30 gün boyunca saklanır.")
        self.lbl_trash_desc.setStyleSheet("color: #aaaaaa; margin-bottom: 10px;")
        l_trash.addWidget(self.lbl_trash_title)
        l_trash.addWidget(self.lbl_trash_desc)
        
        self.table_trash = self.create_table(5)
        l_trash.addWidget(self.table_trash)

        # --- AYARLAR TAB ---
        l_set_outer = QVBoxLayout(self.tab_set)
        self.tab_set.setStyleSheet("background-color: #111318;")
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.settings_content = QWidget()
        self.settings_content.setObjectName("SettingsContent")
        l_set = QVBoxLayout(self.settings_content)
        l_set.setAlignment(Qt.AlignmentFlag.AlignTop)
        l_set.setSpacing(10)
        l_set.setContentsMargins(10, 10, 10, 10)
        self.settings_scroll.setWidget(self.settings_content)
        l_set_outer.addWidget(self.settings_scroll)
        
        self.theme_cb = QComboBox()
        self.theme_cb.addItems(self.theme_combo_labels())
        current_theme = str(self.user_setting_value("theme", "Dark"))
        theme_index = 1 if current_theme == "Light" else 2 if current_theme == "Ocean" else 3 if current_theme == "Emerald" else 4 if current_theme == "Graphite" else 0
        self.theme_cb.setCurrentIndex(theme_index)
        self.theme_cb.currentTextChanged.connect(self.change_theme)
        
        self.lang_cb = QComboBox()
        self.lang_cb.addItems(["Türkçe", "English"])
        self.lang_cb.setCurrentText(self.current_language())
        self.lang_cb.currentTextChanged.connect(self.change_lang)
        
        self.scale_cb = QComboBox()
        self.scale_cb.addItems(["100%", "125%", "150%", "175%", "200%"])
        self.scale_cb.setCurrentText(str(self.user_setting_value("ui_scale", "100%")))
        self.scale_cb.currentTextChanged.connect(self.change_scale)
        
        self.font_weight_cb = QComboBox()
        self.font_weight_cb.addItems(self.font_weight_combo_labels())
        saved_font_weight = str(self.user_setting_value("font_weight", "Normal"))
        self.font_weight_cb.setCurrentIndex(1 if ("Bold" in saved_font_weight or "Kal" in saved_font_weight) else 0)
        self.font_weight_cb.currentTextChanged.connect(self.change_font_weight)
        
        self.print_format_cb = QComboBox()
        receipt_formats = self.receipt_format_combo_labels()
        self.print_format_cb.addItems(receipt_formats)
        saved_print_format = str(self.user_setting_value("print_format", receipt_formats[0]))
        if "Basit" in saved_print_format or "Simple" in saved_print_format:
            self.set_user_setting("receipt_simple_style", "true")
            saved_print_format = receipt_formats[0]
        if "88mm" in saved_print_format:
            saved_print_format = receipt_formats[0]
        elif "56mm" in saved_print_format or "58mm" in saved_print_format:
            saved_print_format = receipt_formats[1]
        elif "A5" in saved_print_format or "Half" in saved_print_format or "Yarım" in saved_print_format or "Yarim" in saved_print_format:
            saved_print_format = receipt_formats[2]
        if saved_print_format not in receipt_formats:
            saved_print_format = receipt_formats[0]
            self.set_user_setting("print_format", saved_print_format)
        self.print_format_cb.setCurrentText(saved_print_format)
        self.print_format_cb.currentTextChanged.connect(lambda txt: self.set_user_setting("print_format", txt))
        for settings_widget in [self.theme_cb, self.lang_cb, self.scale_cb, self.font_weight_cb, self.print_format_cb]:
            settings_widget.setMinimumHeight(34)

        self.receipt_simple_cb = QCheckBox(self.get_trans("Use simple receipt design", "Basit fiş tasarımını kullan"))
        self.receipt_simple_cb.setChecked(str(self.user_setting_value("receipt_simple_style", "false")) == "true")
        self.receipt_simple_cb.toggled.connect(lambda checked: self.set_user_setting("receipt_simple_style", "true" if checked else "false"))

        self.record_start_help = QLabel(self.get_trans(
            "If you are moving from another program, enter the last record number used there. Example: entering 4000 makes the next record MF-2026-004001.",
            "Başka programdan geçişte eski programdaki son kayıt numarasını yazın. Örn: 4000 yazılırsa bir sonraki kayıt MF-2026-004001 olur."
        ))
        self.record_start_help.setWordWrap(True)
        self.record_start_help.setStyleSheet("color:#94a3b8; font-size:12px;")
        self.record_start_in = QLineEdit(str(self.user_setting_value("record_start_sequence", "") or ""))
        self.record_start_in.setPlaceholderText(self.get_trans("Last used record no: 4000", "Son kullanılan kayıt no: 4000"))
        self.btn_record_start_save = QPushButton(self.get_trans("Continue After This Number", "Bu Numaradan Sonra Devam Et"))
        self.btn_record_start_save.clicked.connect(self.save_record_number_start)
        self.record_start_row = QHBoxLayout()
        self.record_start_row.addWidget(self.record_start_in, 2)
        self.record_start_row.addWidget(self.btn_record_start_save, 1)

        self.receipt_qr_cb = QCheckBox(self.get_trans("Show customer tracking QR on receipt", "Fişte müşteri takip QR göster"))
        self.receipt_qr_cb.setChecked(str(self.user_setting_value("receipt_status_qr", "true")) == "true")
        self.receipt_qr_cb.toggled.connect(lambda checked: self.set_user_setting("receipt_status_qr", "true" if checked else "false"))
        
        self.tray_cb = QCheckBox("Kapatıldığında simge durumuna küçülsün")
        self.tray_cb.setChecked(self.user_setting_value("close_to_tray", "false") == "true")
        self.tray_cb.toggled.connect(self.save_tray_setting)

        self.whl_cash_cb = QCheckBox(self.get_trans("Deduct supplier payments from cash", "Toptancı ödemeleri kasadan düşsün"))
        self.whl_cash_cb.setChecked(self.user_setting_value("wholesaler_payments_affect_cash", "false") == "true")
        self.whl_cash_cb.toggled.connect(self.save_wholesaler_cash_setting)

        self.finance_visible_cb = QCheckBox(self.get_trans("Show income/cash cards on dashboard", "Ana panelde kazanç/kasa kutularını göster"))
        self.finance_visible_cb.setChecked(self.user_setting_value("show_finance_dashboard", "false") == "true")
        self.finance_visible_cb.toggled.connect(self.toggle_finance_dashboard_setting)
        self.btn_finance_password = QPushButton("Kazanç Şifresini Değiştir")
        self.btn_finance_password.clicked.connect(self.change_finance_dashboard_password)
        self.btn_finance_password_reset = QPushButton("Kazanç Şifremi Unuttum")
        self.btn_finance_password_reset.setObjectName("SecondaryBtn")
        self.btn_finance_password_reset.clicked.connect(self.reset_finance_dashboard_password)
        
        self.startup_cb = QCheckBox("Bilgisayar açıldığında otomatik başlat")
        self.startup_cb.setChecked(self.user_setting_value("autostart", "false") == "true")
        self.apply_autostart_registry(self.startup_cb.isChecked(), show_errors=False)
        self.startup_cb.toggled.connect(self.toggle_autostart)
        
        self.btn_logo = QPushButton("Dükkan Logosunu Değiştir")
        self.btn_logo.clicked.connect(self.change_logo)
        self.shop_name_in = QLineEdit(self.receipt_shop_name)
        self.shop_name_in.setPlaceholderText(self.get_trans("Shop name on receipt", "Fişte görünecek bayi adı"))
        self.shop_address_in = QLineEdit(self.receipt_shop_address)
        self.shop_address_in.setPlaceholderText(self.get_trans("Address on receipt", "Fişte görünecek adres"))
        self.btn_shop_save = QPushButton(self.get_trans("Save Shop Details", "Bayi Bilgilerini Kaydet"))
        self.btn_shop_save.clicked.connect(self.save_shop_profile)
        for settings_widget in [self.shop_name_in, self.shop_address_in, self.btn_shop_save, self.btn_logo, self.record_start_in, self.btn_record_start_save]:
            settings_widget.setMinimumHeight(34)
        
        self.lbl_set_theme = QLabel(self.get_trans("UI Theme:", "Arayüz Teması:"))
        self.lbl_set_lang = QLabel(self.get_trans("System Language:", "Sistem Dili:"))
        self.lbl_ui_scale = QLabel(self.get_trans("UI Scale (Requires Restart):", "Arayüz Boyutu (Yeniden Başlatma Gerektirir):"))
        self.lbl_font_weight = QLabel(self.get_trans("Font Weight (Requires Restart):", "Yazı Kalınlığı (Yeniden Başlatma Gerektirir):"))
        self.lbl_print_format = QLabel(self.get_trans("<b>🖨️ Printer Output Format:</b>", "<b>🖨️ Yazıcı Çıktı Formatı:</b>"))
        self.lbl_record_start_title = QLabel(self.get_trans("<b>🔢 Record Number Start:</b>", "<b>🔢 Kayıt No Geçiş Ayarı:</b>"))
        self.lbl_receipt_shop_title = QLabel(self.get_trans("<b>🏪 Receipt Shop Details:</b>", "<b>🏪 Fiş Bayi Bilgileri:</b>"))
        self.lbl_wholesaler_cash_title = QLabel(self.get_trans("<b>🏭 Supplier / Cash Settings:</b>", "<b>🏭 Toptancı / Kasa Ayarı:</b>"))
        
        l_set.addWidget(self.lbl_set_theme)
        l_set.addWidget(self.theme_cb)
        l_set.addWidget(self.lbl_set_lang)
        l_set.addWidget(self.lang_cb)
        l_set.addWidget(self.lbl_ui_scale)
        l_set.addWidget(self.scale_cb)
        l_set.addWidget(self.lbl_font_weight)
        l_set.addWidget(self.font_weight_cb)
        l_set.addWidget(self.lbl_print_format)
        l_set.addWidget(self.print_format_cb)
        l_set.addWidget(self.receipt_simple_cb)
        l_set.addWidget(self.receipt_qr_cb)
        l_set.addWidget(self.lbl_record_start_title)
        l_set.addWidget(self.record_start_help)
        l_set.addLayout(self.record_start_row)
        l_set.addWidget(self.lbl_receipt_shop_title)
        l_set.addWidget(self.shop_name_in)
        l_set.addWidget(self.shop_address_in)
        l_set.addWidget(self.btn_shop_save)
        l_set.addWidget(self.btn_logo)
        l_set.addWidget(self.lbl_wholesaler_cash_title)
        l_set.addWidget(self.whl_cash_cb)
        l_set.addWidget(self.finance_visible_cb)
        l_set.addWidget(self.btn_finance_password)
        l_set.addWidget(self.btn_finance_password_reset)
        l_set.addWidget(self.tray_cb)
        l_set.addWidget(self.startup_cb)
        self.apply_settings_panel_style()

        # --- LİSANS VE HAKKINDA ---
        l_lic = QVBoxLayout(self.tab_lic)
        l_lic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.lbl_lic_text = QLabel()
        l_lic.addWidget(self.lbl_lic_text, alignment=Qt.AlignmentFlag.AlignCenter)
        
        self.btn_renew = QPushButton("Lisans Yenile (Online / WhatsApp)")
        self.btn_renew.setStyleSheet("background:#2ecc71; padding: 15px; font-size:14px;")
        self.btn_renew.clicked.connect(lambda: webbrowser.open("https://wa.me/905357309054?text=Lisans%20yenilemek%20istiyorum"))
        
        self.btn_logout = QPushButton("Sistemden Çıkış Yap")
        self.btn_logout.setStyleSheet("background:#ef4444; padding: 10px; font-size:14px; margin-top: 20px;")
        self.btn_logout.clicked.connect(self.logout_user)
        
        l_lic.addWidget(self.btn_renew, alignment=Qt.AlignmentFlag.AlignCenter)
        l_lic.addWidget(self.btn_logout, alignment=Qt.AlignmentFlag.AlignCenter)
        
        l_abt = QVBoxLayout(self.tab_about)
        l_abt.setAlignment(Qt.AlignmentFlag.AlignCenter)

        about_card = QWidget()
        about_card.setObjectName("AboutBrandCard")
        about_card.setStyleSheet("""
            QWidget#AboutBrandCard {
                background: rgba(37, 99, 235, 0.08);
                border: 1px solid rgba(96, 165, 250, 0.35);
                border-radius: 12px;
            }
        """)
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(36, 28, 36, 28)
        about_layout.setSpacing(14)

        about_icon = QLabel()
        pix_about_icon = QPixmap(resource_path("metafold.ico"))
        if not pix_about_icon.isNull():
            about_icon.setPixmap(pix_about_icon.scaled(76, 76, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        about_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_banner = QLabel()
        pix_about_banner = QPixmap(resource_path("banner.png"))
        if pix_about_banner.isNull():
            pix_about_banner = QPixmap(resource_path("metafold_banner.png"))
        if not pix_about_banner.isNull():
            about_banner.setPixmap(pix_about_banner.scaled(300, 86, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        about_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(about_icon)
        about_layout.addWidget(about_banner)

        about_text = QLabel(
            f"<div style='text-align:center;'>"
            f"<h1 style='color:#3584e4; margin:8px 0;'>MetaFold ERP Sistemleri</h1>"
            f"<p style='font-size:14px; line-height:1.45;'>"
            f"<b>Teknik Servis Yönetim Merkezi</b><br>"
            f"<b>Geliştirici:</b> Ahmet Doğan<br>"
            f"<b>Sürüm:</b> v{MEVCUT_SURUM}<br><br>"
            f"<a href='http://www.metafold.net' style='color:#3498db; text-decoration:none; font-size:16px;'><b>www.metafold.net</b></a><br><br>"
            f"<a href='https://www.metafold.com.tr' style='color:#3498db; text-decoration:none; font-size:16px;'><b>www.metafold.com.tr</b></a><br><br>"
            f"Telif Hakkı © 2026"
            f"</p></div>"
        )
        about_text.setOpenExternalLinks(True)
        about_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        about_layout.addWidget(about_text)
        l_abt.addWidget(about_card, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- YÖNETİM / YEDEK / RAPOR ---
        l_admin_root = QVBoxLayout(self.tab_admin)
        l_admin_root.setContentsMargins(0, 0, 0, 0)
        self.admin_scroll = QScrollArea()
        self.admin_scroll.setWidgetResizable(True)
        self.admin_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.admin_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.admin_content = QWidget()
        self.admin_content.setObjectName("AdminContent")
        l_admin = QVBoxLayout(self.admin_content)
        l_admin.setSpacing(10)
        l_admin.setContentsMargins(12, 12, 12, 12)
        self.lbl_sync_status = QLabel("Senkron durumu: Hazır")
        self.lbl_sync_status.setStyleSheet("font-weight:bold; color:#38bdf8; padding:6px;")
        l_admin.addWidget(QLabel("<h2>Yönetim Merkezi</h2>"))
        l_admin.addWidget(self.lbl_sync_status)

        backup_box = QGroupBox("Yedekleme")
        backup_lay = QHBoxLayout(backup_box)
        self.auto_backup_cb = QCheckBox("Günlük otomatik yedek al")
        self.auto_backup_cb.setChecked(str(self.user_setting_value("auto_backup_enabled", "true")) == "true")
        self.auto_backup_cb.toggled.connect(lambda checked: self.set_user_setting("auto_backup_enabled", "true" if checked else "false"))
        self.btn_backup_now = QPushButton("Şimdi Yedek Al")
        self.btn_backup_now.clicked.connect(self.export_backup_zip)
        backup_lay.addWidget(self.auto_backup_cb)
        backup_lay.addStretch()
        backup_lay.addWidget(self.btn_backup_now)
        l_admin.addWidget(backup_box)

        warranty_box = QGroupBox("Garanti Varsayılanı")
        warranty_lay = QHBoxLayout(warranty_box)
        self.default_warranty_in = QLineEdit()
        self.default_warranty_in.setPlaceholderText("Varsayılan garanti günü")
        self.default_warranty_in.setText(str(self.user_setting_value("default_warranty_days", "30")))
        btn_warranty_save = QPushButton("Garanti Ayarını Kaydet")
        btn_warranty_save.clicked.connect(self.save_default_warranty_days)
        warranty_lay.addWidget(QLabel("Gün:"))
        warranty_lay.addWidget(self.default_warranty_in)
        warranty_lay.addWidget(btn_warranty_save)
        l_admin.addWidget(warranty_box)

        report_box = QGroupBox("Hızlı Rapor")
        report_lay = QVBoxLayout(report_box)
        self.lbl_management_report = QLabel("")
        self.lbl_management_report.setWordWrap(True)
        report_btn_row = QHBoxLayout()
        btn_daily_report = QPushButton("Günlük Rapor")
        btn_daily_report.clicked.connect(self.show_daily_service_report)
        btn_warranty_center = QPushButton("Garanti Takibi")
        btn_warranty_center.clicked.connect(self.show_warranty_center)
        btn_low_stock = QPushButton("Stok Uyarıları")
        btn_low_stock.clicked.connect(self.show_low_stock_center)
        btn_audit_log = QPushButton("Denetim Logları")
        btn_audit_log.clicked.connect(self.show_audit_log_dialog)
        btn_priorities = QPushButton("Öncelikler")
        btn_priorities.clicked.connect(self.show_management_priorities)
        btn_smart_summary = QPushButton("Akıllı Özet (Deneme)")
        btn_smart_summary.clicked.connect(self.show_smart_management_summary)
        btn_report_refresh = QPushButton("Raporu Yenile")
        btn_report_refresh.clicked.connect(self.update_management_report)
        report_lay.addWidget(self.lbl_management_report)
        report_btn_row.addWidget(btn_daily_report)
        report_btn_row.addWidget(btn_warranty_center)
        report_btn_row.addWidget(btn_low_stock)
        report_btn_row.addWidget(btn_audit_log)
        report_btn_row.addWidget(btn_priorities)
        report_btn_row.addWidget(btn_smart_summary)
        report_lay.addLayout(report_btn_row)
        report_lay.addWidget(btn_report_refresh)
        l_admin.addWidget(report_box)

        staff_box = QGroupBox("Personel / Yetki Başlangıcı")
        staff_lay = QVBoxLayout(staff_box)
        self.staff_enabled_cb = QCheckBox("Personel PIN sistemi aktif")
        self.staff_enabled_cb.setChecked(self.staff_pin_enabled() or bool(self.staff_accounts()))
        self.staff_enabled_cb.toggled.connect(self.toggle_staff_pin_enabled)
        self.staff_status_label = QLabel("")
        self.staff_status_label.setStyleSheet("font-weight:bold; color:#38bdf8;")
        self.staff_count_label = QLabel("Toplam personel: 0")
        self.staff_count_label.setStyleSheet("font-weight:bold; color:#22c55e;")
        staff_info = QLabel("Rol seçimi varsayılan yetkileri doldurur. Aşağıdaki checklist ile her personelin görebileceği ekranları ve yapabileceği işlemleri tek tek belirleyebilirsiniz.")
        staff_info.setWordWrap(True)
        self.staff_list = QListWidget()
        self.staff_list.setMaximumHeight(120)
        self.staff_list.itemClicked.connect(self.load_staff_form_from_item)
        staff_form = QHBoxLayout()
        self.staff_name_in = QLineEdit()
        self.staff_name_in.setPlaceholderText("Personel adı")
        self.staff_name_in.textEdited.connect(lambda text, w=self.staff_name_in: self.force_uppercase(w, text))
        self.staff_role_in = QComboBox()
        self.staff_role_in.addItems(self.staff_roles())
        self.staff_role_in.currentTextChanged.connect(self.apply_staff_role_defaults_to_checks)
        self.staff_pin_in = QLineEdit()
        self.staff_pin_in.setPlaceholderText("PIN")
        self.staff_pin_in.setEchoMode(QLineEdit.EchoMode.Password)
        self.staff_pin_in.setMaxLength(12)
        btn_staff_new = QPushButton("+ Yeni Personel")
        btn_staff_new.clicked.connect(self.clear_staff_form_for_new_account)
        btn_staff_save = QPushButton("Personel Kaydet")
        btn_staff_save.clicked.connect(self.save_staff_account_from_form)
        btn_staff_photo = QPushButton("Seçili Fotoğraf Değiştir")
        btn_staff_photo.clicked.connect(self.change_selected_staff_photo)
        btn_staff_pin = QPushButton("Seçili PIN Değiştir")
        btn_staff_pin.clicked.connect(self.change_selected_staff_pin)
        self.btn_staff_delete = QPushButton("Seçili Personeli Sil")
        self.btn_staff_delete.clicked.connect(self.delete_selected_staff_account)
        self.btn_staff_delete.setStyleSheet("""
            QPushButton {
                background-color: #ef4444;
                color: #ffffff;
                border: 1px solid rgba(255,255,255,0.18);
                border-radius: 7px;
                padding: 7px 12px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: #dc2626;
                border-color: rgba(255,255,255,0.32);
            }
            QPushButton:disabled {
                background-color: rgba(148, 163, 184, 0.16);
                color: rgba(226, 232, 240, 0.38);
                border: 1px solid rgba(148, 163, 184, 0.14);
            }
        """)
        btn_staff_switch = QPushButton("Personel Girişi Değiştir")
        btn_staff_switch.clicked.connect(lambda: self.show_staff_gate(force=True))
        staff_form.addWidget(self.staff_name_in, 2)
        staff_form.addWidget(self.staff_role_in, 2)
        staff_form.addWidget(self.staff_pin_in, 1)
        staff_form.addWidget(btn_staff_new)
        staff_form.addWidget(btn_staff_save)
        staff_form.addWidget(btn_staff_photo)
        staff_form.addWidget(btn_staff_pin)
        staff_form.addWidget(self.btn_staff_delete)
        staff_lay.addWidget(staff_info)
        staff_lay.addWidget(self.staff_enabled_cb)
        staff_lay.addWidget(self.staff_status_label)
        staff_lay.addWidget(self.staff_count_label)
        staff_lay.addWidget(self.staff_list)
        staff_lay.addLayout(staff_form)
        perm_box = QGroupBox("Kişiye Özel Yetkiler")
        perm_box.setObjectName("StaffPermissionBox")
        perm_grid = QGridLayout(perm_box)
        perm_grid.setHorizontalSpacing(12)
        perm_grid.setVerticalSpacing(12)
        self.staff_permission_checks = {}
        permission_catalog = dict(self.staff_permission_catalog())
        grouped_keys = set()
        group_index = 0
        for group_title, group_icon, group_keys in self.staff_permission_groups():
            visible_keys = [key for key in group_keys if key in permission_catalog]
            if not visible_keys:
                continue
            grouped_keys.update(visible_keys)
            group_box = QGroupBox(f"{group_icon} {group_title}")
            group_box.setObjectName("PermissionGroupBox")
            group_layout = QGridLayout(group_box)
            group_layout.setContentsMargins(10, 16, 10, 10)
            group_layout.setHorizontalSpacing(10)
            group_layout.setVerticalSpacing(6)
            for idx, key in enumerate(visible_keys):
                label = permission_catalog[key]
                cb = QCheckBox(label)
                cb.setToolTip(label)
                self.staff_permission_checks[key] = cb
                group_layout.addWidget(cb, idx // 2, idx % 2)
            perm_grid.addWidget(group_box, group_index // 2, group_index % 2)
            group_index += 1
        remaining_permissions = [(key, label) for key, label in self.staff_permission_catalog() if key not in grouped_keys]
        if remaining_permissions:
            group_box = QGroupBox("Diğer")
            group_box.setObjectName("PermissionGroupBox")
            group_layout = QGridLayout(group_box)
            group_layout.setContentsMargins(10, 16, 10, 10)
            group_layout.setHorizontalSpacing(10)
            group_layout.setVerticalSpacing(6)
            for idx, (key, label) in enumerate(remaining_permissions):
                cb = QCheckBox(label)
                cb.setToolTip(label)
                self.staff_permission_checks[key] = cb
                group_layout.addWidget(cb, idx // 2, idx % 2)
            perm_grid.addWidget(group_box, group_index // 2, group_index % 2)
        perm_box.setStyleSheet("""
            QGroupBox#StaffPermissionBox {
                border: 1px solid rgba(96, 165, 250, 0.25);
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 10px;
            }
            QGroupBox#StaffPermissionBox::title {
                color: #e5e7eb;
                font-weight: 800;
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QGroupBox#PermissionGroupBox {
                background: rgba(15, 23, 42, 0.36);
                border: 1px solid rgba(148, 163, 184, 0.18);
                border-radius: 8px;
                margin-top: 10px;
            }
            QGroupBox#PermissionGroupBox::title {
                color: #60a5fa;
                font-weight: 800;
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }
        """)
        self.apply_staff_role_defaults_to_checks(self.staff_role_in.currentText())
        staff_lay.addWidget(perm_box)
        staff_lay.addWidget(btn_staff_switch)
        l_admin.addWidget(staff_box)
        self.refresh_staff_list()
        self.clear_staff_form_for_new_account()

        template_box = QGroupBox("WhatsApp Mesaj Şablonları")
        template_lay = QVBoxLayout(template_box)
        self.tpl_ready = QTextEdit()
        self.tpl_ready.setMinimumHeight(92)
        self.tpl_ready.setPlaceholderText("Cihaz hazır mesajı")
        self.tpl_waiting = QTextEdit()
        self.tpl_waiting.setMinimumHeight(92)
        self.tpl_waiting.setPlaceholderText("Genel bilgilendirme mesajı")
        self.tpl_part = QTextEdit()
        self.tpl_part.setMinimumHeight(92)
        self.tpl_part.setPlaceholderText("Parça bekliyor mesajı")
        self.tpl_ready.setPlainText(self.user_setting_value("tpl_ready", "Merhaba {musteri}, {cihaz} cihazınızın işlemleri tamamlanmıştır. {firma}"))
        self.tpl_waiting.setPlainText(self.user_setting_value("tpl_waiting", "Merhaba {musteri}, {firma} firmasından ulaşıyorum. {cihaz} cihazınız hakkında bilgilendirme:"))
        self.tpl_part.setPlainText(self.user_setting_value("tpl_part", "Merhaba {musteri}, {cihaz} cihazınız için parça beklenmektedir. {firma}"))
        btn_tpl_save = QPushButton("Şablonları Kaydet")
        btn_tpl_save.clicked.connect(self.save_message_templates)
        template_lay.addWidget(QLabel("Hazır / Tamamlandı:"))
        template_lay.addWidget(self.tpl_ready)
        template_lay.addWidget(QLabel("Genel Bilgilendirme:"))
        template_lay.addWidget(self.tpl_waiting)
        template_lay.addWidget(QLabel("Parça Bekliyor:"))
        template_lay.addWidget(self.tpl_part)
        template_lay.addWidget(btn_tpl_save)
        l_admin.addWidget(template_box)
        l_admin.addStretch()
        self.admin_scroll.setWidget(self.admin_content)
        l_admin_root.addWidget(self.admin_scroll)
        self.apply_admin_panel_style()
        self.setup_global_uppercase_inputs()

    def setup_global_uppercase_inputs(self):
        excluded = {getattr(self, "f_sifre", None)}
        for widget in self.findChildren(QLineEdit):
            if widget in excluded or widget.property("allow_lowercase"):
                continue
            widget.textEdited.connect(lambda text, w=widget: self.force_uppercase(w, text))
        for widget in self.findChildren(QTextEdit):
            widget.textChanged.connect(lambda w=widget: self.force_uppercase_textedit(w))

    def update_user_logo_label(self):
        self.update_sidebar_logo_label()
        if not hasattr(self, "user_logo_label"):
            return
        logo_path = str(getattr(self, "session_custom_logo", "") or "")
        if not logo_path or not os.path.exists(logo_path):
            self.user_logo_label.clear()
            self.user_logo_label.setVisible(False)
            return
        pix = QPixmap(logo_path)
        if pix.isNull():
            self.user_logo_label.clear()
            self.user_logo_label.setVisible(False)
            self.update_sidebar_logo_label()
            return
        self.user_logo_label.setVisible(True)
        self.user_logo_label.setPixmap(pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.update_sidebar_logo_label()

    def apply_settings_panel_style(self):
        if not hasattr(self, "settings_content"):
            return
        theme = str(self.user_setting_value("theme", "Dark"))
        light_mode = theme in ["Light", "Emerald"]
        bg = "#f6f8fb" if light_mode else "#111318"
        field_bg = "#ffffff" if light_mode else "#171a21"
        text = "#172033" if light_mode else "#f8fafc"
        border = "#cbd5e1" if light_mode else "#3f4652"
        scroll_handle = "#94a3b8" if light_mode else "#3f4652"
        self.tab_set.setStyleSheet(f"background-color: {bg};")
        self.settings_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {bg}; border: none; }}
            QScrollBar:vertical {{ background: {bg}; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {scroll_handle}; border-radius: 5px; min-height: 28px; }}
        """)
        self.settings_content.setStyleSheet(f"""
            QWidget#SettingsContent {{ background-color: {bg}; }}
            QWidget#SettingsContent QLabel,
            QWidget#SettingsContent QCheckBox {{
                color: {text};
                font-weight: 700;
            }}
            QWidget#SettingsContent QLineEdit,
            QWidget#SettingsContent QComboBox {{
                background-color: {field_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 7px 10px;
                selection-background-color: #2563eb;
            }}
            QWidget#SettingsContent QLineEdit:focus,
            QWidget#SettingsContent QComboBox:focus {{
                border: 2px solid #60a5fa;
                padding: 6px 9px;
            }}
            QWidget#SettingsContent QComboBox QAbstractItemView {{
                background-color: {field_bg};
                color: {text};
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }}
            QWidget#SettingsContent QPushButton {{
                min-height: 34px;
                color: #ffffff;
                background-color: #2563eb;
                border-radius: 7px;
                font-weight: 700;
            }}
            QWidget#SettingsContent QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {border};
                border-radius: 4px;
                background: {field_bg};
            }}
            QWidget#SettingsContent QCheckBox::indicator:checked {{
                background: #2563eb;
                border-color: #60a5fa;
            }}
        """)

    def apply_admin_panel_style(self):
        if not hasattr(self, "admin_content"):
            return
        theme = str(self.user_setting_value("theme", "Dark"))
        light_mode = theme in ["Light", "Emerald"]
        if light_mode:
            bg = "#f6f8fb"
            card_bg = "#ffffff"
            field_bg = "#ffffff"
            text = "#172033"
            muted = "#475569"
            border = "#cbd5e1"
            scroll_handle = "#94a3b8"
        else:
            bg = "#0f1117"
            card_bg = "#171a21"
            field_bg = "#111318"
            text = "#f8fafc"
            muted = "#cbd5e1"
            border = "#3f4652"
            scroll_handle = "#3f4652"
        self.tab_admin.setStyleSheet(f"background-color: {bg};")
        self.admin_scroll.viewport().setStyleSheet(f"background-color: {bg};")
        self.admin_scroll.setStyleSheet(f"""
            QScrollArea {{ background: {bg}; border: none; }}
            QScrollArea QWidget {{ background: {bg}; }}
            QScrollBar:vertical {{ background: {bg}; width: 10px; }}
            QScrollBar::handle:vertical {{ background: {scroll_handle}; border-radius: 5px; min-height: 28px; }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                background: {bg};
                height: 0px;
            }}
        """)
        self.admin_content.setStyleSheet(f"""
            QWidget#AdminContent {{
                background-color: {bg};
            }}
            QWidget#AdminContent QLabel {{
                color: {text};
                background: transparent;
            }}
            QWidget#AdminContent QGroupBox {{
                background-color: {card_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 8px;
                margin-top: 12px;
                padding: 10px;
                font-weight: 700;
            }}
            QWidget#AdminContent QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: {muted};
                background: {bg};
            }}
            QWidget#AdminContent QTextEdit,
            QWidget#AdminContent QLineEdit {{
                background-color: {field_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 7px 10px;
                selection-background-color: #2563eb;
            }}
            QWidget#AdminContent QTextEdit:focus,
            QWidget#AdminContent QLineEdit:focus {{
                border: 2px solid #60a5fa;
                padding: 6px 9px;
            }}
            QWidget#AdminContent QPushButton {{
                min-height: 34px;
                color: #ffffff;
                background-color: #2563eb;
                border-radius: 7px;
                font-weight: 700;
                padding: 6px 12px;
            }}
            QWidget#AdminContent QCheckBox {{
                color: {text};
                font-weight: 700;
            }}
            QWidget#AdminContent QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1px solid {border};
                border-radius: 4px;
                background: {field_bg};
            }}
            QWidget#AdminContent QCheckBox::indicator:checked {{
                background: #2563eb;
                border-color: #60a5fa;
            }}
        """)

    def filter_musteri_listesi(self, text):
        for i in range(self.list_musteriler.count()):
            item = self.list_musteriler.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def filter_bayi_listesi(self, text):
        for i in range(self.list_bayiler.count()):
            item = self.list_bayiler.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def open_musteri_list_menu(self, pos):
        item = self.list_musteriler.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        show_action = menu.addAction("💎 Akıllı Müşteri Kartı")
        delete_action = menu.addAction("🗑️ Müşteriyi Sil (Çöp Kutusuna Taşı)")
        action = menu.exec(self.list_musteriler.mapToGlobal(pos))
        if action == show_action:
            self.list_musteriler.setCurrentItem(item)
            self.load_musteri_cihaz_gecmisi(item)
            self.show_customer_detail(item)
        elif action == delete_action:
            self.delete_customer_from_list(item)

    def customer_records_for_name(self, customer_name):
        target = self.normalize_upper(customer_name)
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        records = []
        for rec_id, rec in data.items():
            if not isinstance(rec, dict) or self.is_bayi_record(rec):
                continue
            if self.normalize_upper(rec.get("m", "")) == target:
                records.append((rec_id, rec))
        return records

    def customer_identity_key(self, rec_id, record):
        if not isinstance(record, dict):
            return ""
        phone = "".join(filter(str.isdigit, str(record.get("t", ""))))[-10:]
        if phone:
            return f"PHONE-{phone}"
        saved_key = str(record.get("customer_key", "") or "").strip()
        if saved_key:
            return saved_key
        name = self.normalize_upper(record.get("m", "")).strip()
        if name:
            return f"LEGACY-NAME-{name}"
        return f"RECORD-{rec_id}"

    def legacy_customer_key_for_record(self, rec_id, record):
        phone = "".join(filter(str.isdigit, str(record.get("t", "") if isinstance(record, dict) else "")))[-10:]
        if phone:
            return f"PHONE-{phone}"
        name = self.normalize_upper(record.get("m", "") if isinstance(record, dict) else "").strip()
        if name:
            return f"LEGACY-NAME-{name}"
        clean_id = re.sub(r"[^A-Za-z0-9]", "", str(rec_id or "")).upper()[-14:]
        if clean_id:
            return f"CUST-{clean_id}"
        return self.new_customer_key()

    def new_customer_key(self):
        return f"CUST-{uuid.uuid4().hex[:14].upper()}"

    def patch_user_paths(self, updates):
        if not updates:
            return True
        db_url = get_firebase_config().get("databaseURL", "").rstrip("/")
        url = f"{db_url}/users/{self.user_id}.json"
        for attempt in range(2):
            response = requests.patch(url, params={"auth": self.token}, json=updates, timeout=20)
            if response.status_code in [401, 402, 403] and attempt == 0 and self.refresh_firebase_token():
                continue
            response.raise_for_status()
            return True
        return False

    def migrate_legacy_customer_keys(self, data):
        # Müşteri kayıtları kritik veri olduğu için refresh sırasında Firebase'e otomatik
        # customer_key yazmıyoruz. Listeleme tarafında customer_identity_key ile güvenli
        # okuma gruplaması yapılıyor; kalıcı birleştirme ayrı ve kontrollü işlem olmalı.
        if not isinstance(data, dict):
            return data
        return data

    def customer_payload_from_item(self, item_or_customer):
        if isinstance(item_or_customer, dict):
            return item_or_customer
        if isinstance(item_or_customer, QListWidgetItem):
            data = item_or_customer.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, dict):
                return data
            return {"name": item_or_customer.text(), "key": ""}
        return {"name": str(item_or_customer or ""), "key": ""}

    def customer_records_for_identity(self, item_or_customer):
        customer = self.customer_payload_from_item(item_or_customer)
        key = str(customer.get("key", "") or "").strip()
        name = self.normalize_upper(customer.get("name", "")).strip()
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        records = []
        for rec_id, rec in data.items():
            if not isinstance(rec, dict) or self.is_bayi_record(rec):
                continue
            if key:
                if self.customer_identity_key(rec_id, rec) == key:
                    records.append((rec_id, rec))
            elif name and self.normalize_upper(rec.get("m", "")) == name:
                records.append((rec_id, rec))
        return records

    def customer_list_label(self, customer, duplicate_names=None):
        name = self.normalize_upper(customer.get("name", "")).strip()
        phone = "".join(filter(str.isdigit, str(customer.get("phone", ""))))[-10:]
        duplicate_names = duplicate_names or {}
        if duplicate_names.get(name, 0) > 1:
            return f"{name} | {phone if phone else 'TELEFON YOK'}"
        return name

    def customer_key_for_new_record(self, name, phone):
        selected_key = str(getattr(self, "selected_customer_key", "") or "").strip()
        if selected_key:
            return selected_key
        phone = "".join(filter(str.isdigit, str(phone or "")))[-10:]
        if phone:
            return f"PHONE-{phone}"
        return self.new_customer_key()

    def record_address_text(self, record):
        if not isinstance(record, dict):
            return ""
        for key in ["adres", "address", "m_adres", "musteri_adres", "musteri_adresi", "a_adres"]:
            value = str(record.get(key, "") or "").strip()
            if value:
                return value
        return ""

    def confirm_bulk_name_update(self, title, old_name, new_name, updates, scope_text):
        count = len(updates or {})
        if count <= 0:
            return True
        sample = []
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        for rec_id in list(updates.keys())[:8]:
            rec = data.get(rec_id, {})
            if isinstance(rec, dict):
                sample.append(f"- {rec.get('c_no', rec_id)} | {rec.get('ci', '-')} | {rec.get('z', '-')}")
        detail = "\n".join(sample)
        if count > len(sample):
            detail += f"\n... ve {count - len(sample)} kayıt daha"
        message = (
            f"Eski ad: {old_name}\n"
            f"Yeni ad: {new_name}\n"
            f"Kapsam: {scope_text}\n"
            f"Etkilenecek cihaz kaydı: {count}\n\n"
            f"{detail}\n\n"
            "Bu değişiklik veritabanına yazılacak. Devam edilsin mi?"
        )
        return QMessageBox.question(self, title, message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def show_customer_detail(self, customer_name):
        customer = self.customer_payload_from_item(customer_name)
        display_name = customer.get("display") or customer.get("name") or str(customer_name or "")
        records = self.customer_records_for_identity(customer)
        if not records:
            QMessageBox.information(self, "Müşteri Detayı", "Bu müşteriye ait kayıt bulunamadı.")
            return
        now = datetime.date.today()
        phones = sorted({
            "".join(filter(str.isdigit, str(rec.get("t", ""))))[-10:]
            for _, rec in records
            if str(rec.get("t", "")).strip()
        })
        addresses = sorted({self.record_address_text(rec) for _, rec in records if self.record_address_text(rec)})
        total = sum(safe_float(rec.get("masraf", "0")) for _, rec in records)
        paid = sum(safe_float(rec.get("masraf", "0")) for _, rec in records if rec.get("odeme_durumu") == "Ödendi")
        unpaid = max(0.0, total - paid)
        active = 0
        delivered = 0
        approval_waiting = 0
        warranty_active = 0
        fault_counts = {}
        first_date = None
        last_date = None
        for _, rec in records:
            delivered_ok, _ = self.is_delivered_record(rec)
            delivered += 1 if delivered_ok else 0
            active += 0 if delivered_ok else 1
            if str(rec.get("approval_status", "") or "") == "Bekliyor":
                approval_waiting += 1
            warranty_until = str(rec.get("garanti_bitis", "") or "")
            if warranty_until:
                try:
                    if datetime.datetime.strptime(warranty_until, "%d.%m.%Y").date() >= now:
                        warranty_active += 1
                except:
                    pass
            dt = self.parse_date_value(rec.get("z", ""))
            if dt != datetime.datetime.min:
                first_date = dt if first_date is None or dt < first_date else first_date
                last_date = dt if last_date is None or dt > last_date else last_date
            for fault in self.get_faults(rec):
                fault_counts[fault] = fault_counts.get(fault, 0) + 1
        top_faults = sorted(fault_counts.items(), key=lambda item: item[1], reverse=True)[:5]
        recent = sorted(records, key=lambda item: self.parse_date_value(item[1].get("z", "")), reverse=True)[:8]
        avg = total / len(records) if records else 0.0
        trust_color = "#22c55e" if unpaid == 0 else "#f59e0b" if unpaid < max(total * 0.35, 1) else "#ef4444"
        trust_text = "Temiz ödeme geçmişi" if unpaid == 0 else "Açık hesap takip edilmeli"
        p = self.dialog_html_palette()
        cell_style = f"background-color:{p['panel']}; color:{p['text']}; border:1px solid {p['border']}; padding:10px;"
        label_style = f"color:{p['muted']}; font-size:12px; font-weight:700;"
        value_style = f"color:{p['accent']}; font-size:24px; font-weight:900;"
        row_td_style = f"border:1px solid {p['border']}; padding:6px; color:{p['text']};"
        recent_rows = ""
        for rec_id, rec in recent:
            amount = safe_float(rec.get("masraf", "0"))
            recent_rows += (
                f"<tr>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('c_no', rec_id)))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('ci', '-')))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('d', '-')))}</td>"
                f"<td style='{row_td_style}'>{format_money(amount, '₺') if amount else '-'}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('z', '-')))}</td>"
                f"</tr>"
            )
        if not recent_rows:
            recent_rows = f"<tr><td style='{row_td_style}' colspan='5'>Son işlem bulunamadı.</td></tr>"
        faults_html = "<br>".join(f"{html.escape(fault)} ({count})" for fault, count in top_faults) or "Henüz arıza istatistiği yok."
        html_content = f"""
        <div style="font-family:Arial, sans-serif; color:{p['text']}; background-color:{p['bg']}; line-height:1.45;">
            <h2 style="margin:0 0 12px 0; color:{p['accent']};">Akıllı Müşteri Kartı</h2>
            <div style="{cell_style}">
                <b>Müşteri:</b> {html.escape(str(display_name))}<br>
                <b>Telefon:</b> {html.escape(', '.join(phones) if phones else 'Telefon yok')}<br>
                <b>Adres:</b> {html.escape(' | '.join(addresses) if addresses else 'Adres yok')}<br>
                <b>İlk kayıt:</b> {first_date.strftime('%d.%m.%Y') if first_date else '-'} &nbsp;
                <b>Son geliş:</b> {last_date.strftime('%d.%m.%Y %H:%M') if last_date else '-'}
            </div><br>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                    <td style="{cell_style}"><span style="{label_style}">Toplam Cihaz</span><br><span style="{value_style}">{len(records)}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">Aktif İş</span><br><span style="{value_style}">{active}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">Teslim</span><br><span style="{value_style}">{delivered}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">Onay Bekleyen</span><br><span style="{value_style}">{approval_waiting}</span></td>
                </tr>
                <tr>
                    <td style="{cell_style}"><span style="{label_style}">Toplam Hacim</span><br><b>{format_money(total, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Ödenen</span><br><b style="color:#22c55e;">{format_money(paid, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Açık Borç</span><br><b style="color:#ef4444;">{format_money(unpaid, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Ortalama İşlem</span><br><b>{format_money(avg, '₺')}</b></td>
                </tr>
            </table>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                    <td style="{cell_style}"><b>Güven Notu</b><br><span style="color:{trust_color}; font-weight:900;">{trust_text}</span></td>
                    <td style="{cell_style}"><b>Garanti Aktif</b><br>{warranty_active} cihaz</td>
                </tr>
            </table>
            <div style="{cell_style}"><b>En Sık Arızalar</b><br>{faults_html}</div><br>
            <div style="{cell_style}">
                <b>Son İşlemler</b>
                <table width="100%" cellspacing="0" cellpadding="6" style="border-collapse:collapse; margin-top:8px; color:{p['text']};">
                    <tr style="background-color:{p['header']};"><th>Kayıt</th><th>Cihaz</th><th>Durum</th><th>Ücret</th><th>Tarih</th></tr>
                    {recent_rows}
                </table>
            </div>
        </div>
        """
        dlg = ReadOnlyDialog("Akıllı Müşteri Kartı", html_content, self)
        dlg.resize(820, 680)
        dlg.exec()

    def delete_customer_from_list(self, customer_name):
        if not self.require_staff_permission("edit_people", "Müşteri silme"):
            return
        customer = self.customer_payload_from_item(customer_name)
        display_name = customer.get("display") or customer.get("name") or str(customer_name or "")
        records = self.customer_records_for_identity(customer)
        if not records:
            QMessageBox.information(self, "Müşteri Sil", "Bu müşteriye ait kayıt bulunamadı.")
            return
        phones = sorted({"".join(filter(str.isdigit, str(rec.get("t", "")))) for _, rec in records if str(rec.get("t", "")).strip()})
        selected_records = records
        if not customer.get("key") and len(phones) > 1:
            choices = [f"{phone[-10:]} ({sum(1 for _, rec in records if ''.join(filter(str.isdigit, str(rec.get('t', '')))).endswith(phone[-10:]))} kayıt)" for phone in phones]
            choice, ok = QInputDialog.getItem(self, "Müşteri Seç", "Aynı isimde birden fazla telefon bulundu. Silinecek müşteriyi seçin:", choices, 0, False)
            if not ok:
                return
            selected_phone = "".join(filter(str.isdigit, choice.split(" ")[0]))
            selected_records = [(rec_id, rec) for rec_id, rec in records if "".join(filter(str.isdigit, str(rec.get("t", "")))).endswith(selected_phone)]
        elif not customer.get("key") and not phones:
            if QMessageBox.warning(
                self,
                "Telefon Yok",
                "Bu müşteride telefon bilgisi yok. Aynı isimli müşteriler karışabilir.\n\nYine de bu isimdeki tüm kayıtları silmek istiyor musunuz?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

        count = len(selected_records)
        if QMessageBox.question(
            self,
            "Müşteriyi Sil",
            f"{display_name} için {count} cihaz kaydı çöp kutusuna taşınacak.\n\nDevam edilsin mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        moved = 0
        for rec_id, _rec in selected_records:
            if self.soft_delete("kayitlar", rec_id):
                moved += 1
        self.refresh_all_tables()
        QMessageBox.information(self, "Müşteri Silindi", f"{moved} kayıt çöp kutusuna taşındı.")

    def filter_bayi_tablosu(self, text):
        for r in range(self.table_bayi.rowCount()):
            match = False
            for c in range(self.table_bayi.columnCount()):
                it = self.table_bayi.item(r, c)
                if it and text.lower() in it.text().lower(): 
                    match = True
                    break
            self.table_bayi.setRowHidden(r, not match)

    def export_table_to_excel_csv(self, table, default_name):
        path, _ = QFileDialog.getSaveFileName(self, "Excel Tablosu Kaydet", f"{default_name}.csv", "Excel CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            headers = []
            visible_cols = []
            for c in range(table.columnCount()):
                if table.isColumnHidden(c):
                    continue
                visible_cols.append(c)
                header = table.horizontalHeaderItem(c)
                headers.append(header.text() if header else "")
            writer.writerow(headers)
            for r in range(table.rowCount()):
                if table.isRowHidden(r):
                    continue
                writer.writerow([(table.item(r, c).text() if table.item(r, c) else "") for c in visible_cols])
        QMessageBox.information(self, "Excel Dışa Aktarım", "Tablo Excel uyumlu CSV olarak kaydedildi.")

    def is_qdate_in_range(self, date_text, start_date, end_date):
        try:
            q_date = QDate.fromString(str(date_text).split(" ")[0], "dd.MM.yyyy")
            return q_date.isValid() and start_date <= q_date <= end_date
        except:
            return False

    def setup_calendar_date_edit(self, date_edit):
        calendar_style = """
            QCalendarWidget QWidget { background-color: #ffffff; color: #172033; }
            QCalendarWidget QToolButton {
                color: #172033; background: #eef3f8; border: 1px solid #c9d6e4;
                border-radius: 4px; padding: 4px; margin: 1px;
            }
            QCalendarWidget QToolButton:hover { background: #dbeafe; }
            QCalendarWidget QMenu { background: #ffffff; color: #172033; border: 1px solid #c9d6e4; }
            QCalendarWidget QSpinBox { background: #ffffff; color: #172033; border: 1px solid #c9d6e4; }
            QCalendarWidget QAbstractItemView:enabled {
                background: #ffffff; color: #172033; selection-background-color: #2563eb;
                selection-color: #ffffff; outline: 0;
            }
            QCalendarWidget QAbstractItemView:disabled { color: #94a3b8; }
        """
        date_edit_style = """
            QDateEdit { min-width: 118px; padding-right: 30px; }
            QDateEdit::drop-down {
                subcontrol-origin: padding; subcontrol-position: top right; width: 28px;
                border-left: 1px solid rgba(148, 163, 184, 0.55);
            }
            QDateEdit::down-arrow { image: none; width: 0px; height: 0px; }
        """
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd.MM.yyyy")
        cal = QCalendarWidget()
        cal.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        cal.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        cal.setStyleSheet(calendar_style)
        date_edit.setCalendarWidget(cal)
        date_edit.setStyleSheet(date_edit_style)

    def wholesaler_part_tl_value(self, value):
        text = str(value or "0")
        if "TL" in text and "$" not in text:
            return safe_float(text)
        return safe_float(text) * self.usd_rate

    def record_payment_to_cash(self, title, amount, method, source_id=""):
        if self.user_setting_value("wholesaler_payments_affect_cash", "false") != "true":
            return
        payload = {
            "t": datetime.datetime.now().strftime("%d.%m.%Y"),
            "tip": "Gider",
            "aciklama": title,
            "tutar": amount,
            "odeme_tipi": method,
            "source": source_id
        }
        res = db.child("users").child(self.user_id).child("kasa").push(payload, self.token)
        cash_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Kasa Gideri", title, "kasa", cash_id, after=payload)

    def save_wholesaler_cash_setting(self, checked):
        self.set_user_setting("wholesaler_payments_affect_cash", "true" if checked else "false")
        self.refresh_all_tables()

    def apply_finance_visibility(self):
        visible = self.user_setting_value("show_finance_dashboard", "false") == "true" and self.staff_can("finance_dashboard")
        self.apply_dashboard_card_mode(compact=not visible)
        for widget in getattr(self, "finance_widgets", []):
            widget.setVisible(visible)

    def toggle_finance_dashboard_setting(self, checked):
        if checked and not self.require_staff_permission("finance_dashboard", "Kasa/kazanç görünürlüğü"):
            self.finance_visible_cb.blockSignals(True)
            self.finance_visible_cb.setChecked(False)
            self.finance_visible_cb.blockSignals(False)
            self.set_user_setting("show_finance_dashboard", "false")
            self.apply_finance_visibility()
            return
        if checked:
            lock_until = self.finance_password_lock_until()
            if lock_until:
                QMessageBox.warning(self, "Bekleme Süresi", f"Çok fazla hatalı deneme yapıldı.\n\nTekrar deneme zamanı: {lock_until.strftime('%H:%M')}")
                self.finance_visible_cb.blockSignals(True)
                self.finance_visible_cb.setChecked(False)
                self.finance_visible_cb.blockSignals(False)
                self.set_user_setting("show_finance_dashboard", "false")
                self.apply_finance_visibility()
                return
            password, ok = QInputDialog.getText(self, "Kasa Bilgileri", "Kasayı göstermek için master şifre girin:", QLineEdit.EchoMode.Password)
            saved_password = str(self.user_setting_value("finance_dashboard_password", "9977"))
            if not ok or password != saved_password:
                self.register_finance_password_failure()
                QMessageBox.warning(self, "Yetkisiz İşlem", "Şifre hatalı. Kazanç kutuları gizli kalacak.")
                self.finance_visible_cb.blockSignals(True)
                self.finance_visible_cb.setChecked(False)
                self.finance_visible_cb.blockSignals(False)
                self.set_user_setting("show_finance_dashboard", "false")
                self.apply_finance_visibility()
                return
            self.clear_finance_password_failures()
        self.set_user_setting("show_finance_dashboard", "true" if checked else "false")
        self.apply_finance_visibility()

    def change_finance_dashboard_password(self):
        lock_until = self.finance_password_lock_until()
        if lock_until:
            QMessageBox.warning(self, "Bekleme Süresi", f"Çok fazla hatalı deneme yapıldı.\n\nTekrar deneme zamanı: {lock_until.strftime('%H:%M')}")
            return
        current_password = str(self.user_setting_value("finance_dashboard_password", "9977"))
        old_password, ok = QInputDialog.getText(self, "Kazanç Şifresi", "Mevcut şifre:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if old_password != current_password:
            self.register_finance_password_failure()
            QMessageBox.warning(self, "Şifre Hatalı", "Mevcut şifre doğru değil.")
            return
        self.clear_finance_password_failures()

        new_password, ok = QInputDialog.getText(self, "Kazanç Şifresi", "Yeni şifre:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        new_password = str(new_password).strip()
        if len(new_password) < 4:
            QMessageBox.warning(self, "Geçersiz Şifre", "Yeni şifre en az 4 karakter olmalı.")
            return

        repeat_password, ok = QInputDialog.getText(self, "Kazanç Şifresi", "Yeni şifre tekrar:", QLineEdit.EchoMode.Password)
        if not ok:
            return
        if repeat_password != new_password:
            QMessageBox.warning(self, "Şifre Uyuşmuyor", "Yeni şifreler aynı değil.")
            return

        self.set_user_setting("finance_dashboard_password", new_password)
        QMessageBox.information(self, "Başarılı", "Kazanç şifresi güncellendi.")

    def finance_password_lock_until(self):
        raw = str(self.user_setting_value("finance_password_lock_until", "") or "")
        if not raw:
            return None
        try:
            lock_until = datetime.datetime.fromisoformat(raw)
            if datetime.datetime.now() < lock_until:
                return lock_until
        except:
            pass
        self.clear_finance_password_failures()
        return None

    def register_finance_password_failure(self):
        attempts = int(safe_float(self.user_setting_value("finance_password_attempts", "0"))) + 1
        if attempts >= 3:
            self.set_user_setting("finance_password_attempts", "0")
            self.set_user_setting("finance_password_lock_until", (datetime.datetime.now() + datetime.timedelta(minutes=15)).isoformat())
        else:
            self.set_user_setting("finance_password_attempts", str(attempts))

    def clear_finance_password_failures(self):
        self.set_user_setting("finance_password_attempts", "0")
        self.set_user_setting("finance_password_lock_until", "")

    def reset_finance_dashboard_password(self):
        email_confirm, ok = QInputDialog.getText(
            self,
            "Kazanç Şifresi Sıfırlama",
            "Şifreyi sıfırlamak için giriş yaptığınız e-postayı yazın:"
        )
        if not ok:
            return
        if str(email_confirm).strip().lower() != str(self.user_email).strip().lower():
            QMessageBox.warning(self, "Doğrulama Hatası", "E-posta hesabınızla eşleşmedi. Şifre sıfırlanmadı.")
            return
        self.set_user_setting("finance_dashboard_password", "9977")
        self.set_user_setting("show_finance_dashboard", "false")
        self.clear_finance_password_failures()
        if hasattr(self, "finance_visible_cb"):
            self.finance_visible_cb.blockSignals(True)
            self.finance_visible_cb.setChecked(False)
            self.finance_visible_cb.blockSignals(False)
        self.apply_finance_visibility()
        QMessageBox.information(self, "Şifre Sıfırlandı", "Kazanç şifresi varsayılan şifreye döndürüldü: 9977")

    def should_count_cash_record(self, record):
        if self.user_setting_value("wholesaler_payments_affect_cash", "false") == "true":
            return True
        return not str(record.get("source", "")).startswith("toptanci:")

    def kasa_period_bounds(self, mode):
        today = datetime.date.today()
        if mode == "Bugün":
            return today, today
        if mode == "Bu Hafta":
            start = today - datetime.timedelta(days=today.weekday())
            return start, today
        if mode == "Geçen Hafta":
            end = today - datetime.timedelta(days=today.weekday() + 1)
            start = end - datetime.timedelta(days=6)
            return start, end
        if mode == "Geçen Ay":
            first_this = today.replace(day=1)
            end = first_this - datetime.timedelta(days=1)
            start = end.replace(day=1)
            return start, end
        start = today.replace(day=1)
        return start, today

    def update_kasa_period_summary(self):
        if not hasattr(self, "lbl_kasa_period_summary"):
            return
        mode = self.kasa_period_cb.currentText() if hasattr(self, "kasa_period_cb") else "Bugün"
        start, end = self.kasa_period_bounds(mode)
        gelir = gider = servis = 0.0
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        for v in data.values():
            if not isinstance(v, dict):
                continue
            if v.get("odeme_durumu") == "Ödendi" and "İade" not in v.get("d", ""):
                try:
                    dt = datetime.datetime.strptime(str(v.get("z", "")).split(" ")[0], "%d.%m.%Y").date()
                except:
                    continue
                if start <= dt <= end:
                    servis += safe_float(v.get("masraf", "0"))
        kasa_d = safe_dict_parse(getattr(self, "kasa_data", {}))
        if not isinstance(kasa_d, dict):
            kasa_d = {}
        for v in kasa_d.values():
            if not isinstance(v, dict):
                continue
            if not self.should_count_cash_record(v):
                continue
            try:
                dt = datetime.datetime.strptime(str(v.get("t", "")).split(" ")[0], "%d.%m.%Y").date()
            except:
                continue
            if not (start <= dt <= end):
                continue
            tut = safe_float(v.get("tutar", "0"))
            if "Gelir" in v.get("tip", "") or "Income" in v.get("tip", ""):
                gelir += tut
            else:
                gider += tut
        toplam_gelir = servis + gelir
        net = toplam_gelir - gider
        net_color = "#16a34a" if net >= 0 else "#dc2626"
        self.lbl_kasa_period_summary.setText(
            f"<span style='color:#475569;'>{mode}:</span> "
            f"<span style='color:#15803d;'>Gelir: {format_money(toplam_gelir, '₺')}</span>"
            f" <span style='color:#64748b;'>|</span> "
            f"<span style='color:#dc2626;'>Harcama: {format_money(gider, '₺')}</span>"
            f" <span style='color:#64748b;'>|</span> "
            f"<span style='color:{net_color};'>Net: {format_money(net, '₺')}</span>"
        )

    def parse_date_value(self, value):
        text = str(value or "").strip()
        if not text:
            return datetime.datetime.min
        text = text.replace("T", " ").replace("/", ".")
        if "." in text:
            parts = text.split()
            date_part = parts[0]
            date_bits = date_part.split(".")
            if len(date_bits) == 3 and len(date_bits[2]) == 2:
                text = text.replace(date_part, f"{date_bits[0]}.{date_bits[1]}.20{date_bits[2]}", 1)
        formats = [
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(text, fmt)
            except:
                pass
        return datetime.datetime.min

    def is_delivered_record(self, record):
        if not isinstance(record, dict):
            return False, False
        status_norm = self.normalize_upper(record.get("d", ""))
        delivery_norm = self.normalize_upper(record.get("teslim_durumu", ""))
        status_plain = status_norm.replace("İ", "I")
        delivery_plain = delivery_norm.replace("İ", "I")
        is_iade = "IADE" in status_plain or "IADE" in delivery_plain
        status_delivered = (
            "TESLİM EDİLDİ" in status_norm
            or "TESLIM EDILDI" in status_plain
            or "İADE EDİLDİ" in status_norm
            or "IADE EDILDI" in status_plain
        )
        delivery_delivered = (
            "MÜŞTERİYE TESLİM EDİLDİ" in delivery_norm
            or "MUSTERİYE TESLİM EDİLDİ" in delivery_norm
            or "MUSTERIYE TESLIM EDILDI" in delivery_plain
            or "İADE TESLİM EDİLDİ" in delivery_norm
            or "IADE TESLIM EDILDI" in delivery_plain
        )
        waiting = "BEKLIYOR" in status_plain or "BEKLIYOR" in delivery_plain
        if status_delivered or delivery_delivered:
            return True, is_iade
        return False, is_iade

    def delivery_date_for_record(self, record):
        if not isinstance(record, dict):
            return ""
        teslim_tarihi = record.get("teslim_tarihi")
        if teslim_tarihi and self.parse_date_value(teslim_tarihi) != datetime.datetime.min:
            return teslim_tarihi
        return record.get("z", "")

    def device_display_text(self, record):
        if not isinstance(record, dict):
            return ""
        text = str(record.get("ci", "") or "")
        badges = []
        note_history = safe_dict_parse(record.get("not_gecmisi", {}))
        note_count = len(note_history) if isinstance(note_history, dict) else 0
        if record.get("not") and note_count == 0:
            note_count = 1
        if note_count > 0:
            badges.append(f"📝 Not: {note_count}{'!' if record.get('not_okundu') == False else ''}")
        photo_count = len(get_record_photos(record))
        if photo_count > 0:
            badges.append(f"📷 Foto: {photo_count}")
        if len(self.get_faults(record)) > 1:
            badges.append(f"⚠️ Arıza: {len(self.get_faults(record))}")
        approval_badge = self.approval_badge_text(record)
        if approval_badge:
            badges.append(approval_badge)
        if badges:
            text += "  [" + " | ".join(badges) + "]"
        return text

    def approval_badge_text(self, record):
        status = str(record.get("approval_status", "") or "").strip()
        if status == "Bekliyor":
            return "⏳ ONAY BEKLİYOR"
        if status == "Onaylandı":
            return "✅ ONAYLANDI"
        if status == "Reddedildi":
            return "⛔ REDDEDİLDİ"
        return ""

    def approval_color(self, record):
        status = str(record.get("approval_status", "") or "").strip()
        if status == "Bekliyor":
            return QColor("#f59e0b")
        if status == "Onaylandı":
            return QColor("#22c55e")
        if status == "Reddedildi":
            return QColor("#ef4444")
        return None

    def status_display_text(self, record, base_status):
        badge = self.approval_badge_text(record)
        base_status = str(base_status or "")
        return f"{base_status}  {badge}" if badge else base_status

    def party_display_text(self, record):
        if not isinstance(record, dict):
            return ""
        name = str(record.get("m", "") or "")
        if self.is_bayi_record(record):
            return f"{name}  [BAYİ]"
        phone = "".join(filter(str.isdigit, str(record.get("t", ""))))[-10:]
        if phone or self.customer_records_for_name(name):
            return name
        return name

    def party_row_colors(self, record, count):
        if not isinstance(record, dict):
            return None
        approval_color = self.approval_color(record)
        if approval_color:
            return [approval_color] * count
        if self.is_bayi_record(record):
            return [QColor("#38bdf8")] * count
        name = str(record.get("m", "") or "")
        phone = "".join(filter(str.isdigit, str(record.get("t", ""))))[-10:]
        if phone or self.customer_records_for_name(name):
            return [QColor("#a78bfa")] * count
        return None

    def delivered_period_bounds(self):
        mode = self.delivered_period_cb.currentText() if hasattr(self, "delivered_period_cb") else "Bugün"
        today = datetime.date.today()
        if mode == "Tümü":
            return datetime.datetime.min, datetime.datetime.max
        if mode == "Bu Hafta":
            start = today - datetime.timedelta(days=today.weekday())
            return datetime.datetime.combine(start, datetime.time.min), datetime.datetime.combine(today, datetime.time.max)
        if mode == "Bu Ay":
            return datetime.datetime.combine(today.replace(day=1), datetime.time.min), datetime.datetime.combine(today, datetime.time.max)
        if mode == "Tarih Aralığı":
            start = self.delivered_date_start.date().toPyDate()
            end = self.delivered_date_end.date().toPyDate()
            if end < start:
                start, end = end, start
            return datetime.datetime.combine(start, datetime.time.min), datetime.datetime.combine(end, datetime.time.max)
        return datetime.datetime.combine(today, datetime.time.min), datetime.datetime.combine(today, datetime.time.max)

    def on_delivered_period_changed(self, text=None):
        mode = text or (self.delivered_period_cb.currentText() if hasattr(self, "delivered_period_cb") else "")
        if mode == "Bugün" and hasattr(self, "delivered_date_start") and hasattr(self, "delivered_date_end"):
            today_qdate = QDate.currentDate()
            self.delivered_date_start.blockSignals(True)
            self.delivered_date_end.blockSignals(True)
            self.delivered_date_start.setDate(today_qdate)
            self.delivered_date_end.setDate(today_qdate)
            self.delivered_date_start.blockSignals(False)
            self.delivered_date_end.blockSignals(False)
        if hasattr(self, "delivered_date_start"):
            self.delivered_date_start.setEnabled(True)
        if hasattr(self, "delivered_date_end"):
            self.delivered_date_end.setEnabled(True)
        self.filter_delivered_table()

    def on_delivered_date_changed(self):
        if hasattr(self, "delivered_period_cb") and self.delivered_period_cb.currentText() != "Tarih Aralığı":
            self.delivered_period_cb.blockSignals(True)
            self.delivered_period_cb.setCurrentText("Tarih Aralığı")
            self.delivered_period_cb.blockSignals(False)
        if hasattr(self, "delivered_date_start"):
            self.delivered_date_start.setEnabled(True)
        if hasattr(self, "delivered_date_end"):
            self.delivered_date_end.setEnabled(True)
        self.filter_delivered_table()

    def on_delivered_status_changed(self, text=None):
        self.filter_delivered_table()

    def filter_delivered_table(self):
        if not hasattr(self, "table_delivered"):
            return
        self.table_delivered.setRowCount(0)
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        start, end = self.delivered_period_bounds()
        status_filter = self.delivered_status_cb.currentText() if hasattr(self, "delivered_status_cb") else "Tümü"
        total, shown, iade_count, teslim_count = 0, 0, 0, 0
        total_amount = 0.0
        delivered_nakit, delivered_kart, delivered_eft = 0.0, 0.0, 0.0

        delivered_rows = []
        for kid, record in data.items():
            if not isinstance(record, dict):
                continue
            status = str(record.get("d", "") or "")
            delivery = str(record.get("teslim_durumu", "") or "")
            delivered_ok, is_iade = self.is_delivered_record(record)
            if not delivered_ok:
                continue
            total += 1
            odeme = str(record.get("odeme_durumu", "Ödenmedi") or "Ödenmedi")
            if status_filter == "Başarılı Teslim" and is_iade:
                continue
            if status_filter == "İade Teslim" and not is_iade:
                continue
            if status_filter == "Ödendi" and odeme != "Ödendi":
                continue
            if status_filter == "Ödenmedi" and odeme == "Ödendi":
                continue
            delivered_dt = self.parse_date_value(self.delivery_date_for_record(record))
            if delivered_dt == datetime.datetime.min or not (start <= delivered_dt <= end):
                continue
            delivered_rows.append((delivered_dt, kid, record, is_iade))

        delivered_rows.sort(key=lambda item: (item[0], self.parse_date_value(self.delivery_date_for_record(item[2]))), reverse=True)
        for _, kid, record, is_iade in delivered_rows:
            ucret = safe_float(record.get("masraf", "0"))
            money_text = "" if ucret == 0 else f"{format_money(ucret, '₺')}"
            odeme = record.get("odeme_durumu", "Ödenmedi")
            o_tip = record.get("odeme_tipi", "Nakit")
            payment_text = f"{odeme} ({o_tip})" if odeme == "Ödendi" else odeme
            status_text = self.status_display_text(record, "↩ İADE TESLİM EDİLDİ" if is_iade else "TESLİM EDİLDİ")
            color = QColor("#f97316") if is_iade else QColor("#22c55e")
            pay_color = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
            row_idx = self.add_row_to_table(
                self.table_delivered,
                [
                    kid,
                    record.get("c_no"),
                    self.party_display_text(record),
                    self.device_display_text(record),
                    record.get("yapilan_islem", ""),
                    money_text,
                    self.delivery_date_for_record(record),
                    status_text,
                    record.get("teslim_durumu") or "Müşteriye Teslim Edildi",
                    payment_text,
                ],
                self.party_row_colors(record, 10) or [color] * 9 + [pay_color],
            )
            pay_item = self.table_delivered.item(row_idx, 9)
            if pay_item:
                pay_item.setForeground(pay_color)
            if is_iade:
                iade_count += 1
                for col in range(self.table_delivered.columnCount()):
                    item = self.table_delivered.item(row_idx, col)
                    if item:
                        item.setBackground(QColor("#fff3e0"))
            else:
                teslim_count += 1
                if odeme == "Ödendi":
                    total_amount += ucret
                    if "Kart" in o_tip:
                        delivered_kart += ucret
                    elif "EFT" in o_tip or "Havale" in o_tip:
                        delivered_eft += ucret
                    else:
                        delivered_nakit += ucret
            shown += 1

        if hasattr(self, "lbl_delivered_nakit"):
            self.lbl_delivered_nakit.setText(f"Nakit: {format_money(delivered_nakit, '₺')}")
            self.lbl_delivered_kart.setText(f"Kart: {format_money(delivered_kart, '₺')}")
            self.lbl_delivered_eft.setText(f"EFT: {format_money(delivered_eft, '₺')}")
        if hasattr(self, "lbl_delivered_summary"):
            self.lbl_delivered_summary.setText(
                f"Gösterilen: {shown} / Toplam Teslim: {total} | Başarılı: {teslim_count} | İade: {iade_count} | Tutar: {format_money(total_amount, '₺')}"
            )
        self.update_main_tab_counts(c_delivered=shown)

    def get_faults(self, record):
        if not isinstance(record, dict):
            return []
        faults = record.get("arizalar", [])
        if isinstance(faults, dict):
            faults = list(faults.values())
        if not isinstance(faults, list):
            faults = []
        faults = [self.normalize_upper(f).strip() for f in faults if str(f).strip()]
        primary = self.normalize_upper(record.get("a", "")).strip()
        if primary and primary not in faults:
            faults.insert(0, primary)
        return faults

    def format_faults(self, record, compact=True):
        faults = self.get_faults(record)
        if not faults:
            return ""
        if compact and len(faults) > 1:
            return f"⚠️ {faults[0]} (+{len(faults) - 1})"
        return " / ".join(faults) if compact else "<br>".join(faults)

    def add_extra_fault_from_form(self):
        fault = self.normalize_upper(self.f_ariza.text()).strip()
        if not fault:
            QMessageBox.information(self, "Ek Arıza", "Önce arıza alanına eklemek istediğiniz arızayı yazın.")
            return
        if fault not in self.extra_faults:
            self.extra_faults.append(fault)
        self.f_ariza.clear()
        self.lbl_ariza_ozet.setText("Ek arızalar: " + " / ".join(self.extra_faults))

    def filtered_party_names(self, names, data, is_bayi, mode):
        if not isinstance(data, dict):
            data = {}
        rows = []
        for name in names:
            if not name:
                continue
            target = self.normalize_upper(name)
            records = [
                v for v in data.values()
                if isinstance(v, dict) and self.normalize_upper(v.get("m", "")) == target and self.is_bayi_record(v) == is_bayi
            ]
            if not records:
                if is_bayi and mode in ["Alfabetik", "Son Kayıt"]:
                    rows.append((name, datetime.datetime.min))
                continue
            paid = any(v.get("odeme_durumu") == "Ödendi" for v in records)
            unpaid = any(v.get("odeme_durumu", "Ödenmedi") != "Ödendi" for v in records)
            if mode == "Ödeme Yapanlar" and not paid:
                continue
            if mode == "Ödeme Yapmayanlar" and not unpaid:
                continue
            latest = max(self.parse_date_value(v.get("z", "")) for v in records)
            rows.append((name, latest))
        if mode == "Son Kayıt":
            rows.sort(key=lambda item: item[1], reverse=True)
        else:
            rows.sort(key=lambda item: self.normalize_upper(item[0]))
        return [name for name, _ in rows]

    def customer_names_for_list(self, mode):
        return [customer.get("display", customer.get("name", "")) for customer in self.customer_entries_for_list(mode)]

    def customer_entries_for_list(self, mode):
        rows = []
        for customer in self.get_customer_index():
            name = self.normalize_upper(customer.get("name", ""))
            key = str(customer.get("key", "") or "")
            if not name or not key:
                continue
            records = [rec for rec in customer.get("records", []) if isinstance(rec, dict) and not self.is_bayi_record(rec)]
            if not records:
                continue
            paid = any(rec.get("odeme_durumu") == "Ödendi" for rec in records)
            unpaid = any(rec.get("odeme_durumu", "Ödenmedi") != "Ödendi" for rec in records)
            if mode == "Ödeme Yapanlar" and not paid:
                continue
            if mode == "Ödeme Yapmayanlar" and not unpaid:
                continue
            latest = max(self.parse_date_value(rec.get("z", "")) for rec in records)
            rows.append((customer, latest))
        if mode == "Son Kayıt":
            rows.sort(key=lambda item: item[1], reverse=True)
        else:
            rows.sort(key=lambda item: self.normalize_upper(item[0].get("name", "")))
        name_counts = {}
        for customer, _ in rows:
            name = self.normalize_upper(customer.get("name", "")).strip()
            name_counts[name] = name_counts.get(name, 0) + 1
        entries = []
        for customer, _ in rows:
            item = dict(customer)
            item["display"] = self.customer_list_label(item, name_counts)
            entries.append(item)
        return entries

    def is_bayi_record(self, record):
        if not isinstance(record, dict):
            return False
        record_type = str(record.get("record_type", "") or "").strip().lower()
        if record_type in ["bayi", "dealer", "partner"]:
            return True
        value = record.get("is_bayi", False)
        if isinstance(value, str):
            return value.strip().lower() in ["true", "1", "evet", "yes"]
        return bool(value)

    def normalize_upper(self, text):
        return str(text or "").replace("i", "İ").upper()

    def force_uppercase(self, widget, text):
        upper = self.normalize_upper(text)
        if text == upper:
            return
        pos = widget.cursorPosition()
        widget.blockSignals(True)
        widget.setText(upper)
        widget.setCursorPosition(min(pos, len(upper)))
        widget.blockSignals(False)

    def force_uppercase_textedit(self, widget):
        text = widget.toPlainText()
        upper = self.normalize_upper(text)
        if text == upper:
            return
        cursor = widget.textCursor()
        pos = cursor.position()
        widget.blockSignals(True)
        widget.setPlainText(upper)
        cursor.setPosition(min(pos, len(upper)))
        widget.setTextCursor(cursor)
        widget.blockSignals(False)

    def get_customer_index(self):
        data = safe_dict_parse(self.kayitlar_data)
        if not isinstance(data, dict):
            data = {}
        customers = {}
        for rec_id, rec in data.items():
            if not isinstance(rec, dict):
                continue
            if self.is_bayi_record(rec):
                continue
            name = self.normalize_upper(rec.get("m", ""))
            phone = "".join(filter(str.isdigit, str(rec.get("t", ""))))[-10:]
            if not name:
                continue
            key = self.customer_identity_key(rec_id, rec)
            info = customers.setdefault(key, {"key": key, "name": name, "phone": phone, "count": 0, "last": "", "records": []})
            info["count"] += 1
            info["records"].append(rec)
            z = str(rec.get("z", ""))
            if z > info["last"]:
                info["last"] = z
                info["name"] = name
            if phone:
                info["phone"] = phone
        return list(customers.values())

    def open_customer_picker(self):
        customers = self.get_customer_index()
        if not customers:
            QMessageBox.information(self, "Kayıtlı Müşteri", "Henüz kayıtlı müşteri bulunamadı.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Kayıtlı Müşteri Seç")
        dlg.setMinimumSize(520, 420)
        lay = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Ad soyad veya telefon yazın...")
        result_list = QListWidget()
        lay.addWidget(search)
        lay.addWidget(result_list)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btns)

        def populate(term=""):
            term_norm = self.normalize_upper(term)
            term_digits = "".join(filter(str.isdigit, str(term)))
            result_list.clear()
            for customer in customers:
                haystack = f"{customer['name']} {customer['phone']}"
                if term_norm and term_norm not in haystack and (not term_digits or term_digits not in customer["phone"]):
                    continue
                label = f"{customer['name']}  |  {customer['phone'] or 'Telefon yok'}  |  {customer['count']} kayıt"
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, customer)
                result_list.addItem(item)
        populate()

        search.textChanged.connect(populate)
        result_list.itemDoubleClicked.connect(lambda _: dlg.accept())
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted and result_list.currentItem():
            customer = result_list.currentItem().data(Qt.ItemDataRole.UserRole)
            self.selected_customer_key = str(customer.get("key", "") or "")
            self.cb_bayi_kayit.blockSignals(True)
            self.cb_bayi_kayit.setChecked(False)
            self.cb_bayi_kayit.blockSignals(False)
            if hasattr(self, "cb_registered_customer"):
                self.cb_registered_customer.blockSignals(True)
                self.cb_registered_customer.setChecked(True)
                self.cb_registered_customer.blockSignals(False)
            self.f_ad.show()
            self.f_ad.setText(customer["name"])
            self.f_tel.setText(customer["phone"][-10:])
            if hasattr(self, "lbl_record_mode_state"):
                self.lbl_record_mode_state.setText("Kayıtlı müşteri seçildi")
            self.lbl_musteri_uyari.show()
            self.lbl_musteri_uyari.setStyleSheet("color:#16a34a; font-weight:700; padding: 2px 0;")
            self.lbl_musteri_uyari.setText(f"Seçili kayıtlı müşteri: {customer['name']} ({customer['count']} kayıt)")
            self.f_cihaz.setFocus()

    def apply_customer_suggestion(self, item=None):
        item = item or self.customer_suggestions.currentItem()
        if not item:
            return
        customer = item.data(Qt.ItemDataRole.UserRole)
        if not customer:
            return
        self.selected_customer_key = str(customer.get("key", "") or "")
        if hasattr(self, "cb_bayi_kayit") and self.cb_bayi_kayit.isChecked():
            self.cb_bayi_kayit.blockSignals(True)
            self.cb_bayi_kayit.setChecked(False)
            self.cb_bayi_kayit.blockSignals(False)
        if hasattr(self, "cb_registered_customer"):
            self.cb_registered_customer.blockSignals(True)
            self.cb_registered_customer.setChecked(True)
            self.cb_registered_customer.blockSignals(False)
        self.f_ad.setText(customer["name"])
        self.f_tel.setText(customer["phone"][-10:])
        if hasattr(self, "lbl_record_mode_state"):
            self.lbl_record_mode_state.setText("Kayıtlı müşteri seçildi")
        self.customer_suggestions.setVisible(False)
        self.lbl_musteri_uyari.show()
        self.lbl_musteri_uyari.setStyleSheet("color:#16a34a; font-weight:700; padding: 2px 0;")
        self.lbl_musteri_uyari.setText(f"Seçili kayıtlı müşteri: {customer['name']} ({customer['count']} kayıt)")
        self.f_cihaz.setFocus()

    def clear_selected_customer_selection(self, *_args):
        if getattr(self, "cb_bayi_kayit", None) and self.cb_bayi_kayit.isChecked():
            return
        if not getattr(self, "selected_customer_key", ""):
            return
        self.selected_customer_key = ""
        if hasattr(self, "cb_registered_customer"):
            self.cb_registered_customer.blockSignals(True)
            self.cb_registered_customer.setChecked(False)
            self.cb_registered_customer.blockSignals(False)
        if hasattr(self, "lbl_record_mode_state"):
            self.lbl_record_mode_state.setText("Yeni müşteri kaydı")

    def open_partner_picker(self):
        partners = []
        data = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
        if isinstance(data, dict):
            for pid, info in data.items():
                if not isinstance(info, dict):
                    continue
                name = self.normalize_upper(info.get("ad", "")).strip()
                if not name:
                    continue
                phone = "".join(filter(str.isdigit, str(info.get("tel", "") or info.get("telefon", ""))))[-10:]
                partners.append({"key": str(pid), "name": name, "phone": phone})
        known_names = {p["name"] for p in partners}
        for name in sorted([n for n in self.bayi_isimleri if n], key=self.normalize_upper):
            norm = self.normalize_upper(name).strip()
            if norm and norm not in known_names:
                partners.append({"key": "", "name": norm, "phone": self.partner_phone_by_name(norm)})

        if not partners:
            QMessageBox.information(self, "Bayi Seç", "Henüz kayıtlı bayi bulunamadı.")
            return None

        dlg = QDialog(self)
        dlg.setWindowTitle("Bayi Seç")
        dlg.setMinimumSize(520, 420)
        lay = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Bayi adı veya telefon yazın...")
        result_list = QListWidget()
        lay.addWidget(search)
        lay.addWidget(result_list)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btns)

        def populate(term=""):
            term_norm = self.normalize_upper(term)
            term_digits = "".join(filter(str.isdigit, str(term)))
            result_list.clear()
            for partner in partners:
                haystack = f"{partner['name']} {partner['phone']}"
                if term_norm and term_norm not in haystack and (not term_digits or term_digits not in partner["phone"]):
                    continue
                item = QListWidgetItem(f"{partner['name']}  |  {partner['phone'] or 'Telefon yok'}")
                item.setData(Qt.ItemDataRole.UserRole, partner)
                result_list.addItem(item)
            if result_list.count() > 0:
                result_list.setCurrentRow(0)

        populate()
        search.textChanged.connect(populate)
        result_list.itemDoubleClicked.connect(lambda _: dlg.accept())
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)

        if dlg.exec() == QDialog.DialogCode.Accepted and result_list.currentItem():
            return result_list.currentItem().data(Qt.ItemDataRole.UserRole)
        return None

    def refresh_customer_suggestions(self, customers, name, phone):
        self.customer_suggestions.clear()
        if self.cb_bayi_kayit.isChecked() or (len(name) < 2 and len(phone) < 3):
            self.customer_suggestions.setVisible(False)
            return

        matches = []
        for customer in customers:
            name_match = name and name in customer["name"]
            phone_match = phone and phone in customer["phone"]
            if name_match or phone_match:
                matches.append(customer)

        matches = sorted(matches, key=lambda c: (0 if c["phone"].endswith(phone) and phone else 1, c["name"]))[:5]
        for customer in matches:
            label = f"{customer['name']}    |    {customer['phone'] or 'Telefon yok'}    |    {customer['count']} kayıt"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, customer)
            self.customer_suggestions.addItem(item)
        self.customer_suggestions.setVisible(bool(matches))

    def update_customer_hint(self):
        if self.cb_bayi_kayit.isChecked():
            self.lbl_musteri_uyari.setText("")
            self.lbl_musteri_uyari.hide()
            self.customer_suggestions.setVisible(False)
            return
        name = self.normalize_upper(self.f_ad.text()).strip()
        phone = "".join(filter(str.isdigit, self.f_tel.text()))
        if len(phone) > 10:
            phone = phone[-10:]
        if not name and not phone:
            self.lbl_musteri_uyari.setText("")
            self.lbl_musteri_uyari.hide()
            self.customer_suggestions.setVisible(False)
            return

        customers = self.get_customer_index()
        self.refresh_customer_suggestions(customers, name, phone)
        by_phone = [c for c in customers if phone and c["phone"].endswith(phone)]
        by_name = [c for c in customers if name and c["name"] == name]

        if by_phone:
            c = by_phone[0]
            self.lbl_musteri_uyari.show()
            self.lbl_musteri_uyari.setStyleSheet("color:#16a34a; font-weight:700; padding: 2px 0;")
            self.lbl_musteri_uyari.setText(f"Kayıtlı müşteri bulundu: {c['name']} ({c['count']} kayıt)")
        elif by_name:
            phones = ", ".join(sorted({c["phone"] or "telefon yok" for c in by_name}))
            self.lbl_musteri_uyari.show()
            self.lbl_musteri_uyari.setStyleSheet("color:#f59e0b; font-weight:700; padding: 2px 0;")
            self.lbl_musteri_uyari.setText(f"Aynı isimde müşteri var. Karışmaması için telefon kontrolü yapın: {phones}")
        else:
            self.lbl_musteri_uyari.show()
            self.lbl_musteri_uyari.setStyleSheet("color:#64748b; font-weight:600; padding: 2px 0;")
            self.lbl_musteri_uyari.setText("Yeni müşteri olarak kaydedilecek.")

    def change_font_weight(self, text):
        self.set_user_setting("font_weight", text)
        self.settings.setValue("current_font_weight", text)
        QMessageBox.information(self, "Bilgi", "Yazı kalınlığı kaydedildi. Değişikliğin uygulanması için programı tamamen kapatıp yeniden açın.")

    def toggle_registered_customer_mode(self, checked):
        if checked:
            if self.cb_bayi_kayit.isChecked():
                self.cb_bayi_kayit.setChecked(False)
            self.open_customer_picker()
            if not self.f_ad.text().strip():
                self.selected_customer_key = ""
                self.cb_registered_customer.blockSignals(True)
                self.cb_registered_customer.setChecked(False)
                self.cb_registered_customer.blockSignals(False)
                self.lbl_record_mode_state.setText("Yeni müşteri kaydı")
        else:
            self.selected_customer_key = ""
            if not self.cb_bayi_kayit.isChecked():
                self.lbl_record_mode_state.setText("Yeni müşteri kaydı")

    def toggle_bayi_mode(self, state):
        if hasattr(self, "lbl_record_mode_state"):
            self.lbl_record_mode_state.setText("Bayi cihaz kaydı" if state else "Yeni müşteri kaydı")
        if state: 
            self.selected_customer_key = ""
            if hasattr(self, "cb_registered_customer") and self.cb_registered_customer.isChecked():
                self.cb_registered_customer.blockSignals(True)
                self.cb_registered_customer.setChecked(False)
                self.cb_registered_customer.blockSignals(False)
            partner = self.open_partner_picker()
            if not partner:
                self.cb_bayi_kayit.blockSignals(True)
                self.cb_bayi_kayit.setChecked(False)
                self.cb_bayi_kayit.blockSignals(False)
                self.selected_bayi_key = ""
                self.lbl_record_mode_state.setText("Yeni müşteri kaydı")
                self.f_ad.show()
                self.lbl_musteri_uyari.hide()
                return
            name = partner["name"]
            self.selected_bayi_key = str(partner.get("key", "") or "")
            if self.combo_bayi.findText(name) < 0:
                self.combo_bayi.addItem(name)
            self.combo_bayi.setCurrentText(name)
            self.f_ad.hide()
            self.btn_musteri_sec.hide()
            self.customer_suggestions.hide()
            self.f_tel.setText(partner.get("phone", "")[-10:])
            self.lbl_musteri_uyari.show()
            self.lbl_musteri_uyari.setStyleSheet("color:#16a34a; font-weight:700; padding: 2px 0;")
            self.lbl_musteri_uyari.setText(f"Seçili bayi: {name}")
            self.f_cihaz.setFocus()
        else: 
            self.selected_bayi_key = ""
            self.f_ad.show()
            self.btn_musteri_sec.hide()
            self.lbl_musteri_uyari.show()
            self.combo_bayi.hide()
            self.update_customer_hint()

    def partner_phone_by_name(self, name):
        target = self.normalize_upper(name)
        data = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
        if isinstance(data, dict):
            for info in data.values():
                if isinstance(info, dict) and self.normalize_upper(info.get("ad", "")) == target:
                    return "".join(filter(str.isdigit, str(info.get("tel", "") or info.get("telefon", ""))))[-10:]
        return ""

    def fill_partner_phone(self, name):
        if not getattr(self, "cb_bayi_kayit", None) or not self.cb_bayi_kayit.isChecked():
            return
        normalized_name = self.normalize_upper(name).strip()
        current_key = str(getattr(self, "selected_bayi_key", "") or "")
        current_info = self.partner_info_by_key(current_key)
        current_name = self.normalize_upper(current_info.get("ad", "")).strip() if current_info else ""
        if current_key and current_name == normalized_name:
            key, info = current_key, current_info
        else:
            key, info = self.partner_record_key_by_name(normalized_name)
            if key:
                self.selected_bayi_key = str(key)
            else:
                self.selected_bayi_key = ""
        if isinstance(info, dict) and info:
            phone = "".join(filter(str.isdigit, str(info.get("tel", "") or info.get("telefon", ""))))[-10:]
        else:
            phone = self.partner_phone_by_name(normalized_name)
        self.f_tel.setText(phone)

    def partner_info_by_key(self, key):
        key = str(key or "")
        if not key:
            return {}
        data = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
        if not isinstance(data, dict):
            data = safe_dict_parse(db.child("users").child(self.user_id).child("sabit_bayiler").get(self.token).val() or {})
        info = data.get(key) if isinstance(data, dict) else {}
        return info if isinstance(info, dict) else {}

    def partner_record_key_by_name(self, name):
        target = self.normalize_upper(name)
        data = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
        if not isinstance(data, dict):
            data = safe_dict_parse(db.child("users").child(self.user_id).child("sabit_bayiler").get(self.token).val() or {})
        if isinstance(data, dict):
            for key, info in data.items():
                if isinstance(info, dict) and self.normalize_upper(info.get("ad", "")) == target:
                    return key, info
        return None, None

    def selected_partner_from_combo(self):
        name = self.normalize_upper(self.combo_bayi.currentText()).strip()
        current_key = str(getattr(self, "selected_bayi_key", "") or "")
        current_info = self.partner_info_by_key(current_key)
        current_name = self.normalize_upper(current_info.get("ad", "")).strip() if current_info else ""
        if current_key and current_name == name:
            return name, current_key, current_info

        key, info = self.partner_record_key_by_name(name)
        if not self.ensure_write_connection("Bayi güncelleme"):
            return

        if key:
            self.selected_bayi_key = str(key)
            return name, str(key), info if isinstance(info, dict) else {}

        self.selected_bayi_key = ""
        return name, "", {}

    def open_bayi_list_menu(self, pos):
        item = self.list_bayiler.itemAt(pos)
        if not item:
            return
        bayi_adi = item.text()
        menu = QMenu(self)
        smart_action = menu.addAction("💎 Akıllı Bayi Kartı")
        view_action = menu.addAction("👁️ Detay Görüntüle")
        edit_action = menu.addAction("Düzenle")
        menu.addSeparator()
        delete_action = menu.addAction("Sil")
        action = menu.exec(self.list_bayiler.mapToGlobal(pos))
        try:
            if action == smart_action:
                self.show_bayi_smart_card(bayi_adi)
            elif action == view_action:
                self.show_bayi_detail(bayi_adi)
            elif action == edit_action:
                self.edit_bayi_info(bayi_adi)
            elif action == delete_action:
                self.list_bayiler.setCurrentItem(item)
                self.manuel_bayi_sil()
        except Exception as e:
            QMessageBox.warning(self, "Bayi Detayı", f"Bayi bilgisi açılırken hata oluştu:\n{e}")

    def bayi_records_for_name(self, bayi_adi):
        target = self.normalize_upper(bayi_adi)
        key, _ = self.partner_record_key_by_name(bayi_adi)
        key = str(key or "")
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        records = []
        for rec_id, rec in data.items():
            if not isinstance(rec, dict) or not self.is_bayi_record(rec):
                continue
            rec_key = str(rec.get("bayi_key", "") or rec.get("bayi_id", "") or "")
            same_key = key and rec_key == key
            same_name = self.normalize_upper(rec.get("m", "")) == target
            if same_key or (not key and same_name):
                records.append((rec_id, rec))
        return records

    def show_bayi_detail(self, bayi_adi):
        phone = self.partner_phone_by_name(bayi_adi) or "Telefon yok"
        records = self.bayi_records_for_name(bayi_adi)
        addresses = sorted({self.record_address_text(rec) for _, rec in records if self.record_address_text(rec)})
        key, info = self.partner_record_key_by_name(bayi_adi)
        if isinstance(info, dict):
            partner_address = str(info.get("adres", "") or info.get("address", "") or "").strip()
            if partner_address:
                addresses.append(partner_address)
        total = sum(safe_float(rec.get("masraf", "0")) for _, rec in records)
        paid = sum(safe_float(rec.get("masraf", "0")) for _, rec in records if rec.get("odeme_durumu") == "Ödendi")
        unpaid = max(0.0, total - paid)
        recent = sorted(records, key=lambda item: self.parse_date_value(item[1].get("z", "")), reverse=True)[:8]
        html = f"""
        <div style='line-height:1.55;'>
            <h3>Bayi Detayı</h3>
            <b>Bayi adı:</b> {bayi_adi}<br>
            <b>Telefon:</b> {phone}<br>
            <b>Adres:</b> {' | '.join(sorted(set(addresses))) if addresses else 'Adres yok'}<br><br>
            <b>Toplam cihaz:</b> {len(records)}<br>
            <b>Toplam cari hacim:</b> {format_money(total, '₺')}<br>
            <b>Ödenen:</b> {format_money(paid, '₺')}<br>
            <b>Kalan borç:</b> {format_money(unpaid, '₺')}<br>
        """
        if recent:
            html += "<br><b>Son işlemler:</b><br>"
            for _, rec in recent:
                html += f"{rec.get('c_no', '-')} | {rec.get('ci', '-')} | {rec.get('d', '-')} | {rec.get('z', '-')}<br>"
        else:
            html += "<br>Bu bayiye bağlı cihaz kaydı bulunmuyor."
        html += "</div>"
        ReadOnlyDialog("Bayi Detayı", html, self).exec()

    def show_bayi_smart_card(self, bayi_adi):
        display_name = self.normalize_upper(bayi_adi).strip()
        records = self.bayi_records_for_name(display_name)
        key, info = self.partner_record_key_by_name(display_name)
        phone = self.partner_phone_by_name(display_name) or ""
        addresses = sorted({self.record_address_text(rec) for _, rec in records if self.record_address_text(rec)})
        if isinstance(info, dict):
            partner_phone = "".join(filter(str.isdigit, str(info.get("tel", "") or info.get("telefon", ""))))[-10:]
            if partner_phone:
                phone = partner_phone
            partner_address = str(info.get("adres", "") or info.get("address", "") or "").strip()
            if partner_address:
                addresses.append(partner_address)

        total = sum(safe_float(rec.get("masraf", "0")) for _, rec in records)
        paid = sum(safe_float(rec.get("masraf", "0")) for _, rec in records if rec.get("odeme_durumu") == "Ödendi")
        unpaid = max(0.0, total - paid)
        active = 0
        delivered = 0
        returned = 0
        delivery_waiting = 0
        return_waiting = 0
        warranty_active = 0
        first_date = None
        last_date = None
        fault_counts = {}
        device_counts = {}
        payment_breakdown = {"Nakit": 0.0, "Kart": 0.0, "EFT": 0.0}
        today = datetime.date.today()

        for _, rec in records:
            delivered_ok, is_iade = self.is_delivered_record(rec)
            status_blob = self.normalize_upper(f"{rec.get('d', '')} {rec.get('teslim_durumu', '')}").replace("İ", "I")
            if delivered_ok:
                if is_iade:
                    returned += 1
                else:
                    delivered += 1
            else:
                active += 1
                if "IADE" in status_blob and "BEKLIYOR" in status_blob:
                    return_waiting += 1
                elif "TESLIM" in status_blob and "BEKLIYOR" in status_blob:
                    delivery_waiting += 1

            if rec.get("odeme_durumu") == "Ödendi":
                amount = safe_float(rec.get("masraf", "0"))
                method = self.normalize_upper(rec.get("odeme_tipi", "Nakit"))
                if "KART" in method:
                    payment_breakdown["Kart"] += amount
                elif "EFT" in method or "HAVALE" in method:
                    payment_breakdown["EFT"] += amount
                else:
                    payment_breakdown["Nakit"] += amount

            warranty_until = str(rec.get("garanti_bitis", "") or "")
            if warranty_until:
                try:
                    if datetime.datetime.strptime(warranty_until, "%d.%m.%Y").date() >= today:
                        warranty_active += 1
                except:
                    pass

            dt = self.parse_date_value(rec.get("z", ""))
            if dt != datetime.datetime.min:
                first_date = dt if first_date is None or dt < first_date else first_date
                last_date = dt if last_date is None or dt > last_date else last_date

            for fault in self.get_faults(rec):
                fault_counts[fault] = fault_counts.get(fault, 0) + 1
            device = self.normalize_upper(rec.get("ci", "")).strip()
            if device:
                device_counts[device] = device_counts.get(device, 0) + 1

        p = self.dialog_html_palette()
        cell_style = f"background-color:{p['panel']}; color:{p['text']}; border:1px solid {p['border']}; padding:10px;"
        label_style = f"color:{p['muted']}; font-size:12px; font-weight:700;"
        value_style = f"color:{p['accent']}; font-size:24px; font-weight:900;"
        row_td_style = f"border:1px solid {p['border']}; padding:6px; color:{p['text']};"
        recent = sorted(records, key=lambda item: self.parse_date_value(item[1].get("z", "")), reverse=True)[:10]
        recent_rows = ""
        for rec_id, rec in recent:
            amount = safe_float(rec.get("masraf", "0"))
            payment = rec.get("odeme_durumu", "Ödenmedi")
            if payment == "Ödendi":
                payment = f"{payment} ({rec.get('odeme_tipi', 'Nakit')})"
            recent_rows += (
                f"<tr>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('c_no', rec_id)))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('m', display_name)))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('ci', '-')))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('yapilan_islem', rec.get('d', '-')) or '-'))}</td>"
                f"<td style='{row_td_style}'>{format_money(amount, '₺') if amount else '-'}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(payment))}</td>"
                f"<td style='{row_td_style}'>{html.escape(str(rec.get('z', '-')))}</td>"
                f"</tr>"
            )
        if not recent_rows:
            recent_rows = f"<tr><td style='{row_td_style}' colspan='7'>Bu bayiye bağlı cihaz kaydı bulunmuyor.</td></tr>"

        top_faults = sorted(fault_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        top_devices = sorted(device_counts.items(), key=lambda item: item[1], reverse=True)[:6]
        faults_html = "<br>".join(f"{html.escape(fault)} ({count})" for fault, count in top_faults) or "Henüz arıza istatistiği yok."
        devices_html = "<br>".join(f"{html.escape(device)} ({count})" for device, count in top_devices) or "Henüz cihaz istatistiği yok."
        payment_html = (
            f"<span style='color:#22c55e;'><b>Nakit:</b> {format_money(payment_breakdown['Nakit'], '₺')}</span><br>"
            f"<span style='color:#38bdf8;'><b>Kart:</b> {format_money(payment_breakdown['Kart'], '₺')}</span><br>"
            f"<span style='color:#f59e0b;'><b>EFT:</b> {format_money(payment_breakdown['EFT'], '₺')}</span>"
        )
        account_color = "#22c55e" if unpaid == 0 else "#f59e0b" if unpaid < max(total * 0.35, 1) else "#ef4444"
        account_text = "Cari temiz" if unpaid == 0 else "Açık cari takip edilmeli"

        html_content = f"""
        <div style="font-family:Arial, sans-serif; color:{p['text']}; background-color:{p['bg']}; line-height:1.45;">
            <h2 style="margin:0 0 12px 0; color:{p['accent']};">Akıllı Bayi Kartı</h2>
            <div style="{cell_style}">
                <b>Bayi:</b> {html.escape(str(display_name))}<br>
                <b>Telefon:</b> {html.escape(phone if phone else 'Telefon yok')}<br>
                <b>Adres:</b> {html.escape(' | '.join(sorted(set(addresses))) if addresses else 'Adres yok')}<br>
                <b>İlk kayıt:</b> {first_date.strftime('%d.%m.%Y') if first_date else '-'} &nbsp;
                <b>Son işlem:</b> {last_date.strftime('%d.%m.%Y %H:%M') if last_date else '-'}
            </div><br>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                    <td style="{cell_style}"><span style="{label_style}">Toplam Cihaz</span><br><span style="{value_style}">{len(records)}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">Aktif İş</span><br><span style="{value_style}">{active}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">Teslim</span><br><span style="{value_style}">{delivered}</span></td>
                    <td style="{cell_style}"><span style="{label_style}">İade</span><br><span style="{value_style}">{returned}</span></td>
                </tr>
                <tr>
                    <td style="{cell_style}"><span style="{label_style}">Teslim Bekleyen</span><br><b>{delivery_waiting}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">İade Bekleyen</span><br><b>{return_waiting}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Garanti Aktif</span><br><b>{warranty_active}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Cari Durum</span><br><b style="color:{account_color};">{account_text}</b></td>
                </tr>
                <tr>
                    <td style="{cell_style}"><span style="{label_style}">Toplam Cari</span><br><b>{format_money(total, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Ödenen</span><br><b style="color:#22c55e;">{format_money(paid, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Açık Borç</span><br><b style="color:#ef4444;">{format_money(unpaid, '₺')}</b></td>
                    <td style="{cell_style}"><span style="{label_style}">Ödeme Dağılımı</span><br>{payment_html}</td>
                </tr>
            </table>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                    <td style="{cell_style}"><b>En Sık Arızalar</b><br>{faults_html}</td>
                    <td style="{cell_style}"><b>En Çok Gelen Cihazlar</b><br>{devices_html}</td>
                </tr>
            </table>
            <div style="{cell_style}">
                <b>Son Bayi İşlemleri</b>
                <table width="100%" cellspacing="0" cellpadding="6" style="border-collapse:collapse; margin-top:8px; color:{p['text']};">
                    <tr style="background-color:{p['header']};"><th>Kayıt</th><th>Müşteri</th><th>Cihaz</th><th>İşlem</th><th>Ücret</th><th>Ödeme</th><th>Tarih</th></tr>
                    {recent_rows}
                </table>
            </div>
        </div>
        """
        dlg = ReadOnlyDialog("Akıllı Bayi Kartı", html_content, self)
        dlg.resize(900, 720)
        dlg.exec()

    def edit_bayi_info(self, bayi_adi):
        if not self.require_staff_permission("edit_people", "Bayi düzenleme"):
            return
        key, info = self.partner_record_key_by_name(bayi_adi)
        current_phone = ""
        if isinstance(info, dict):
            current_phone = "".join(filter(str.isdigit, str(info.get("tel", "") or info.get("telefon", ""))))[-10:]
        if not current_phone:
            current_phone = self.partner_phone_by_name(bayi_adi)

        dlg = QDialog(self)
        dlg.setWindowTitle("Bayi Düzenle")
        lay = QVBoxLayout(dlg)
        name_input = QLineEdit(self.normalize_upper(bayi_adi))
        name_input.textEdited.connect(lambda text, w=name_input: self.force_uppercase(w, text))
        name_input.setPlaceholderText("Firma/Bayi adı")
        phone_input = QLineEdit(current_phone)
        phone_input.setPlaceholderText("Telefon (opsiyonel)")
        phone_input.setMaxLength(10)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(QLabel("Bayi bilgileri"))
        lay.addWidget(name_input)
        lay.addWidget(phone_input)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        new_name = self.normalize_upper(name_input.text()).strip()
        new_phone = "".join(filter(str.isdigit, phone_input.text()))[-10:]
        if not new_name:
            QMessageBox.warning(self, "Bayi Düzenle", "Bayi adı zorunludur.")
            return

        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        saved_key = str(key or "")
        updates = {}
        for rec_id, rec in data.items():
            if not isinstance(rec, dict) or not self.is_bayi_record(rec):
                continue
            rec_bayi_key = str(rec.get("bayi_key", "") or rec.get("bayi_id", "") or "")
            if saved_key and rec_bayi_key == saved_key:
                updates[rec_id] = {"m": new_name, "t": new_phone, "bayi_key": saved_key, "record_type": "bayi"}
        if not self.confirm_bulk_name_update("Bayi Adı Değişikliği", bayi_adi, new_name, updates, "Yalnızca bu bayiye bağlı bayi_key eşleşen kayıtlar"):
            return

        if key:
            db.child("users").child(self.user_id).child("sabit_bayiler").child(key).update({"ad": new_name, "tel": new_phone}, self.token)
        else:
            res = db.child("users").child(self.user_id).child("sabit_bayiler").push({"ad": new_name, "tel": new_phone}, self.token)
            saved_key = str(res.get("name", "") if isinstance(res, dict) else "")

        for rec_id, update_data in updates.items():
            if not self.update_record_fields(rec_id, update_data, "Bayi bağlı kayıt güncelleme"):
                return
            self.publish_public_status(rec_id)
        self.audit_log(
            "Bayi Güncelleme",
            f"{bayi_adi} -> {new_name}",
            "sabit_bayiler",
            saved_key or key or "",
            before={"ad": bayi_adi},
            after={"ad": new_name, "tel": new_phone, "bagli_kayit": len(updates)}
        )
        self.refresh_all_tables()

    def manuel_bayi_ekle(self):
        if not self.require_staff_permission("edit_people", "Bayi ekleme"):
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Bayi Ekle")
        lay = QVBoxLayout(dlg)
        name_input = QLineEdit()
        name_input.textEdited.connect(lambda text, w=name_input: self.force_uppercase(w, text))
        name_input.setPlaceholderText("Firma/Bayi adı")
        phone_input = QLineEdit()
        phone_input.setPlaceholderText("Telefon (opsiyonel)")
        phone_input.setMaxLength(10)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(QLabel("Bayi bilgileri"))
        lay.addWidget(name_input)
        lay.addWidget(phone_input)
        lay.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            isim = self.normalize_upper(name_input.text()).strip()
            tel = "".join(filter(str.isdigit, phone_input.text()))[-10:]
            if not isim:
                QMessageBox.warning(self, "Bayi Ekle", "Bayi adı zorunludur.")
                return
            payload = {"ad": isim, "tel": tel}
            res = db.child("users").child(self.user_id).child("sabit_bayiler").push(payload, self.token)
            bayi_id = res.get("name", "") if isinstance(res, dict) else ""
            self.audit_log("Bayi Ekleme", f"{isim} eklendi", "sabit_bayiler", bayi_id, after=payload)
            self.refresh_all_tables()

    def manuel_bayi_sil(self):
        if not self.require_staff_permission("edit_people", "Bayi silme"):
            return
        it = self.list_bayiler.currentItem()
        if not it: return
        isim = it.text()
        key, _ = self.partner_record_key_by_name(isim)
        linked_records = self.bayi_records_for_name(isim)
        message = f"{isim} adlı bayiyi silmek istiyor musunuz?"
        if linked_records:
            message += f"\n\nBu bayiye bağlı {len(linked_records)} cihaz kaydı silinmeyecek; müşteri kaydı olarak korunacak."
        if QMessageBox.question(self, "Sil", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return

        deleted_profile = False
        if key:
            deleted_profile = self.soft_delete("sabit_bayiler", key)
        else:
            bayiler = safe_dict_parse(db.child("users").child(self.user_id).child("sabit_bayiler").get(self.token).val() or {})
            if not isinstance(bayiler, dict):
                bayiler = {}
            target = self.normalize_upper(isim)
            for k, v in bayiler.items():
                if not isinstance(v, dict):
                    continue
                if self.normalize_upper(v.get("ad", "")) == target:
                    deleted_profile = self.soft_delete("sabit_bayiler", k) or deleted_profile

        for rec_id, _ in linked_records:
            if not self.update_record_fields(rec_id, {
                "is_bayi": False,
                "record_type": "musteri",
                "bayi_key": ""
            }, "Bayi bağlı kayıt güncelleme"):
                return
            self.publish_public_status(rec_id)

        if not deleted_profile and not linked_records:
            QMessageBox.information(self, "Sil", "Silinecek bayi kaydı bulunamadı.")
            return
        self.audit_log(
            "Bayi Silme",
            f"{isim} silindi. Bağlı {len(linked_records)} cihaz müşteri kaydına çevrildi.",
            "sabit_bayiler",
            key or "",
            before={"ad": isim, "bagli_kayit": len(linked_records)}
        )
        self.refresh_all_tables()

    def hesapla_stok_satis(self):
        try:
            alis = safe_float(self.stk_alis.text())
            kar = safe_float(self.stk_kar.text())
            if alis > 0 and kar >= 0: 
                sat = alis + (alis * kar / 100)
                self.stk_satis.setText(f"{sat:.2f}".replace(".", ","))
        except: 
            pass

    def change_scale(self, text):
        self.set_user_setting("ui_scale", text)
        self.settings.setValue("current_ui_scale", text)
        QMessageBox.information(self, "Bilgi", "Arayüz boyutu kaydedildi. Değişikliğin uygulanması için programı tamamen kapatıp yeniden açın.")

    def change_lang(self, text):
        normalized = "English" if str(text or "").lower().startswith("eng") else "Türkçe"
        self.set_user_setting("lang", normalized)
        if hasattr(self, "lang_cb") and self.lang_cb.currentText() != normalized:
            self.lang_cb.blockSignals(True)
            self.lang_cb.setCurrentText(normalized)
            self.lang_cb.blockSignals(False)
        self.translate_ui()

    def theme_combo_labels(self):
        return self.get_trans(
            ["Dark Theme", "Light Theme", "Ocean Theme", "Emerald Theme", "Graphite Theme"],
            ["Koyu Tema (Dark)", "Açık Tema (Light)", "Okyanus Tema", "Zümrüt Tema", "Grafit Tema"]
        )

    def font_weight_combo_labels(self):
        return self.get_trans(["Normal", "Bold"], ["Normal", "Kalın (Bold)"])

    def receipt_format_combo_labels(self):
        return self.get_trans(
            ["80mm (Standard Receipt)", "56mm (Small Receipt)", "A5 (Half A4 Page)"],
            ["80mm (Standart Fiş)", "56mm (Küçük Fiş)", "A5 (A4 Yarım Sayfa)"]
        )

    def payment_method_options(self):
        return [
            ("Nakit", self.get_trans("Cash", "Nakit")),
            ("Kredi Kartı", self.get_trans("Credit Card", "Kredi Kartı")),
            ("EFT / Havale", self.get_trans("EFT / Bank Transfer", "EFT / Havale")),
        ]

    def populate_payment_method_combo(self, combo, current="Nakit"):
        raw_current = str(current or "Nakit")
        combo.blockSignals(True)
        combo.clear()
        for value, label in self.payment_method_options():
            combo.addItem(label, value)
        idx = combo.findData(raw_current)
        if idx < 0 and ("Kart" in raw_current or "Card" in raw_current):
            idx = combo.findData("Kredi Kartı")
        if idx < 0 and ("EFT" in raw_current or "Havale" in raw_current or "Transfer" in raw_current):
            idx = combo.findData("EFT / Havale")
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def payment_method_from_combo(self, combo):
        data = combo.currentData() if combo is not None else None
        if data:
            return str(data)
        text = str(combo.currentText() if combo is not None else "")
        if "Kart" in text or "Card" in text:
            return "Kredi Kartı"
        if "EFT" in text or "Havale" in text or "Transfer" in text:
            return "EFT / Havale"
        return "Nakit"

    def refresh_language_sensitive_combo_labels(self):
        if hasattr(self, "theme_cb"):
            current_theme = str(self.user_setting_value("theme", "Dark"))
            theme_index = 1 if current_theme == "Light" else 2 if current_theme == "Ocean" else 3 if current_theme == "Emerald" else 4 if current_theme == "Graphite" else 0
            self.theme_cb.blockSignals(True)
            self.theme_cb.clear()
            self.theme_cb.addItems(self.theme_combo_labels())
            self.theme_cb.setCurrentIndex(theme_index)
            self.theme_cb.blockSignals(False)

        if hasattr(self, "font_weight_cb"):
            current_weight = str(self.user_setting_value("font_weight", "Normal"))
            weight_index = 1 if ("Bold" in current_weight or "Kal" in current_weight) else 0
            self.font_weight_cb.blockSignals(True)
            self.font_weight_cb.clear()
            self.font_weight_cb.addItems(self.font_weight_combo_labels())
            self.font_weight_cb.setCurrentIndex(weight_index)
            self.font_weight_cb.blockSignals(False)

        if hasattr(self, "print_format_cb"):
            current_format = str(self.user_setting_value("print_format", "80mm"))
            format_index = 2 if ("A5" in current_format or "Half" in current_format or "Yarım" in current_format or "Yarim" in current_format) else 1 if ("56mm" in current_format or "58mm" in current_format) else 0
            self.print_format_cb.blockSignals(True)
            self.print_format_cb.clear()
            self.print_format_cb.addItems(self.receipt_format_combo_labels())
            self.print_format_cb.setCurrentIndex(format_index)
            self.print_format_cb.blockSignals(False)

        if hasattr(self, "k_odeme_tipi"):
            self.populate_payment_method_combo(self.k_odeme_tipi, self.payment_method_from_combo(self.k_odeme_tipi))

    def live_calc(self, text, rate, label):
        try: 
            label.setText(f"<b>{format_money(safe_float(text) * rate, '₺')}</b>")
        except: 
            label.setText("0 ₺")

    def live_calc_rev(self, text, rate, label):
        try: 
            label.setText(f"<b>{format_money(safe_float(text) / rate, '$')}</b>")
        except: 
            label.setText("0 $")

    def save_tray_setting(self): 
        self.set_user_setting("close_to_tray", "true" if self.tray_cb.isChecked() else "false")
        
    def change_theme(self, text): 
        if "Light" in text or "Açık" in text:
            t = "Light"
        elif "Okyanus" in text or "Ocean" in text:
            t = "Ocean"
        elif "Zümrüt" in text or "Emerald" in text:
            t = "Emerald"
        elif "Grafit" in text or "Graphite" in text:
            t = "Graphite"
        else:
            t = "Dark"
        self.set_user_setting("theme", t)
        self.manager.setStyleSheet(get_theme_stylesheet(t))
        if hasattr(self, "sidebar"):
            self.sidebar.setStyleSheet(self.sidebar_stylesheet())
        self.apply_settings_panel_style()
        self.apply_admin_panel_style()
        self.apply_staff_gate_style()
        if hasattr(self.manager, "login_screen"):
            self.manager.login_screen.refresh_theme(t)
        
    def change_logo(self):
        fn, _ = QFileDialog.getOpenFileName(self, "Logo Seç", "", "Resim (*.png *.jpg *.jpeg)")
        if fn: 
            self.session_custom_logo = fn
            self.set_user_setting("custom_logo", fn)
            self.update_user_logo_label()
            if hasattr(self.manager, 'login_screen'): 
                self.manager.login_screen.update_avatar(use_custom=False)

    def save_shop_profile(self):
        name = self.normalize_upper(self.shop_name_in.text()).strip()
        address = self.normalize_upper(self.shop_address_in.text()).strip()
        self.receipt_shop_name = name
        self.receipt_shop_address = address
        self.set_user_setting("receipt_shop_name", name)
        self.set_user_setting("receipt_shop_address", address)
        self.update_title_company_name()
        QMessageBox.information(self, "Kaydedildi", "Fiş bayi bilgileri bu kullanıcı için kaydedildi.")

    def max_existing_record_sequence(self, year=None):
        year = int(year or datetime.datetime.now().year)
        prefix = f"MF-{year}-"
        max_no = 0
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        for rec in data.values():
            if not isinstance(rec, dict):
                continue
            code = str(rec.get("c_no", "") or "").strip()
            if not code.startswith(prefix):
                continue
            try:
                max_no = max(max_no, int(code.split("-")[-1]))
            except Exception:
                pass
        return max_no

    def cloud_record_counter_value(self, year=None):
        year = int(year or datetime.datetime.now().year)
        try:
            val = db.child("users").child(self.user_id).child("sayaclar").child("kayit_no").child(str(year)).get(self.token).val()
            return int(safe_float(val))
        except Exception:
            return 0

    def apply_record_number_sequence(self, requested, year=None):
        year = int(year or datetime.datetime.now().year)
        requested = int(safe_float(requested, -1))
        if requested < 0:
            raise ValueError("Geçerli bir sıra numarası girin.")

        existing_max = self.max_existing_record_sequence(year)
        cloud_counter = self.cloud_record_counter_value(year)
        target = max(requested, existing_max, cloud_counter)
        db.child("users").child(self.user_id).child("sayaclar").child("kayit_no").child(str(year)).set(target, self.token)
        self.set_user_setting("record_start_sequence", str(target))
        if hasattr(self, "record_start_in"):
            self.record_start_in.setText(str(target))
        self.audit_log(
            "Kayıt No Ayarı",
            f"{year} yılı kayıt no sırası {target} olarak ayarlandı",
            "sayaclar",
            f"kayit_no/{year}",
            after={"year": year, "counter": target}
        )
        return target

    def save_record_number_start(self):
        year = datetime.datetime.now().year
        raw_value = str(self.record_start_in.text() if hasattr(self, "record_start_in") else "").strip()
        if not raw_value:
            QMessageBox.warning(self, "Kayıt No", "Başlangıç sıra numarası girin.")
            return
        requested = int(safe_float(raw_value, -1))
        if requested < 0:
            QMessageBox.warning(self, "Kayıt No", "Geçerli bir sıra numarası girin.")
            return
        if not self.ensure_write_connection("Kayıt no ayarı"):
            return

        try:
            target = self.apply_record_number_sequence(requested, year)
        except Exception as e:
            try:
                if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                    target = self.apply_record_number_sequence(requested, year)
                else:
                    raise
            except Exception as retry_error:
                QMessageBox.warning(self, "Kayıt No", self.friendly_write_error("Kayıt no ayarı", retry_error))
                return

        next_code = f"MF-{year}-{target + 1:06d}"
        if target != requested:
            QMessageBox.information(
                self,
                "Kayıt No",
                f"Mevcut kayıt/sayaç daha yüksek olduğu için sıra {target} olarak korundu.\n\nBir sonraki kayıt no: {next_code}"
            )
        else:
            QMessageBox.information(self, "Kayıt No", f"Bir sonraki kayıt no: {next_code}")

    def show_record_number_migration_prompt_once(self):
        if getattr(self, "license_blocked", False):
            return
        if str(self.user_setting_value("record_counter_migration_prompt_seen", "false")) == "true":
            return
        if safe_float(self.user_setting_value("record_start_sequence", "0")) > 0:
            self.set_user_setting("record_counter_migration_prompt_seen", "true")
            return
        records = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        record_count = len(records) if isinstance(records, dict) else 0
        if record_count > 250:
            self.set_user_setting("record_counter_migration_prompt_seen", "true")
            return

        year = datetime.datetime.now().year
        cloud_counter = self.cloud_record_counter_value(year)
        if max(record_count, cloud_counter) > 250:
            self.set_user_setting("record_counter_migration_prompt_seen", "true")
            return

        answer = QMessageBox.question(
            self,
            "Kayıt No Geçiş Ayarı",
            "Başka bir programdan MetaFold'a geçiyorsanız eski programdaki son kayıt numaranızı girebilirsiniz.\n\n"
            "Bunu 0 kayıt varken de, birkaç kayıt girdikten sonra da yapabilirsiniz.\n\n"
            f"Örneğin 4000 girerseniz ilk yeni kayıt MF-{year}-004001 olarak başlar.\n\n"
            "Şimdi ayarlamak ister misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        self.set_user_setting("record_counter_migration_prompt_seen", "true")
        if answer != QMessageBox.StandardButton.Yes:
            return

        value, ok = QInputDialog.getText(self, "Kayıt No Geçiş Ayarı", "Eski programdaki son kayıt numarası:", text="4000")
        if not ok:
            return
        requested = int(safe_float(value, -1))
        if requested < 0:
            QMessageBox.warning(self, "Kayıt No", "Geçerli bir sıra numarası girin.")
            return
        if not self.ensure_write_connection("Kayıt no ayarı"):
            return
        try:
            target = self.apply_record_number_sequence(requested, year)
        except Exception as e:
            try:
                if self.is_firebase_auth_error(e) and self.refresh_firebase_token():
                    target = self.apply_record_number_sequence(requested, year)
                else:
                    raise
            except Exception as retry_error:
                QMessageBox.warning(self, "Kayıt No", self.friendly_write_error("Kayıt no ayarı", retry_error))
                return
        QMessageBox.information(self, "Kayıt No", f"Bir sonraki kayıt no: MF-{year}-{target + 1:06d}")

    def check_autostart_registry(self):
        import sys
        if os.name == 'nt':
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_READ)
                value, _ = winreg.QueryValueEx(key, "MetaFoldERP")
                self.startup_cb.setChecked(str(value).strip() == self.autostart_command())
                winreg.CloseKey(key)
            except: 
                self.startup_cb.setChecked(False)

    def autostart_command(self):
        import sys
        if getattr(sys, "frozen", False):
            return f'"{sys.executable}"'
        interpreter = sys.executable
        pythonw = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
        if os.path.exists(pythonw):
            interpreter = pythonw
        script = os.path.abspath(sys.argv[0])
        return f'"{interpreter}" "{script}"'

    def toggle_autostart(self):
        self.set_user_setting("autostart", "true" if self.startup_cb.isChecked() else "false")
        self.apply_autostart_registry(self.startup_cb.isChecked(), show_errors=True)

    def apply_autostart_registry(self, enabled, show_errors=True):
        import sys
        if os.name == 'nt':
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\CurrentVersion\Run', 0, winreg.KEY_SET_VALUE)
                if enabled:
                    winreg.SetValueEx(key, "MetaFoldERP", 0, winreg.REG_SZ, self.autostart_command())
                else:
                    try: 
                        winreg.DeleteValue(key, "MetaFoldERP")
                    except: pass
                winreg.CloseKey(key)
            except Exception as e: 
                if show_errors:
                    QMessageBox.warning(self, "Hata", f"Kayıt defterine yazılamadı: {e}")

    def clear_saved_login_credentials(self):
        for key in ("email", "password", "password_secure"):
            self.settings.remove(key)
        self.settings.setValue("remember", "false")
        self.settings.setValue("auto_login", "false")
        self.settings.sync()

        login_screen = getattr(self.manager, "login_screen", None)
        if login_screen is None:
            return
        for field_name in ("login_email", "login_pass"):
            field = getattr(login_screen, field_name, None)
            if field is not None:
                field.clear()
        for checkbox_name in ("remember_cb", "auto_login_cb"):
            checkbox = getattr(login_screen, checkbox_name, None)
            if checkbox is not None:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)

    def logout_user(self):
        if QMessageBox.question(self, 'Çıkış', "Sistemden çıkış yapmak istiyor musunuz?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                devices_req = db.child("users").child(self.user_id).child("aktif_cihazlar").get(self.token).val() or {}
                devices = safe_dict_parse(devices_req)
                if not isinstance(devices, dict):
                    devices = {}
                import uuid
                my_device_id = str(uuid.getnode())
                for k, v in devices.items():
                    if v == my_device_id: 
                        db.child("users").child(self.user_id).child("aktif_cihazlar").child(k).remove(self.token)
            except: pass
            
            if getattr(self, 'stream_worker', None): 
                self.stream_worker.stop()
                self.stream_worker.quit()
                self.stream_worker.wait()
                
            self.clear_saved_login_credentials()
            self.manager.setCurrentIndex(0)
            self.manager.login_screen.lbl_status.setText("")
            self.manager.login_screen.update_avatar(use_custom=False)
            self.manager.login_screen.refresh_theme("Dark")
            self.manager.setFixedSize(700, 520)
            if hasattr(self.manager, "center_on_active_screen"):
                self.manager.center_on_active_screen(force=True, reset_user_position=True)
            self.manager.removeWidget(self)
            self.deleteLater()

    def add_kasa(self):
        if not self.require_staff_permission("cash_add", "Kasa işlemi"):
            return
        tip = self.k_tip.currentText()
        odeme_tipi = self.payment_method_from_combo(getattr(self, "k_odeme_tipi", None))
        aciklama = self.normalize_upper(self.k_aciklama.text()).strip()
        tutar = safe_float(self.k_tutar.text())
        if not aciklama or tutar == 0:
            return

        payload = {
            "t": datetime.datetime.now().strftime("%d.%m.%Y"),
            "tip": tip,
            "odeme_tipi": odeme_tipi,
            "aciklama": aciklama,
            "tutar": tutar
        }
        res = db.child("users").child(self.user_id).child("kasa").push(payload, self.token)
        cash_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Kasa İşlemi", f"{tip} ({odeme_tipi}): {aciklama} - {format_money(tutar, '₺')}", "kasa", cash_id, after=payload)
        self.k_aciklama.clear()
        self.k_tutar.clear()
        self.refresh_all_tables()

    def add_stok(self):
        if not self.require_staff_permission("stock_add", "Stok ekleme"):
            return
        barkod = self.normalize_upper(self.stk_barkod.text()).strip()
        ad = self.normalize_upper(self.stk_ad.text()).strip()
        alis = safe_float(self.stk_alis.text())
        satis = safe_float(self.stk_satis.text())
        adet = safe_float(self.stk_adet.text())
        birim = self.stk_birim.currentText()
        if not ad:
            return

        stok_kodu = self.next_stock_code()
        payload = {
            "stok_kodu": stok_kodu,
            "barkod": barkod,
            "ad": ad,
            "alis": alis,
            "satis": satis,
            "adet": adet,
            "birim": birim
        }
        res = db.child("users").child(self.user_id).child("stok").push(payload, self.token)
        stock_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Stok Ekleme", f"{stok_kodu} - {ad} eklendi. Adet: {self.format_quantity(adet)}", "stok", stock_id, after=payload)
        self.stk_barkod.clear()
        self.stk_ad.clear()
        self.stk_alis.clear()
        self.stk_satis.clear()
        self.stk_adet.clear()
        self.stk_kar.clear()
        self.refresh_all_tables()

    def find_stock_by_barcode_or_code(self, code):
        code_norm = self.normalize_upper(code).strip()
        data = safe_dict_parse(getattr(self, "stok_data", {}))
        if not isinstance(data, dict):
            data = {}
        for sid, item in data.items():
            if not isinstance(item, dict):
                continue
            values = [
                item.get("barkod", ""),
                item.get("barcode", ""),
                self.stock_code_for_item(sid, item),
                item.get("stok_kodu", ""),
            ]
            if any(self.normalize_upper(v).strip() == code_norm for v in values if v):
                return sid, item
        return None, None

    def update_stock_barcode_button(self):
        if not hasattr(self, "btn_stk_barcode") or not hasattr(self, "stk_barcode_mode"):
            return
        mode = self.stk_barcode_mode.currentData()
        self.btn_stk_barcode.setText("Ürünü Sorgula" if mode == "query" else "Barkodu İşle")

    def show_stock_barcode_details(self, sid, item, query_code=""):
        if not isinstance(item, dict):
            QMessageBox.warning(self, "Stok", "Ürün bilgisi okunamadı.")
            return
        birim = item.get("birim", "₺") or "₺"
        alis = safe_float(item.get("alis", "0"))
        satis = safe_float(item.get("satis", "0"))
        adet = safe_float(item.get("adet", "0"))
        stok_kodu = self.stock_code_for_item(sid, item)
        barkod = item.get("barkod", "") or item.get("barcode", "") or query_code
        kar = satis - alis
        stok_degeri = alis * adet

        rows = [
            ("Stok Kodu", stok_kodu),
            ("Parça Adı", item.get("ad", "")),
            ("Barkod", barkod),
            ("Stok Adedi", self.format_quantity(adet)),
            ("Alış Fiyatı", format_money(alis, birim)),
            ("Satış Fiyatı", format_money(satis, birim)),
            ("Birim Kar", format_money(kar, birim)),
            ("Stok Alış Değeri", format_money(stok_degeri, birim)),
        ]
        html_rows = "".join(
            "<tr>"
            f"<td style='padding:8px 12px; color:#9ca3af; width:150px;'>{html.escape(label)}</td>"
            f"<td style='padding:8px 12px; font-weight:700;'>{html.escape(str(value or '-'))}</td>"
            "</tr>"
            for label, value in rows
        )
        content = (
            "<h2 style='margin:0 0 12px 0; color:#38bdf8;'>Ürün Sorgulama</h2>"
            "<table style='width:100%; border-collapse:collapse;'>"
            f"{html_rows}"
            "</table>"
        )
        ReadOnlyDialog("Barkod Ürün Bilgisi", content, self).exec()

    def adjust_stock_quantity(self, sid, item, delta, reason="Barkod"):
        current_qty = safe_float(item.get("adet", "0"))
        new_qty = current_qty + delta
        if new_qty < 0:
            QMessageBox.warning(self, "Stok Yetersiz", f"Mevcut stok: {self.format_quantity(current_qty)}")
            return False
        db.child("users").child(self.user_id).child("stok").child(sid).update({"adet": new_qty}, self.token)
        self.audit_log(
            "Stok Hareketi",
            f"{reason}: {item.get('ad', '')} {self.format_quantity(current_qty)} -> {self.format_quantity(new_qty)}",
            "stok",
            sid,
            before={"adet": current_qty},
            after={"adet": new_qty}
        )
        self.set_sync_status(f"{reason}: {item.get('ad', '')} stok {self.format_quantity(new_qty)}", "#22c55e")
        self.refresh_all_tables()
        return True

    def create_stock_from_barcode(self, barcode):
        dlg = QDialog(self)
        dlg.setWindowTitle("Barkoddan Yeni Stok")
        lay = QVBoxLayout(dlg)
        name_in = QLineEdit()
        name_in.setPlaceholderText("Parça adı")
        name_in.textEdited.connect(lambda text, w=name_in: self.force_uppercase(w, text))
        buy_in = QLineEdit()
        buy_in.setPlaceholderText("Alış fiyatı")
        sell_in = QLineEdit()
        sell_in.setPlaceholderText("Satış fiyatı")
        qty_in = QLineEdit("1")
        qty_in.setPlaceholderText("Başlangıç adedi")
        unit_cb = QComboBox()
        unit_cb.addItems(["₺", "$"])
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(QLabel(f"Barkod: {barcode}"))
        lay.addWidget(name_in)
        lay.addWidget(buy_in)
        lay.addWidget(sell_in)
        lay.addWidget(qty_in)
        lay.addWidget(unit_cb)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name = self.normalize_upper(name_in.text()).strip()
        if not name:
            QMessageBox.warning(self, "Stok", "Parça adı zorunludur.")
            return
        payload = {
            "stok_kodu": self.next_stock_code(),
            "barkod": self.normalize_upper(barcode).strip(),
            "ad": name,
            "alis": safe_float(buy_in.text()),
            "satis": safe_float(sell_in.text()),
            "adet": safe_float(qty_in.text(), 1),
            "birim": unit_cb.currentText()
        }
        res = db.child("users").child(self.user_id).child("stok").push(payload, self.token)
        stock_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Barkoddan Stok Ekleme", f"{payload.get('stok_kodu')} - {name}", "stok", stock_id, after=payload)
        self.refresh_all_tables()

    def process_stock_barcode(self):
        barcode = self.normalize_upper(self.stk_barcode_input.text()).strip()
        if not barcode:
            return
        mode = self.stk_barcode_mode.currentData()
        sid, item = self.find_stock_by_barcode_or_code(barcode)
        if not item:
            if mode == "query":
                QMessageBox.warning(self, "Ürün Bulunamadı", "Bu barkoda bağlı stok ürünü bulunamadı.")
                self.stk_barcode_input.clear()
                return
            if QMessageBox.question(self, "Barkod Bulunamadı", "Bu barkod stokta kayıtlı değil. Yeni stok kartı oluşturulsun mu?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.create_stock_from_barcode(barcode)
            self.stk_barcode_input.clear()
            return
        if mode == "query":
            self.show_stock_barcode_details(sid, item, barcode)
            self.stk_barcode_input.clear()
            return
        delta = 1 if mode == "in" else -1
        if self.adjust_stock_quantity(sid, item, delta, "Barkod işlemi"):
            self.stk_barcode_input.clear()

    def send_whatsapp(self, kid):
        v = db.child("users").child(self.user_id).child("kayitlar").child(kid).get(self.token).val()
        if not v:
            return

        tel = "".join(filter(str.isdigit, v.get("t", "")))
        if tel.startswith("0"):
            tel = tel[1:]

        if len(tel) != 10:
            QMessageBox.warning(self, "Hata", "Geçerli bir 10 haneli telefon numarası bulunamadı!")
            return

        durum = v.get("d", "")
        if "Parça Bekliyor" in durum:
            template = self.user_setting_value("tpl_part", "Merhaba {musteri}, {cihaz} cihazınız için parça beklenmektedir. {firma}")
        elif durum in ["Teslim Edildi", "İade Edildi", "Hazır", "Hazir", "İşlemleri Tamamlandı"]:
            template = self.user_setting_value("tpl_ready", "Merhaba {musteri}, {cihaz} cihazınızın işlemleri tamamlanmıştır. {firma}")
        else:
            template = self.user_setting_value("tpl_waiting", "Merhaba {musteri}, {firma} firmasından ulaşıyorum. {cihaz} cihazınız hakkında bilgilendirme:")
        msg = self.render_message_template(template, v)

        webbrowser.open(f"https://wa.me/90{tel}?text={requests.utils.quote(msg)}")

    def open_stok_menu(self, pos, table):
        if not self.require_staff_permission("edit_stock", "Stok işlemi"):
            return
        row = table.rowAt(pos.y())
        if row < 0:
            return

        kid_item = table.item(row, 0)
        if not kid_item:
            return

        kid = kid_item.text()
        menu = QMenu(self)
        stock_out = menu.addAction(self.get_trans("Stock Out", "Stoktan Çıkış Yap"))
        assign_barcode = menu.addAction("🏷️ Barkod Ata / Değiştir")
        delete_stock = menu.addAction(self.get_trans("Delete Stock", "Sil (Çöp Kutusuna Gönder)"))
        action = menu.exec(QCursor.pos())

        if action == delete_stock:
            if QMessageBox.question(self, "Emin misiniz?", "Stok kaydı silinecek. Emin misiniz?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                self.soft_delete("stok", kid)
                self.refresh_all_tables()
        elif action == stock_out:
            v = db.child("users").child(self.user_id).child("stok").child(kid).get(self.token).val()
            if not v:
                return
            mevcut_adet = safe_float(v.get("adet", "0"))
            adet_str, ok = QInputDialog.getText(self, "Çıkış Yap", f"Mevcut Adet: {self.format_quantity(mevcut_adet)}\nKaç adet düşülecek?")
            if ok:
                yeni_adet = max(0.0, mevcut_adet - safe_float(adet_str))
                db.child("users").child(self.user_id).child("stok").child(kid).update({"adet": str(yeni_adet)}, self.token)
                self.audit_log(
                    "Stok Çıkışı",
                    f"{v.get('ad', '')} stoktan çıkış: {self.format_quantity(mevcut_adet)} -> {self.format_quantity(yeni_adet)}",
                    "stok",
                    kid,
                    before={"adet": mevcut_adet},
                    after={"adet": yeni_adet}
                )
                self.refresh_all_tables()
        elif action == assign_barcode:
            v = db.child("users").child(self.user_id).child("stok").child(kid).get(self.token).val() or {}
            barcode, ok = QInputDialog.getText(self, "Barkod", "Barkod:", text=str(v.get("barkod", "") or v.get("barcode", "")))
            if ok:
                new_barcode = self.normalize_upper(barcode).strip()
                db.child("users").child(self.user_id).child("stok").child(kid).update({"barkod": new_barcode}, self.token)
                self.audit_log("Stok Barkod", f"{v.get('ad', '')} barkod güncellendi", "stok", kid, before={"barkod": v.get("barkod", "") or v.get("barcode", "")}, after={"barkod": new_barcode})
                self.refresh_all_tables()

    def open_kasa_menu(self, pos, table):
        if not self.require_staff_permission("cash_add", "Kasa hareketi düzenleme"):
            return
        row = table.rowAt(pos.y())
        if row < 0:
            return

        kid_item = table.item(row, 0)
        if not kid_item:
            return

        menu = QMenu(self)
        delete_transaction = menu.addAction(self.get_trans("Delete Transaction", "Sil (Çöp Kutusuna Gönder)"))
        if menu.exec(QCursor.pos()) == delete_transaction:
            self.soft_delete("kasa", kid_item.text())
            self.refresh_all_tables()

    def open_trash_menu(self, pos, table):
        row = table.rowAt(pos.y())
        menu = QMenu(self)
        restore_action = permanent_delete_action = None
        module = item_id = None
        if row >= 0:
            hidden_item = table.item(row, 0)
            if hidden_item and "|" in hidden_item.text():
                module, item_id = hidden_item.text().split("|", 1)
                restore_action = menu.addAction("Geri Yükle")
                permanent_delete_action = menu.addAction("Kalıcı Olarak Sil")
                menu.addSeparator()
        delete_all_action = menu.addAction("Tümünü Kalıcı Olarak Sil")
        action = menu.exec(QCursor.pos())

        if restore_action and action == restore_action:
            item_info = db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).get(self.token).val()
            if item_info and "data" in item_info:
                db.child("users").child(self.user_id).child(module).child(item_id).set(item_info["data"], self.token)
                db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).remove(self.token)
                if module == "kayitlar":
                    self.apply_stream_record_change(item_id, item_info.get("data"), replace=True)
                    self.touch_record_sync_meta(item_id, "upsert")
                self.audit_log("Çöp Kutusu", f"{module} kaydı geri yüklendi", module, item_id, after=item_info.get("data"))
                self.refresh_all_tables()
        elif permanent_delete_action and action == permanent_delete_action:
            if QMessageBox.question(self, "Uyarı", "Bu veri kesinlikle geri getirilemez. Silinsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                item_info = db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).get(self.token).val()
                db.child("users").child(self.user_id).child("cop_kutusu").child(module).child(item_id).remove(self.token)
                self.audit_log("Kalıcı Silme", f"{module} kaydı çöp kutusundan kalıcı silindi", module, item_id, before=item_info)
                self.refresh_all_tables()
        elif action == delete_all_action:
            if QMessageBox.question(self, "Kalıcı Silme", "Çöp kutusundaki tüm veriler kalıcı olarak silinecek.\n\nBu işlem geri alınamaz. Devam edilsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                trash_snapshot = db.child("users").child(self.user_id).child("cop_kutusu").get(self.token).val()
                db.child("users").child(self.user_id).child("cop_kutusu").remove(self.token)
                self.audit_log("Kalıcı Silme", "Çöp kutusundaki tüm veriler kalıcı silindi", "cop_kutusu", "all", before=trash_snapshot)
                self.refresh_all_tables()

    def add_wholesaler(self):
        n = self.normalize_upper(self.firm_in.text()).strip()
        if n: 
            payload = {"ad": n}
            res = db.child("users").child(self.user_id).child("firmalar").push(payload, self.token)
            firm_id = res.get("name", "") if isinstance(res, dict) else ""
            self.audit_log("Toptancı Ekleme", f"{n} eklendi", "firmalar", firm_id, after=payload)
            self.firm_in.clear()
            self.load_wholesalers()

    def generate_record_code(self):
        year = datetime.datetime.now().year
        next_no = self.reserve_next_record_sequence(year)
        return f"MF-{year}-{next_no:06d}"

    def reserve_next_record_sequence(self, year=None):
        year = int(year or datetime.datetime.now().year)
        db_url = get_firebase_config().get("databaseURL", "").rstrip("/")
        url = f"{db_url}/users/{self.user_id}/sayaclar/kayit_no/{year}.json"
        headers = {"X-Firebase-ETag": "true"}
        last_error = None
        for attempt in range(8):
            try:
                response = requests.get(url, params={"auth": self.token}, headers=headers, timeout=8)
                if response.status_code in [401, 402, 403] and self.refresh_firebase_token():
                    response = requests.get(url, params={"auth": self.token}, headers=headers, timeout=8)
                response.raise_for_status()
                etag = response.headers.get("ETag")
                if not etag:
                    raise RuntimeError("Firebase kayit no kilidi alinamadi.")

                cloud_no = int(safe_float(response.json()))
                local_start = int(safe_float(self.user_setting_value("record_start_sequence", "0")))
                existing_max = self.max_existing_record_sequence(year)
                next_no = max(cloud_no, local_start, existing_max) + 1

                update = requests.put(
                    url,
                    params={"auth": self.token},
                    headers={"if-match": etag},
                    json=next_no,
                    timeout=8
                )
                if update.status_code == 412:
                    time.sleep(0.08 + (attempt * 0.05))
                    continue
                if update.status_code in [401, 402, 403] and self.refresh_firebase_token():
                    update = requests.put(
                        url,
                        params={"auth": self.token},
                        headers={"if-match": etag},
                        json=next_no,
                        timeout=8
                    )
                update.raise_for_status()
                self.set_user_setting("record_start_sequence", str(next_no))
                return next_no
            except Exception as exc:
                last_error = exc
                time.sleep(0.08 + (attempt * 0.05))
        raise RuntimeError(f"Kayit no sayaci guvenli sekilde ayrilamadi: {last_error}")

    def ensure_unique_record_code(self, kid, code):
        code = str(code or "").strip()
        if not kid or not code:
            return code
        try:
            data = safe_dict_parse(self.read_user_section("kayitlar", default={}))
        except Exception:
            data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        duplicate = any(
            rec_id != kid and isinstance(rec, dict) and str(rec.get("c_no", "")).strip() == code
            for rec_id, rec in data.items()
        )
        if not duplicate:
            return code
        suffix = str(kid)[-5:].upper().replace("-", "")
        unique_code = f"{code}-{suffix}"
        try:
            self.update_record_fields(kid, {"c_no": unique_code}, "Kayıt no güncelleme", require_connection=False)
        except Exception:
            pass
        return unique_code

    def show_new_record_output_dialog(self, record_data):
        dlg = QDialog(self)
        dlg.setWindowTitle("Kayıt Başarılı")
        dlg.resize(520, 280)
        lay = QVBoxLayout(dlg)
        title = QLabel(f"<b>Cihaz başarıyla eklendi</b><br><span style='color:#94a3b8;'>Kayıt No: {html.escape(str(record_data.get('c_no', '') or '-'))}</span>")
        title.setWordWrap(True)
        title.setStyleSheet("font-size:15px;")
        option_box = QGroupBox("Çıktılar")
        option_lay = QHBoxLayout(option_box)
        cb_receipt = QCheckBox("Fiş")
        cb_label = QCheckBox("Etiket")
        cb_receipt.setChecked(True)
        cb_label.setChecked(True)
        option_lay.addWidget(cb_receipt)
        option_lay.addWidget(cb_label)
        option_lay.addStretch()

        btn_print_selected = QPushButton("🖨️ Seçili Çıktıları Yazdır")
        btn_print_selected.setObjectName("PrimaryBtn")
        btn_preview = QPushButton("👁️ Önizle")
        btn_pdf = QPushButton("📄 PDF")
        btn_continue = QPushButton("Devam")
        btn_continue.setObjectName("SecondaryBtn")

        def print_selected():
            if not cb_receipt.isChecked() and not cb_label.isChecked():
                QMessageBox.information(self, "Çıktı", "Yazdırmak için fiş veya etiket seçin.")
                return
            if cb_receipt.isChecked():
                self.print_receipt(record_data, "print")
            if cb_label.isChecked():
                self.print_device_label(record_data, "print")
            dlg.accept()

        def show_preview_menu():
            menu = QMenu(dlg)
            receipt_action = menu.addAction("Fişi Göster")
            label_action = menu.addAction("Etiketi Göster")
            action = menu.exec(QCursor.pos())
            if action == receipt_action:
                self.print_receipt(record_data, "preview")
            elif action == label_action:
                self.print_device_label(record_data, "preview")

        def show_pdf_menu():
            menu = QMenu(dlg)
            receipt_action = menu.addAction("Fişi PDF Kaydet")
            label_action = menu.addAction("Etiketi PDF Kaydet")
            action = menu.exec(QCursor.pos())
            if action == receipt_action:
                self.print_receipt(record_data, "pdf")
            elif action == label_action:
                self.print_device_label(record_data, "pdf")

        btn_print_selected.clicked.connect(print_selected)
        btn_preview.clicked.connect(show_preview_menu)
        btn_pdf.clicked.connect(show_pdf_menu)
        btn_continue.clicked.connect(dlg.accept)

        secondary_row = QHBoxLayout()
        secondary_row.addWidget(btn_preview)
        secondary_row.addWidget(btn_pdf)
        secondary_row.addStretch()
        secondary_row.addWidget(btn_continue)
        lay.addWidget(title)
        lay.addWidget(option_box)
        lay.addWidget(btn_print_selected)
        lay.addLayout(secondary_row)
        lay.addStretch()
        dlg.exec()

    def save_device(self):
        if not self.require_staff_permission("new_record", "Cihaz kaydı"):
            return
        is_bayi = self.cb_bayi_kayit.isChecked()
        if is_bayi:
            m, bayi_key, selected_partner_info = self.selected_partner_from_combo()
            customer_key = ""
        else:
            bayi_key = ""
            selected_partner_info = {}
            m = self.normalize_upper(self.f_ad.text()).strip()
            customer_key = self.customer_key_for_new_record(m, self.f_tel.text())
        t = "".join(filter(str.isdigit, self.f_tel.text()))
        if is_bayi and selected_partner_info:
            t = "".join(filter(str.isdigit, str(selected_partner_info.get("tel", "") or selected_partner_info.get("telefon", ""))))
        if len(t) > 10:
            t = t[-10:]
        c = self.normalize_upper(self.f_cihaz.text()).strip()
        a = self.normalize_upper(self.f_ariza.text()).strip()
        arizalar = list(self.extra_faults)
        if a and a not in arizalar:
            arizalar.insert(0, a)
        a = arizalar[0] if arizalar else ""
        initial_note = self.normalize_upper(self.f_not.toPlainText()).strip() if hasattr(self, "f_not") else ""
        yaklasik = safe_float(self.f_yaklasik.text())
        garanti_gun = int(safe_float(self.f_garanti_gun.text(), safe_float(self.user_setting_value("default_warranty_days", "30")))) if self.cb_garanti_ver.isChecked() else 0
        garanti_bitis = (datetime.datetime.now() + datetime.timedelta(days=garanti_gun)).strftime("%d.%m.%Y") if garanti_gun > 0 else ""
        if is_bayi and not bayi_key:
            key_by_name, _ = self.partner_record_key_by_name(m)
            bayi_key = str(key_by_name or "")
        
        if not m or not c: 
            QMessageBox.warning(self, "Uyarı", "Müşteri/Bayi ve Cihaz zorunludur!")
            return

        if not self.ensure_write_connection("Cihaz kaydı"):
            return
            
        try:
            if is_bayi and m and not bayi_key:
                try:
                    res_partner = db.child("users").child(self.user_id).child("sabit_bayiler").push({"ad": m, "tel": t}, self.token)
                    bayi_key = str(res_partner.get("name", "") if isinstance(res_partner, dict) else "")
                    if bayi_key:
                        self.sabit_bayiler_data = safe_dict_parse(getattr(self, "sabit_bayiler_data", {}))
                        if not isinstance(self.sabit_bayiler_data, dict):
                            self.sabit_bayiler_data = {}
                        self.sabit_bayiler_data[bayi_key] = {"ad": m, "tel": t}
                except Exception:
                    bayi_key = ""
            c_no = self.generate_record_code()
            sif = f"Desen: {self.kayitli_desen}" if self.sifre_tipi.currentIndex() == 1 else self.f_sifre.text().strip()
            d = {
                "c_no": c_no, 
                "m": m, 
                "t": t, 
                "ci": c, 
                "a": a, 
                "arizalar": arizalar,
                "sifre": sif, 
                "sim": self.cb_sim.isChecked(), 
                "sd": self.cb_sd.isChecked(), 
                "kilif": self.cb_kilif.isChecked(), 
                "d": "İşlem Bekliyor", 
                "not": initial_note, 
                "not_okundu": True, 
                "is_bayi": is_bayi, 
                "record_type": "bayi" if is_bayi else "musteri",
                "bayi_key": bayi_key,
                "customer_key": "" if is_bayi else customer_key,
                "yaklasik_ucret": str(yaklasik) if yaklasik > 0 else "",
                "garanti_gun": str(garanti_gun) if garanti_gun > 0 else "",
                "garanti_bitis": garanti_bitis,
                "z": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            }
            res = db.child("users").child(self.user_id).child("kayitlar").push(d, self.token)
            kid = res['name']
            d["c_no"] = self.ensure_unique_record_code(kid, d.get("c_no"))
            d["record_id"] = kid
            self.apply_stream_record_change(kid, d)
            try:
                self.update_record_fields(kid, {"record_id": kid, "c_no": d.get("c_no")}, "Kayıt tamamlama", require_connection=False)
            except:
                pass
            self.log_record_action(kid, f"Kayıt açıldı: {d.get('c_no')} - {m} / {c}")
            if initial_note:
                self.append_note_history(kid, initial_note, "Kayıt sırasında eklendi")
            self.publish_public_status(kid, d)
            self.refresh_record_views_after_stream()
            
            self.show_new_record_output_dialog(d)
                
            self.f_ad.clear()
            self.f_tel.clear()
            self.f_cihaz.clear()
            self.f_ariza.clear()
            self.extra_faults = []
            self.lbl_ariza_ozet.clear()
            if hasattr(self, "f_not"):
                self.f_not.clear()
            self.f_yaklasik.clear()
            self.f_garanti_gun.setText(str(self.user_setting_value("default_warranty_days", "30")))
            self.cb_garanti_ver.setChecked(False)
            self.sifre_tipi.setCurrentIndex(0)
            self.f_sifre.clear()
            self.kayitli_desen = ""
            self.btn_desen.setText("Desen Çiz")
            self.btn_desen.setStyleSheet("")
            self.cb_sim.setChecked(False)
            self.cb_sd.setChecked(False)
            self.cb_kilif.setChecked(False)
            self.cb_bayi_kayit.setChecked(False)
            self.selected_bayi_key = ""
            self.selected_customer_key = ""
            if hasattr(self, "cb_registered_customer"):
                self.cb_registered_customer.blockSignals(True)
                self.cb_registered_customer.setChecked(False)
                self.cb_registered_customer.blockSignals(False)
            if hasattr(self, "lbl_record_mode_state"):
                self.lbl_record_mode_state.setText("Yeni müşteri kaydı")
            self.lbl_musteri_uyari.clear()
            self.lbl_musteri_uyari.hide()
            
            QTimer.singleShot(500, lambda: self.open_photo_dialog_for_new(kid))
        except Exception as e: 
            QMessageBox.warning(self, "Kayıt Hatası", self.friendly_write_error("Cihaz kaydı", e))

    def open_photo_dialog_for_new(self, kid):
        PhotoDialog(kid, self.user_id, NETLIFY_URL, self, 1).exec()
        self.touch_record_sync_meta(kid, "upsert")
        try:
            fresh_record = db.child("users").child(self.user_id).child("kayitlar").child(kid).get(self.token).val()
            if isinstance(fresh_record, dict):
                self.apply_stream_record_change(kid, fresh_record, replace=True)
        except Exception:
            pass
        record = self.get_local_record(kid)
        if isinstance(record, dict):
            self.upsert_record_row_from_cache(kid, record)
            self.refresh_record_views_after_stream()

    def update_income_stats(self, amount, date_str, stats):
        try:
            diff = (datetime.datetime.now() - datetime.datetime.strptime(date_str.split(" ")[0], "%d.%m.%Y")).days
            if diff == 0: stats['g'] += amount
            if diff <= 7: stats['h'] += amount
            if diff <= 30: stats['a'] += amount
        except: 
            pass

    def load_musteri_cihaz_gecmisi(self, item):
        customer = self.customer_payload_from_item(item)
        m_adi = customer.get("display") or customer.get("name") or (item.text() if isinstance(item, QListWidgetItem) else str(item or ""))
        self.lbl_secili_musteri.setText(f"<h2>{m_adi} Geçmiş Cihaz Kayıtları</h2>")
        self.table_musteri_gecmis.setRowCount(0)
        for k, v in self.customer_records_for_identity(customer):
            if not isinstance(v, dict):
                continue
            ucret = safe_float(v.get("masraf", "0"))
            m_str = "" if ucret == 0 else f"{format_money(ucret, '₺')}"
            self.add_row_to_table(self.table_musteri_gecmis, [k, v.get("c_no"), v.get("ci"), self.format_faults(v), v.get("yapilan_islem","-"), m_str, v.get("z")])

    def filter_dokum_by_date(self):
        self.table_dokum.setRowCount(0)
        q_basla = self.date_basla.date().toPyDate()
        q_bitis = self.date_bitis.date().toPyDate()
        if q_basla > q_bitis:
            q_basla, q_bitis = q_bitis, q_basla
        data = safe_dict_parse(self.kayitlar_data)
        if not isinstance(data, dict):
            data = {}
        t_is, t_nakit, t_kart, t_eft = 0.0, 0.0, 0.0, 0.0
        
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            zaman_str = v.get("z", "")
            if zaman_str:
                try:
                    c_date = self.parse_date_value(zaman_str).date()
                    if q_basla <= c_date <= q_bitis:
                        ucret = safe_float(v.get("masraf", "0"))
                        m_str = "" if ucret == 0 else f"{format_money(ucret, '₺')}"
                        o_tip = v.get("odeme_tipi", "Nakit")
                        o_durum = v.get("odeme_durumu", "Ödenmedi")
                        
                        self.add_row_to_table(self.table_dokum, [k, v.get("c_no"), v.get("m"), v.get("ci"), v.get("yapilan_islem","-"), m_str, f"{o_durum} ({o_tip})", v.get("z")])
                        
                        odeme_norm = self.normalize_upper(o_durum)
                        durum_norm = self.normalize_upper(v.get("d", ""))
                        tip_norm = self.normalize_upper(o_tip)
                        if "ÖDENDİ" in odeme_norm and "İADE" not in durum_norm:
                            t_is += ucret
                            if "KART" in tip_norm: t_kart += ucret
                            elif "EFT" in tip_norm or "HAVALE" in tip_norm: t_eft += ucret
                            else: t_nakit += ucret
                except: 
                    pass
                
        self.lbl_dokum_alt_toplam.setText(
            f"📋 <b>Seçili Aralık Toplamı:</b> {format_money(t_is, '₺')}  |  "
            f"<span style='color:#22c55e;'><b>Nakit:</b> {format_money(t_nakit, '₺')}</span>  |  "
            f"<span style='color:#38bdf8;'><b>Kart:</b> {format_money(t_kart, '₺')}</span>  |  "
            f"<span style='color:#f59e0b;'><b>EFT:</b> {format_money(t_eft, '₺')}</span>"
        )

    def show_advanced_device_report(self, kid):
        kayitlar = safe_dict_parse(self.kayitlar_data)
        if not isinstance(kayitlar, dict):
            kayitlar = {}
        v = kayitlar.get(kid)
        if not isinstance(v, dict): return
        toptanci_data = safe_dict_parse(db.child("users").child(self.user_id).child("toptanci").get(self.token).val() or {})
        if not isinstance(toptanci_data, dict):
            toptanci_data = {}
        parca_satirlari = []
        
        for tk, tv in toptanci_data.items():
            if not isinstance(tv, dict):
                continue
            if tv.get("kid") == kid:
                parca_satirlari.append(f"<b>Toptancı:</b> {tv.get('firma')} | {tv.get('parca')} | {format_money(safe_float(tv.get('tutar')), '$')}")

        used_parts = safe_dict_parse(v.get("kullanilan_parcalar", {}))
        if isinstance(used_parts, dict):
            for part in used_parts.values():
                if isinstance(part, dict):
                    parca_satirlari.append(
                        f"<b>Stok:</b> {part.get('parca', '')} x {self.format_quantity(part.get('adet', 0))} | "
                        f"Satış: {format_money(safe_float(part.get('satis', 0)), part.get('birim', '₺'))}"
                    )
        parca_notu = "<br>".join(parca_satirlari) if parca_satirlari else "Bu cihaz için parça kaydı bulunmuyor."
                
        report_html = f"""
        <div style='line-height:1.5;'>
        <b>Kayıt No:</b> {v.get('c_no')}<br><b>Müşteri:</b> {v.get('m')}<br><b>Telefon:</b> {v.get('t', 'Belirtilmemiş')}<br>
        <b>Cihaz Model:</b> {v.get('ci')}<br><b>Bildirilen Arıza:</b><br>{self.format_faults(v, compact=False)}<br>
        <b>Kayıt Tarihi:</b> {v.get('z', 'Belirtilmemiş')}<br><b>Durum:</b> {v.get('d', 'Belirtilmemiş')}<br><br>
        <div style='background:#eef3f8; color:#172033; padding:8px; border-radius:4px;'>
        <b>🔧 Yapılan İşlem:</b> {v.get('yapilan_islem', 'Girilmemiş.')}<br>
        <b>💸 Alınan Ücret:</b> {format_money(safe_float(v.get('masraf')), '₺')}<br>
        <b>💰 Yaklaşık Ücret:</b> {format_money(safe_float(v.get('yaklasik_ucret')), '₺') if safe_float(v.get('yaklasik_ucret')) > 0 else 'Belirtilmemiş'}<br>
        <b>💳 Ödeme Türü:</b> {v.get('odeme_durumu', 'Ödenmedi')} ({v.get('odeme_tipi', 'Belirtilmemiş')})
        </div><br>
        <b>🔐 Şifre / Desen:</b> {v.get('sifre', 'Belirtilmemiş')}<br>
        <b>🧩 Aksesuar:</b> SIM: {'Var' if v.get('sim') else 'Yok'} | SD: {'Var' if v.get('sd') else 'Yok'} | Kılıf: {'Var' if v.get('kilif') else 'Yok'}<br><br>
        <b>📦 Toptancı / Parça Durumu:</b><br>{parca_notu}<br><br>
        <b>📝 Not:</b> {v.get('not', 'Not yok') or 'Not yok'}
        </div>
        """
        dlg = ReadOnlyDialog("Teknik İşlem ve Parça Bilgi Raporu", report_html, self)
        dlg.exec()

    def record_price_summary(self, record):
        net = safe_float(record.get("masraf", "0"))
        approx = safe_float(record.get("yaklasik_ucret", "0"))
        if net > 0:
            return format_public_money(net)
        if approx > 0:
            return f"Yaklaşık: {format_public_money(approx)}"
        return "Ücret bilgisi girilmemiş"

    def warranty_status_text(self, record):
        until = str(record.get("garanti_bitis", "") or "").strip()
        days = str(record.get("garanti_gun", "") or "").strip()
        if not until:
            return "Garanti verilmedi"
        try:
            end_date = datetime.datetime.strptime(until, "%d.%m.%Y").date()
            left = (end_date - datetime.date.today()).days
            if left >= 0:
                suffix = f"{left} gün kaldı"
            else:
                suffix = f"{abs(left)} gün önce bitti"
            return f"{until} tarihine kadar ({suffix})" + (f" - {days} gün" if days else "")
        except:
            return until

    def service_timeline_entries(self, kid, record):
        entries = []
        created = str(record.get("z", "") or "")
        if created:
            entries.append((self.parse_date_value(created), created, "Kayıt açıldı"))

        approval_requested = str(record.get("approval_requested_at", "") or "")
        if approval_requested:
            entries.append((self.parse_date_value(approval_requested), approval_requested, f"Müşteri onayı istendi: {record.get('approval_status', 'Bekliyor')}"))

        logs = safe_dict_parse(record.get("logs", {}))
        if isinstance(logs, dict):
            for log in logs.values():
                if not isinstance(log, dict):
                    continue
                when = str(log.get("tarih", "") or "")
                detail = str(log.get("detay", "") or "")
                user = str(log.get("kullanici", "") or "")
                if detail:
                    entries.append((self.parse_date_value(when), when, f"{detail}{' - ' + user if user else ''}"))

        delivery_date = str(record.get("teslim_tarihi", "") or "")
        if delivery_date:
            entries.append((self.parse_date_value(delivery_date), delivery_date, str(record.get("teslim_durumu", "Teslim edildi"))))

        entries.sort(key=lambda item: item[0])
        return entries

    def service_timeline_html(self, kid, record):
        entries = self.service_timeline_entries(kid, record)
        p = self.dialog_html_palette()
        if not entries:
            return f"<span style='color:{p['muted']};'>Henüz zaman çizelgesi yok.</span>"
        lines = []
        for _, when, detail in entries[-12:]:
            lines.append(
                f"<div style='border-left:3px solid {p['accent']}; padding:4px 0 8px 10px; margin-left:4px; color:{p['text']};'>"
                f"<b style='color:{p['accent']};'>{html.escape(str(when or 'Tarih yok'))}</b><br>"
                f"{html.escape(str(detail or ''))}"
                "</div>"
            )
        return "".join(lines)

    def record_parts_html(self, kid, record):
        rows = []
        used_parts = safe_dict_parse(record.get("kullanilan_parcalar", {}))
        if isinstance(used_parts, dict):
            for part in used_parts.values():
                if not isinstance(part, dict):
                    continue
                rows.append(
                    f"Stok/Diğer: {part.get('parca', '')} x {self.format_quantity(part.get('adet', 0))} "
                    f"- {format_money(safe_float(part.get('satis', 0)), part.get('birim', '₺'))}"
                )
        wholesaler_parts = safe_dict_parse(getattr(self, "toptanci_data", {}))
        if not isinstance(wholesaler_parts, dict) or not wholesaler_parts:
            try:
                wholesaler_parts = safe_dict_parse(db.child("users").child(self.user_id).child("toptanci").get(self.token).val() or {})
            except Exception:
                wholesaler_parts = {}
        if isinstance(wholesaler_parts, dict):
            for part in wholesaler_parts.values():
                if isinstance(part, dict) and str(part.get("kid", "")) == str(kid):
                    rows.append(
                        f"Toptancı: {part.get('firma', '')} / {part.get('parca', '')} "
                        f"- {format_money(safe_float(part.get('tutar', 0)), '$')}"
                    )
        if not rows:
            return f"<span style='color:{self.dialog_html_palette()['muted']};'>Parça kaydı yok.</span>"
        return "<br>".join(html.escape(str(row)) for row in rows)

    def approval_badge_html(self, record):
        status = str(record.get("approval_status", "") or "İstenmedi")
        color = "#f59e0b" if status == "Bekliyor" else "#22c55e" if status == "Onaylandı" else "#ef4444" if status == "Reddedildi" else "#94a3b8"
        return f"<span style='color:{color}; font-weight:700;'>{html.escape(status)}</span>"

    def build_device_dossier_html(self, kid, record):
        photos = get_record_photos(record)
        note_history = safe_dict_parse(record.get("not_gecmisi", {}))
        note_count = len(note_history) if isinstance(note_history, dict) else (1 if record.get("not") else 0)
        delivered_ok, delivered_iade = self.is_delivered_record(record)
        service_result = "İade teslim edildi" if delivered_iade and delivered_ok else str(record.get("d", "") or "Belirtilmemiş")
        party_type = "Bayi cihazı" if self.is_bayi_record(record) else "Kayıtlı müşteri" if str(record.get("customer_key", "") or "") else "Yeni müşteri"
        p = self.dialog_html_palette()
        cell_style = f"background-color:{p['panel']}; color:{p['text']}; border:1px solid {p['border']}; padding:10px;"
        return f"""
        <div style="font-family:Arial, sans-serif; color:{p['text']}; background-color:{p['bg']}; line-height:1.45;">
            <h2 style="color:{p['accent']}; margin:0 0 12px 0;">Akıllı Cihaz Dosyası</h2>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                <td style="{cell_style}">
                    <b>Kayıt No:</b> {html.escape(str(record.get('c_no', '')))}<br>
                    <b>Tip:</b> {html.escape(party_type)}<br>
                    <b>Müşteri/Bayi:</b> {html.escape(str(record.get('m', '')))}<br>
                    <b>Telefon:</b> {html.escape(str(record.get('t', '') or 'Belirtilmemiş'))}<br>
                    <b>Cihaz:</b> {html.escape(str(record.get('ci', '')))}
                </td>
                <td style="{cell_style}">
                    <b>Durum:</b> {html.escape(service_result)}<br>
                    <b>Teslim:</b> {html.escape(str(record.get('teslim_durumu', '') or 'Bekliyor'))}<br>
                    <b>Ödeme:</b> {html.escape(str(record.get('odeme_durumu', 'Ödenmedi')))} ({html.escape(str(record.get('odeme_tipi', '')) or '-')})<br>
                    <b>Ücret:</b> {html.escape(self.record_price_summary(record))}<br>
                    <b>Müşteri Onayı:</b> {self.approval_badge_html(record)}
                </td>
                </tr>
            </table>
            <div style="{cell_style}">
                <b>Arıza Listesi</b><br>{self.format_faults(record, compact=False)}
            </div>
            <br>
            <div style="{cell_style}">
                <b>Yapılan İşlem</b><br>{html.escape(str(record.get('yapilan_islem', '') or 'Henüz işlem girilmedi.'))}
            </div>
            <br>
            <table width="100%" cellspacing="6" cellpadding="0">
                <tr>
                <td style="{cell_style}">
                    <b>Parça / Stok</b><br>{self.record_parts_html(kid, record)}
                </td>
                <td style="{cell_style}">
                    <b>Garanti</b><br>{html.escape(self.warranty_status_text(record))}<br><br>
                    <b>Fotoğraf:</b> {len(photos)} adet<br>
                    <b>Not:</b> {note_count} kayıt
                </td>
                </tr>
            </table>
            <div style="{cell_style}">
                <b>Zaman Çizelgesi</b><br>{self.service_timeline_html(kid, record)}
            </div>
            <br>
            <div style="{cell_style}">
                <b>Son Not</b><br>{html.escape(str(record.get('not', '') or 'Not yok.'))}
            </div>
        </div>
        """

    def show_device_dossier(self, kid):
        record = self.get_local_record(kid)
        if not isinstance(record, dict) or not record:
            QMessageBox.warning(self, "Cihaz Dosyası", "Kayıt bulunamadı.")
            return
        dlg = ReadOnlyDialog("Akıllı Cihaz Dosyası", self.build_device_dossier_html(kid, record), self)
        dlg.resize(760, 720)
        dlg.exec()

    def customer_approval_message(self, record):
        name = str(record.get("m", "") or "").strip()
        device = str(record.get("ci", "") or "").strip()
        code = str(record.get("c_no", "") or "").strip()
        price = self.record_price_summary(record)
        operation = str(record.get("yapilan_islem", "") or "Yapılacak işlem").strip()
        greeting = f"Merhaba {name}," if name else "Merhaba,"
        return (
            f"{greeting}\n\n"
            f"{device} cihazınız için servis onayı gerekiyor.\n"
            f"Kayıt No: {code}\n"
            f"İşlem: {operation}\n"
            f"Ücret: {price}\n\n"
            f"Onaylıyorsanız bu mesaja ONAY, istemiyorsanız RED yazarak dönüş yapabilirsiniz.\n\n"
            f"{self.display_company_name()}"
        )

    def request_customer_approval(self, kid, record):
        tel = "".join(filter(str.isdigit, str(record.get("t", ""))))
        if tel.startswith("0"):
            tel = tel[1:]
        if len(tel) != 10:
            QMessageBox.warning(self, "Müşteri Onayı", "Bu kayıt için geçerli 10 haneli telefon numarası bulunamadı.")
            return
        payload = {
            "approval_status": "Bekliyor",
            "approval_requested_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
            "approval_price": self.record_price_summary(record),
            "approval_token": str(record.get("approval_token", "") or uuid.uuid4().hex[:12]).upper()
        }
        try:
            if not self.update_record_fields(kid, payload, "Müşteri onayı"):
                return
            record.update(payload)
            self.log_record_action(kid, "Müşteri onayı istendi")
            self.publish_public_status(kid, record)
        except Exception as e:
            QMessageBox.warning(self, "Müşteri Onayı", f"Onay bilgisi kaydedilemedi:\n{e}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Müşteri Onay Mesajı")
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("WhatsApp ile gönderilecek onay mesajı:"))
        msg_box = QTextEdit()
        msg_box.setPlainText(self.customer_approval_message(record))
        lay.addWidget(msg_box)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("WhatsApp Gönder")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Sadece Kaydet")
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            webbrowser.open(f"https://wa.me/90{tel}?text={urllib.parse.quote(msg_box.toPlainText())}")
        self.refresh_all_tables()

    def set_customer_approval_status(self, kid, record, status):
        try:
            payload = {
                "approval_status": status,
                "approval_updated_at": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            }
            if not self.update_record_fields(kid, payload, "Müşteri onayı"):
                return
            self.log_record_action(kid, f"Müşteri onayı: {status}")
            record["approval_status"] = status
            self.publish_public_status(kid, record)
            self.refresh_all_tables()
        except Exception as e:
            QMessageBox.warning(self, "Müşteri Onayı", f"Onay durumu güncellenemedi:\n{e}")

    def records_for_date(self, target_date):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            return []
        rows = []
        for kid, rec in data.items():
            if isinstance(rec, dict) and self.parse_date_value(rec.get("z", "")).date() == target_date:
                rows.append((kid, rec))
        return rows

    def show_daily_service_report(self):
        today = datetime.date.today()
        records = self.records_for_date(today)
        delivered = []
        income = 0.0
        faults = {}
        for kid, rec in records:
            if self.is_delivered_record(rec)[0]:
                delivered.append((kid, rec))
            if rec.get("odeme_durumu") == "Ödendi":
                income += safe_float(rec.get("masraf", "0"))
            for fault in self.get_faults(rec):
                faults[fault] = faults.get(fault, 0) + 1
        fault_html = "<br>".join(f"{html.escape(k)}: {v}" for k, v in sorted(faults.items(), key=lambda x: x[1], reverse=True)[:8]) or "Bugün arıza kaydı yok."
        row_html = "".join(
            f"<tr><td>{html.escape(rec.get('c_no', ''))}</td><td>{html.escape(rec.get('m', ''))}</td><td>{html.escape(rec.get('ci', ''))}</td><td>{html.escape(rec.get('d', ''))}</td></tr>"
            for _, rec in records[:80]
        ) or "<tr><td colspan='4'>Bugün kayıt yok.</td></tr>"
        report = f"""
        <div style='font-family:Arial; line-height:1.45;'>
            <h2>Günlük Servis Raporu - {today.strftime('%d.%m.%Y')}</h2>
            <b>Bugünkü kayıt:</b> {len(records)} &nbsp; <b>Teslim edilen:</b> {len(delivered)} &nbsp; <b>Tahsilat:</b> {format_money(income, '₺')}<br><br>
            <b>En sık arızalar:</b><br>{fault_html}<br><br>
            <table width='100%' cellspacing='0' cellpadding='6' border='1'>
                <tr><th>Kayıt</th><th>Müşteri/Bayi</th><th>Cihaz</th><th>Durum</th></tr>
                {row_html}
            </table>
        </div>
        """
        dlg = ReadOnlyDialog("Günlük Servis Raporu", report, self, actions=[("⬇ Dışa Aktar", self.show_daily_report_export_menu)])
        dlg.resize(760, 640)
        dlg.exec()

    def show_daily_report_export_menu(self):
        menu = QMenu(self)
        pdf_action = menu.addAction("PDF olarak kaydet")
        excel_action = menu.addAction("Excel uyumlu CSV kaydet")
        action = menu.exec(QCursor.pos())
        if action == pdf_action:
            self.export_daily_service_report_pdf()
        elif action == excel_action:
            self.export_daily_service_report_excel()

    def build_daily_service_report_export(self, target_date=None):
        target_date = target_date or datetime.date.today()
        records = self.records_for_date(target_date)
        delivered = []
        income = 0.0
        faults = {}
        for _, rec in records:
            if self.is_delivered_record(rec)[0]:
                delivered.append(rec)
            if rec.get("odeme_durumu") == "Ödendi":
                income += safe_float(rec.get("masraf", "0"))
            for fault in self.get_faults(rec):
                faults[fault] = faults.get(fault, 0) + 1

        fault_html = "<br>".join(
            f"{html.escape(str(k))}: {v}"
            for k, v in sorted(faults.items(), key=lambda x: x[1], reverse=True)[:8]
        ) or "Bugün arıza kaydı yok."
        row_html = "".join(
            "<tr>"
            f"<td>{html.escape(str(rec.get('c_no', '')))}</td>"
            f"<td>{html.escape(str(rec.get('m', '')))}</td>"
            f"<td>{html.escape(str(rec.get('ci', '')))}</td>"
            f"<td>{html.escape(str(rec.get('d', '')))}</td>"
            f"<td>{html.escape(str(rec.get('yapilan_islem', '') or '-'))}</td>"
            f"<td>{format_money(safe_float(rec.get('masraf', '0')), '₺')}</td>"
            f"<td>{html.escape(str(rec.get('odeme_durumu', 'Ödenmedi')))}</td>"
            "</tr>"
            for _, rec in records[:120]
        ) or "<tr><td colspan='7'>Bugün kayıt yok.</td></tr>"
        report_html = f"""
        <div style='font-family:Arial; line-height:1.45; color:#111827;'>
            <h2>Günlük Servis Raporu - {target_date.strftime('%d.%m.%Y')}</h2>
            <b>Bugünkü kayıt:</b> {len(records)} &nbsp;
            <b>Teslim edilen:</b> {len(delivered)} &nbsp;
            <b>Tahsilat:</b> {format_money(income, '₺')}<br><br>
            <b>En sık arızalar:</b><br>{fault_html}<br><br>
            <table width='100%' cellspacing='0' cellpadding='6' border='1' style='border-collapse:collapse;'>
                <tr style='background:#e5e7eb;'>
                    <th>Kayıt</th><th>Müşteri/Bayi</th><th>Cihaz</th><th>Durum</th><th>İşlem</th><th>Ücret</th><th>Ödeme</th>
                </tr>
                {row_html}
            </table>
        </div>
        """
        return {
            "date": target_date,
            "records": records,
            "delivered_count": len(delivered),
            "income": income,
            "faults": faults,
            "html": report_html,
        }

    def export_daily_service_report_pdf(self):
        payload = self.build_daily_service_report_export()
        date_text = payload["date"].strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(self, "Günlük Rapor PDF Kaydet", f"Gunluk_Servis_Raporu_{date_text}.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(96)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(path)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
        printer.setPageMargins(QMarginsF(10, 10, 10, 10), QPageLayout.Unit.Millimeter)
        doc = QTextDocument()
        doc.setHtml(payload["html"])
        doc.setPageSize(printer.pageRect(QPrinter.Unit.Point).size())
        doc.print(printer)
        QMessageBox.information(self, "Günlük Rapor", "Günlük rapor PDF olarak kaydedildi.")

    def export_daily_service_report_excel(self):
        payload = self.build_daily_service_report_export()
        date_text = payload["date"].strftime("%Y-%m-%d")
        path, _ = QFileDialog.getSaveFileName(self, "Günlük Rapor Excel Kaydet", f"Gunluk_Servis_Raporu_{date_text}.csv", "Excel CSV (*.csv)")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["Günlük Servis Raporu", payload["date"].strftime("%d.%m.%Y")])
            writer.writerow(["Bugünkü kayıt", len(payload["records"]), "Teslim edilen", payload["delivered_count"], "Tahsilat", format_money(payload["income"], "₺")])
            writer.writerow([])
            writer.writerow(["En sık arızalar"])
            sorted_faults = sorted(payload["faults"].items(), key=lambda x: x[1], reverse=True)
            if sorted_faults:
                for fault, count in sorted_faults:
                    writer.writerow([fault, count])
            else:
                writer.writerow(["Bugün arıza kaydı yok.", ""])
            writer.writerow([])
            writer.writerow(["Kayıt No", "Müşteri/Bayi", "Telefon", "Cihaz", "Arıza", "Durum", "İşlem", "Ücret", "Ödeme Durumu", "Ödeme Tipi", "Tarih"])
            for _, rec in payload["records"]:
                writer.writerow([
                    rec.get("c_no", ""),
                    rec.get("m", ""),
                    rec.get("t", ""),
                    rec.get("ci", ""),
                    " | ".join(self.get_faults(rec)),
                    rec.get("d", ""),
                    rec.get("yapilan_islem", ""),
                    format_money(safe_float(rec.get("masraf", "0")), "₺"),
                    rec.get("odeme_durumu", "Ödenmedi"),
                    rec.get("odeme_tipi", ""),
                    rec.get("z", ""),
                ])
        QMessageBox.information(self, "Günlük Rapor", "Günlük rapor Excel uyumlu CSV olarak kaydedildi.")

    def show_warranty_center(self):
        data = safe_dict_parse(getattr(self, "kayitlar_data", {}))
        if not isinstance(data, dict):
            data = {}
        rows = []
        today = datetime.date.today()
        for kid, rec in data.items():
            if not isinstance(rec, dict):
                continue
            until = str(rec.get("garanti_bitis", "") or "")
            if not until:
                continue
            try:
                end_date = datetime.datetime.strptime(until, "%d.%m.%Y").date()
            except:
                continue
            rows.append((end_date, rec))
        rows.sort(key=lambda item: item[0])
        table_rows = []
        for end_date, rec in rows[:120]:
            left = (end_date - today).days
            color = "#ef4444" if left < 0 else "#f59e0b" if left <= 7 else "#22c55e"
            table_rows.append(
                f"<tr><td>{html.escape(rec.get('c_no', ''))}</td><td>{html.escape(rec.get('m', ''))}</td>"
                f"<td>{html.escape(rec.get('ci', ''))}</td><td style='color:{color}; font-weight:bold;'>{end_date.strftime('%d.%m.%Y')} ({left} gün)</td></tr>"
            )
        body = "".join(table_rows) or "<tr><td colspan='4'>Garanti kaydı bulunamadı.</td></tr>"
        dlg = ReadOnlyDialog("Garanti Takip Merkezi", f"""
        <div style='font-family:Arial; line-height:1.45;'>
            <h2>Garanti Takip Merkezi</h2>
            <table width='100%' cellspacing='0' cellpadding='6' border='1'>
                <tr><th>Kayıt</th><th>Müşteri/Bayi</th><th>Cihaz</th><th>Garanti Bitişi</th></tr>
                {body}
            </table>
        </div>
        """, self)
        dlg.resize(760, 640)
        dlg.exec()

    def show_low_stock_center(self):
        stok = safe_dict_parse(getattr(self, "stok_data", {}))
        if not isinstance(stok, dict):
            stok = {}
        rows = []
        for sid, item in stok.items():
            if not isinstance(item, dict):
                continue
            qty = safe_float(item.get("adet", 0))
            if qty <= 2:
                rows.append(
                    f"<tr><td>{html.escape(self.stock_code_for_item(sid, item))}</td><td>{html.escape(str(item.get('ad', '')))}</td>"
                    f"<td style='color:#ef4444; font-weight:bold;'>{self.format_quantity(qty)}</td>"
                    f"<td>{format_money(safe_float(item.get('satis', 0)), item.get('birim', '₺'))}</td></tr>"
                )
        body = "".join(rows) or "<tr><td colspan='4'>Düşük stok uyarısı yok.</td></tr>"
        dlg = ReadOnlyDialog("Stok Uyarı Merkezi", f"""
        <div style='font-family:Arial; line-height:1.45;'>
            <h2>Stok Uyarı Merkezi</h2>
            <p>Adedi 2 veya altına düşen parçalar burada görünür.</p>
            <table width='100%' cellspacing='0' cellpadding='6' border='1'>
                <tr><th>Stok Kodu</th><th>Parça</th><th>Adet</th><th>Satış</th></tr>
                {body}
            </table>
        </div>
        """, self)
        dlg.resize(720, 560)
        dlg.exec()

    def refresh_all_tables(self, retried=False, prefer_cache=False, force_cloud=False):
        if getattr(self, "_refreshing_tables", False):
            self._refresh_requested = True
            return
        if not self.firebase_connection_available(timeout=0.6) and self.has_cached_section("kayitlar"):
            self._cache_only_refresh = True
            try:
                self._refresh_all_tables_impl(prefer_cache=True, force_cloud=False)
            except Exception as error:
                self._refreshing_tables = False
                self._refresh_prefer_cache = False
                self._refresh_force_cloud = False
                self.handle_refresh_error(error, retried=retried)
            finally:
                self._cache_only_refresh = False
            return
        local_cache_available = bool(prefer_cache and not force_cloud and self.has_cached_section("kayitlar"))
        if not local_cache_available and not self.ensure_firebase_session():
            if not retried:
                QTimer.singleShot(3000, lambda: self.refresh_all_tables(retried=True))
            return
        try:
            self._refresh_all_tables_impl(prefer_cache=prefer_cache, force_cloud=force_cloud)
        except Exception as error:
            self._refreshing_tables = False
            self._refresh_prefer_cache = False
            self._refresh_force_cloud = False
            self.handle_refresh_error(error, retried=retried)

    def _refresh_all_tables_impl(self, prefer_cache=False, force_cloud=False):
        if getattr(self, "_refreshing_tables", False):
            self._refresh_requested = True
            return
        self._refreshing_tables = True
        self._cache_fallback_sections = set()
        self._cache_preferred_sections = set()
        self._refresh_prefer_cache = bool(prefer_cache)
        self._refresh_force_cloud = bool(force_cloud)
        self.set_sync_status("Veriler yenileniyor", "#f59e0b")
        current_bayi = self.list_bayiler.currentItem().text() if self.list_bayiler.currentItem() else None
        current_must_item = self.list_musteriler.currentItem()
        current_must = current_must_item.text() if current_must_item else None
        current_must_data = current_must_item.data(Qt.ItemDataRole.UserRole) if current_must_item else {}
        current_must_key = str(current_must_data.get("key", "") if isinstance(current_must_data, dict) else "")
        
        for t in [self.table_act, self.table_ready, self.table_done, self.table_delivered, self.table_kasa, self.table_stok, self.table_trash, self.table_dokum]: 
            t.setRowCount(0)
            
        self.list_bayiler.clear()
        self.list_musteriler.clear()
        
        self.kayitlar_data = self.read_user_section("kayitlar", default={})
        data = safe_dict_parse(self.kayitlar_data)
        if not isinstance(data, dict):
            data = {}
        data = self.migrate_legacy_customer_keys(data)
        self.kayitlar_data = data
        
        toplam_kazanc, bekleyen_alacak, m_gelir, m_gider = 0.0, 0.0, 0.0, 0.0
        tot_nakit, tot_kart, tot_eft = 0.0, 0.0, 0.0
        done_nakit, done_kart, done_eft = 0.0, 0.0, 0.0
        c_act, c_ready, c_done, c_delivered = 0, 0, 0, 0
        c_teslim_wait, c_iade_wait = 0, 0
        stats = {'g': 0.0, 'h': 0.0, 'a': 0.0}
        
        self.bayi_isimleri.clear()
        self.musteri_listesi.clear()
        self.cihaz_listesi.clear()
        self.ariza_listesi.clear()
        self.operation_listesi.clear()
        
        sabit_bayiler = self.read_user_section("sabit_bayiler", default={})
        sabit_d = safe_dict_parse(sabit_bayiler)
        if not isinstance(sabit_d, dict):
            sabit_d = {}
        self.sabit_bayiler_data = sabit_d
        for v in sabit_d.values():
            if not isinstance(v, dict):
                continue
            self.bayi_isimleri.add(v.get("ad"))
        
        for k, v in data.items():
            if not isinstance(v, dict):
                continue
            st = v.get("d", "")
            c_text = self.device_display_text(v)
                
            if v.get("m"):
                if self.is_bayi_record(v):
                    self.bayi_isimleri.add(v.get("m"))
                else:
                    self.musteri_listesi.add(self.normalize_upper(v.get("m")))
            if v.get("ci"): self.cihaz_listesi.add(self.normalize_upper(v.get("ci")))
            if v.get("yapilan_islem"): self.operation_listesi.add(self.normalize_upper(v.get("yapilan_islem")))
            for fault in self.get_faults(v):
                self.ariza_listesi.add(fault)
            
            ucret = safe_float(v.get("masraf", "0"))
            m_str = "" if ucret == 0 else f"{format_money(ucret, '')}"
            odeme = v.get("odeme_durumu", "Ödenmedi")
            zaman = v.get("z", "")
            o_tip = v.get("odeme_tipi", "Nakit")
            
            if st in ["İşlem Bekliyor", "Islem Bekliyor"]:
                yaklasik = safe_float(v.get("yaklasik_ucret", "0"))
                fiyat_text = f"{format_money(ucret, '₺')}" if ucret > 0 else f"Yaklaşık: {format_money(yaklasik, '₺')}" if yaklasik > 0 else ""
                row_colors = self.party_row_colors(v, 8) or [QColor("#f59e0b")]*8
                self.add_row_to_table(self.table_ready, [k, v.get("c_no"), self.party_display_text(v), c_text, self.format_faults(v), fiyat_text, zaman, self.status_display_text(v, st)], row_colors)
                c_ready += 1
            elif st in ["Tamirde", "Parça Bekliyor"]:
                yaklasik = safe_float(v.get("yaklasik_ucret", "0"))
                fiyat_text = f"{format_money(ucret, '₺')}" if ucret > 0 else f"Yaklaşık: {format_money(yaklasik, '₺')}" if yaklasik > 0 else ""
                self.add_row_to_table(self.table_act, [k, v.get("c_no"), self.party_display_text(v), c_text, self.format_faults(v), fiyat_text, zaman, self.status_display_text(v, st)], self.party_row_colors(v, 8))
                c_act += 1
            elif "Hazır" in st or "Hazir" in st or "İşlemleri Tamamlandı" in st or "Islemleri Tamamlandi" in st:
                row_colors = self.party_row_colors(v, 10) or [QColor("#22c55e")]*10
                row_colors[8] = QColor("#f97316")
                row_colors[9] = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
                o_durum_metin = f"{odeme} ({o_tip})" if odeme == "Ödendi" else odeme
                self.add_row_to_table(self.table_done, [k, v.get("c_no"), self.party_display_text(v), c_text, v.get("yapilan_islem",""), f"{m_str} ₺" if m_str else "", zaman, self.status_display_text(v, "İşlemi Tamamlandı"), "Teslim Bekliyor", o_durum_metin], row_colors)
                c_done += 1
                c_teslim_wait += 1
            elif st in ["Teslim Bekliyor", "İade Bekliyor", "Iade Bekliyor", "Teslim Edildi", "İade Edildi", "Iade Edildi"]:
                delivered_ok, delivered_is_iade = self.is_delivered_record(v)
                is_iade = "İade" in st or "Iade" in st or delivered_is_iade
                if "Bekliyor" in st:
                    durum_goster = "↩ İADE BEKLİYOR" if is_iade else "TESLİM BEKLİYOR"
                else:
                    durum_goster = "↩ İADE EDİLDİ" if is_iade else st
                c1 = QColor("#2ecc71") if "Teslim" in st else QColor("#f97316")
                c2 = QColor("#2ecc71") if odeme == "Ödendi" else QColor("#ef4444")
                teslim_durumu = v.get("teslim_durumu", "")
                if not teslim_durumu:
                    teslim_durumu = "Müşteriye Teslim Edildi" if st == "Teslim Edildi" else "Teslim Bekliyor"
                if delivered_ok:
                    c_delivered += 1
                else:
                    c_done += 1
                if "Teslim Bekliyor" in teslim_durumu:
                    if is_iade:
                        c_iade_wait += 1
                    else:
                        c_teslim_wait += 1
                
                o_durum_metin = f"{odeme} ({o_tip})" if odeme == "Ödendi" else odeme
                if not delivered_ok:
                    base_colors = self.party_row_colors(v, 10) or [c1]*10
                    base_colors[8] = QColor("#22c55e") if "Teslim Edildi" in teslim_durumu else QColor("#f97316")
                    base_colors[9] = c2
                    row_idx = self.add_row_to_table(self.table_done, [k, v.get("c_no"), self.party_display_text(v), c_text, v.get("yapilan_islem",""), f"{m_str} ₺" if m_str else "", zaman, self.status_display_text(v, durum_goster), teslim_durumu, o_durum_metin], base_colors)
                    if is_iade:
                        for col in range(self.table_done.columnCount()):
                            item = self.table_done.item(row_idx, col)
                            if item:
                                item.setBackground(QColor("#fff3e0"))
                
                if "Teslim" in st:
                    if odeme == "Ödendi": 
                        toplam_kazanc += ucret
                        self.update_income_stats(ucret, zaman, stats)
                        if "Kart" in o_tip:
                            tot_kart += ucret
                            done_kart += ucret
                        elif "EFT" in o_tip or "Havale" in o_tip:
                            tot_eft += ucret
                            done_eft += ucret
                        else:
                            tot_nakit += ucret
                            done_nakit += ucret
                    else: 
                        bekleyen_alacak += ucret

        kasa_ham = self.read_user_section("kasa", default={})
        kasa_d = safe_dict_parse(kasa_ham)
        if not isinstance(kasa_d, dict):
            kasa_d = {}
        self.kasa_data = kasa_d
        for k, v in kasa_d.items():
            if not isinstance(v, dict):
                continue
            if not self.should_count_cash_record(v):
                continue
            tip = v.get("tip", "Gelir")
            odeme_tipi = str(v.get("odeme_tipi", "") or "Nakit")
            tut = safe_float(v.get("tutar", "0"))
            c = QColor("#2ecc71") if "Gelir" in tip or "Income" in tip else QColor("#ef4444")
            self.add_row_to_table(self.table_kasa, [k, v.get("t"), tip, odeme_tipi, v.get("aciklama"), f"{format_money(tut, '₺')}"], [c]*6)
            if "Gelir" in tip or "Income" in tip: 
                m_gelir += tut
                self.update_income_stats(tut, v.get("t"), stats)
                if "Kart" in odeme_tipi:
                    tot_kart += tut
                elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                    tot_eft += tut
                else:
                    tot_nakit += tut
            else: 
                m_gider += tut
                self.update_income_stats(-tut, v.get("t"), stats)
                if "Kart" in odeme_tipi:
                    tot_kart -= tut
                elif "EFT" in odeme_tipi or "Havale" in odeme_tipi:
                    tot_eft -= tut
                else:
                    tot_nakit -= tut

        stk_ham = self.read_user_section("stok", default={})
        stk_d = safe_dict_parse(stk_ham)
        if not isinstance(stk_d, dict):
            stk_d = {}
        self.stok_data = stk_d
        toplam_stok_tl = 0.0
        for idx, (k, v) in enumerate(stk_d.items(), 1):
            if not isinstance(v, dict):
                continue
            alis = safe_float(v.get('alis', '0'))
            adet = safe_float(v.get('adet', '0'))
            birim = v.get('birim', '₺')
            toplam_stok_tl += ((alis if birim == "₺" else alis * self.usd_rate) * adet)
            stok_kodu = self.stock_code_for_item(k, v, idx)
            self.add_row_to_table(self.table_stok, [k, stok_kodu, v.get("barkod", "") or v.get("barcode", ""), v.get("ad"), f"{format_money(alis, birim)}", f"{format_money(safe_float(v.get('satis', '0')), birim)}", self.format_quantity(v.get("adet"))])

        trash_data = safe_dict_parse(self.read_user_section("cop_kutusu", default={}))
        if not isinstance(trash_data, dict):
            trash_data = {}
        self.trash_data = trash_data
        now = datetime.datetime.now()
        for module, items in trash_data.items():
            items = safe_dict_parse(items)
            if not isinstance(items, dict):
                continue
            for item_id, item_info in items.items():
                if not isinstance(item_info, dict):
                    continue
                del_date_str = item_info.get("deleted_at", "")
                data = safe_dict_parse(item_info.get("data", {}))
                if not isinstance(data, dict):
                    data = {}
                ozet = "Bilinmeyen Veri"
                if module == "kayitlar": ozet = f"Müşteri: {data.get('m', '')} - Cihaz: {data.get('ci', '')}"
                elif module == "stok": ozet = f"Stok Parçası: {data.get('ad', '')}"
                elif module == "kasa": ozet = f"Kasa Hareketi: {data.get('aciklama', '')}"
                elif module == "sabit_bayiler": ozet = f"Bayi: {data.get('ad', '')} - Tel: {data.get('tel', '') or 'Yok'}"
                elif module == "firmalar": ozet = f"Toptancı: {data.get('ad', '')}"
                elif module == "toptanci": ozet = f"Toptancı Parçası: {data.get('parca', '')} - Firma: {data.get('firma', '')}"
                
                kalan_gun = 30
                if del_date_str:
                    try: 
                        kalan_gun = 30 - (now - datetime.datetime.strptime(del_date_str, "%Y-%m-%d")).days
                    except: pass
                
                c = QColor("#ef4444") if kalan_gun <= 5 else QColor("#e0e0e0" if self.user_setting_value("theme", "Dark") != "Light" else "#333333")
                self.add_row_to_table(self.table_trash, [f"{module}|{item_id}", module.capitalize(), ozet, del_date_str, f"{kalan_gun} Gün"], [None, None, None, None, c])

        net_kasa = (toplam_kazanc + m_gelir) - m_gider
        self.lbl_gunluk.setText(f"{format_money(stats['g'], '₺')}")
        self.lbl_haftalik.setText(f"{format_money(stats['h'], '₺')}")
        self.lbl_aylik.setText(f"{format_money(stats['a'], '₺')}")
        self.lbl_kasa.setText(f"{format_money(net_kasa, '₺')}")
        self.lbl_islemde.setText(str(c_act))
        self.lbl_bekleyen.setText(str(c_ready))
        self.lbl_teslim_bekleyen.setText(str(c_teslim_wait))
        self.lbl_iade_bekleyen.setText(str(c_iade_wait))
        
        self.lbl_tot_nakit.setText(f"💵 Nakit Kasa: {format_money(tot_nakit, '₺')}")
        self.lbl_tot_kart.setText(f"💳 Kredi Kartı: {format_money(tot_kart, '₺')}")
        self.lbl_tot_eft.setText(f"📱 EFT / Havale: {format_money(tot_eft, '₺')}")
        self.lbl_done_nakit.setText(f"Nakit: {format_money(done_nakit, '₺')}")
        self.lbl_done_kart.setText(f"Kart: {format_money(done_kart, '₺')}")
        self.lbl_done_eft.setText(f"EFT: {format_money(done_eft, '₺')}")
        self.lbl_toplam.setText(f"<b>Cihazlardan Gelen (Net):</b> {format_money(toplam_kazanc, '₺')}")
        self.lbl_alacak.setText(f"<b>Açık Hesap (Bekleyen):</b> {format_money(bekleyen_alacak, '₺')}")
        self.lbl_stok_deger.setText(f"<b>Toplam Stok Değeri:</b> {format_money(toplam_stok_tl, '₺')} | {format_money(toplam_stok_tl / self.usd_rate if self.usd_rate else 0, '$')}")
        self.update_notification_summary()
        
        self.update_main_tab_counts(c_act, c_ready, c_done)
        self.filter_delivered_table()
        
        self.refresh_autocomplete_models()
        
        bayi_mode = self.bayi_filter_cb.currentText() if hasattr(self, "bayi_filter_cb") else "Alfabetik"
        must_mode = self.must_filter_cb.currentText() if hasattr(self, "must_filter_cb") else "Alfabetik"
        bayi_names = self.filtered_party_names(list(self.bayi_isimleri), data, True, bayi_mode)
        musteri_entries = self.customer_entries_for_list(must_mode)
        
        self.list_bayiler.addItems(bayi_names)
        current_combo_bayi = self.combo_bayi.currentText()
        self.combo_bayi.blockSignals(True)
        self.combo_bayi.clear()
        self.combo_bayi.addItems(sorted([name for name in self.bayi_isimleri if name], key=self.normalize_upper))
        if current_combo_bayi and self.combo_bayi.findText(current_combo_bayi) >= 0:
            self.combo_bayi.setCurrentText(current_combo_bayi)
        self.combo_bayi.blockSignals(False)
        self.fill_partner_phone(self.combo_bayi.currentText())
        
        for customer in musteri_entries:
            item = QListWidgetItem(customer.get("display", customer.get("name", "")))
            item.setData(Qt.ItemDataRole.UserRole, customer)
            self.list_musteriler.addItem(item)
        if hasattr(self, "lbl_bayi_sayac"):
            self.lbl_bayi_sayac.setText(f"{len(bayi_names)} bayi")
        if hasattr(self, "lbl_musteri_sayac"):
            self.lbl_musteri_sayac.setText(f"{len(musteri_entries)} müşteri")
        
        if current_bayi:
            items = self.list_bayiler.findItems(current_bayi, Qt.MatchFlag.MatchExactly)
            if items: 
                self.list_bayiler.setCurrentItem(items[0])
                self.load_bayi_detay(items[0])
                
        if current_must_key:
            for idx in range(self.list_musteriler.count()):
                item = self.list_musteriler.item(idx)
                data = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(data, dict) and str(data.get("key", "")) == current_must_key:
                    self.list_musteriler.setCurrentItem(item)
                    self.load_musteri_cihaz_gecmisi(item)
                    break
        elif current_must:
            items = self.list_musteriler.findItems(current_must, Qt.MatchFlag.MatchExactly)
            if items: 
                self.list_musteriler.setCurrentItem(items[0])
                self.load_musteri_cihaz_gecmisi(items[0])
                
        if self.tabs.currentWidget() == getattr(self, "tab_whl", None):
            self.load_wholesalers()
        self.filter_dokum_by_date()
        self.update_kasa_period_summary()
        self.apply_all_table_filters()
        self.update_management_report()
        self.apply_staff_permissions()
        if getattr(self, "_cache_fallback_sections", set()):
            self._read_only_cache_mode = True
            self.set_sync_status(f"Yerel kopya kullanıldı - {datetime.datetime.now().strftime('%H:%M:%S')}", "#f59e0b")
        elif getattr(self, "_cache_preferred_sections", set()):
            self._read_only_cache_mode = False
            self.set_sync_status(f"Yerelden okundu - {datetime.datetime.now().strftime('%H:%M:%S')}", "#38bdf8")
        else:
            self._read_only_cache_mode = False
            self.set_sync_status(f"Güncel - {datetime.datetime.now().strftime('%H:%M:%S')}", "#22c55e")
        self._refresh_prefer_cache = False
        self._refresh_force_cloud = False
        self._refreshing_tables = False
        if getattr(self, "_refresh_requested", False):
            self._refresh_requested = False
            self.trigger_debounce_refresh()

    def translate_ui(self):
        self.tabs.setTabText(0, self.get_trans("📊 Dashboard", "📊 Ana Panel"))
        self.tabs.setTabText(1, self.get_trans("➕ New Entry", "➕ Yeni Kayıt"))
        if getattr(self, "_tab_count_act", None) is None:
            self.tabs.setTabText(2, self.get_trans("⏳ In Progress", "⏳ İşlemdekiler"))
        if getattr(self, "_tab_count_ready", None) is None:
            self.tabs.setTabText(3, self.get_trans("⌛ Waiting Jobs", "⌛ İşlem Bekleyenler"))
        if getattr(self, "_tab_count_done", None) is None:
            self.tabs.setTabText(4, self.get_trans("📦 Delivery/Return", "📦 Teslim/İade"))
        if getattr(self, "_tab_count_delivered", None) is None:
            self.tabs.setTabText(5, self.get_trans("✅ Delivered", "✅ Teslim Edilenler"))
        self.update_main_tab_counts()
        self.tabs.setTabText(6, self.get_trans("👥 Customers", "👥 Müşteriler"))
        self.tabs.setTabText(7, self.get_trans("🏢 Partners", "🏢 Bayiler"))
        self.tabs.setTabText(8, self.get_trans("🧩 Stock", "🧩 Stok"))
        self.tabs.setTabText(9, self.get_trans("🏭 Suppliers", "🏭 Toptancı"))
        self.tabs.setTabText(10, self.get_trans("📋 Detailed Report", "📋 Detaylı Döküm"))
        self.tabs.setTabText(11, self.get_trans("💱 Currency", "💱 Döviz"))
        self.tabs.setTabText(12, self.get_trans("🗑️ Trash", "🗑️ Çöp Kutusu"))
        self.tabs.setTabText(13, self.get_trans("⚙️ Settings", "⚙️ Ayarlar"))
        self.tabs.setTabText(14, self.get_trans("🔐 License", "🔐 Lisans"))
        self.tabs.setTabText(15, self.get_trans("ℹ️ About", "ℹ️ Hakkında"))
        self.tabs.setTabText(16, self.get_trans("🧭 Management", "🧭 Yönetim"))
        virus_tab_text = self.get_trans("Virus Cleaner (Premium)", "Virüs Temizleyici (Premium)") if getattr(self, "is_trial_license", False) else self.get_trans("Virus Cleaner", "Virüs Temizleyici")
        self.tabs.setTabText(17, virus_tab_text)
        if hasattr(self, "global_search_label"):
            self.global_search_label.setText(self.get_trans("Search:", "Genel Arama:"))
        if hasattr(self, "global_search_input"):
            self.global_search_input.setPlaceholderText(self.get_trans(
                "Search reg no, customer, phone, device, fault, note, partner, stock or supplier...",
                "Kayıt no, müşteri, telefon, cihaz, arıza, not, bayi, stok veya toptancı ara..."
            ))
        if hasattr(self, "global_search_button"):
            self.global_search_button.setText(self.get_trans("Search", "Ara"))
        self.refresh_language_sensitive_combo_labels()
        if hasattr(self, "nav_buttons"):
            self.build_sidebar_navigation()
            self.update_sidebar_count(2, getattr(self, "_tab_count_act", 0))
            self.update_sidebar_count(3, getattr(self, "_tab_count_ready", 0))
            self.update_sidebar_count(4, getattr(self, "_tab_count_done", 0))
            self.update_sidebar_count(5, getattr(self, "_tab_count_delivered", 0))
        self.gb_gun.setTitle(self.get_trans("Daily Income", "Günlük Kazanç"))
        self.gb_haf.setTitle(self.get_trans("Weekly Income", "Haftalık Kazanç"))
        self.gb_ay.setTitle(self.get_trans("Monthly Income", "Aylık Kazanç"))
        self.gb_net.setTitle(self.get_trans("Net Vault", "Net Kasa"))
        self.gb_isl.setTitle(self.get_trans("In Progress", "İşlemde Olan"))
        self.gb_bek.setTitle(self.get_trans("Waiting Jobs", "İşlem Bekleyenler"))
        self.gb_teslim_bek.setTitle(self.get_trans("Waiting Delivery", "Teslim Bekleyen"))
        self.gb_iade_bek.setTitle(self.get_trans("Waiting Return Delivery", "İade Teslimi Bekleyen"))
        self.lbl_kasa_title.setText(self.get_trans("Manual Cash Transactions", "Manuel Kasa İşlemleri"))
        self.k_tip.setItemText(0, self.get_trans("Income", "Gelir"))
        self.k_tip.setItemText(1, self.get_trans("Expense", "Gider"))
        if hasattr(self, "k_odeme_tipi"):
            self.populate_payment_method_combo(self.k_odeme_tipi, self.payment_method_from_combo(self.k_odeme_tipi))
        self.k_aciklama.setPlaceholderText(self.get_trans("Description...", "Açıklama..."))
        self.k_tutar.setPlaceholderText(self.get_trans("Amount (₺)", "Tutar (₺)"))
        self.b_kasa_ekle.setText(self.get_trans("Add Transaction", "Kasaya İşle"))
        self.cb_registered_customer.setText(self.get_trans("Select registered customer", "Kayıtlı müşteri seç"))
        self.cb_bayi_kayit.setText(self.get_trans("Select partner", "Bayi seç"))
        self.f_ad.setPlaceholderText(self.get_trans("Customer Name", "Müşteri Adı"))
        self.f_tel.setPlaceholderText(self.get_trans("Phone (optional)", "Telefon (opsiyonel)"))
        self.f_cihaz.setPlaceholderText(self.get_trans("Device Brand / Model", "Cihaz Marka / Model"))
        self.f_ariza.setPlaceholderText(self.get_trans("Complaint / Fault", "Şikayet / Arıza"))
        self.f_not.setPlaceholderText(self.get_trans("Customer note (optional)", "Müşteri notu (opsiyonel)"))
        self.f_yaklasik.setPlaceholderText(self.get_trans("Estimated price (optional ₺)", "Yaklaşık ücret (opsiyonel ₺)"))
        self.sifre_tipi.setItemText(0, self.get_trans("Text Password", "Metin Şifresi"))
        self.sifre_tipi.setItemText(1, self.get_trans("Pattern (Draw)", "Ekran Deseni (Çizim)"))
        self.f_sifre.setPlaceholderText(self.get_trans("Device Password", "Cihaz Şifresi"))
        self.btn_desen.setText(self.get_trans("Draw Pattern", "Desen Çiz"))
        self.cb_sim.setText(self.get_trans("SIM Card", "SIM Kart Var"))
        self.cb_sd.setText(self.get_trans("SD Card", "Hafıza Kartı Var"))
        self.cb_kilif.setText(self.get_trans("Case", "Kılıf Var"))
        self.b_save.setText(self.get_trans("Save Device", "Cihazı Kaydet"))
        self.lbl_yeni_title.setText(self.get_trans("<h2>New Registration</h2>", "<h2>Yeni Cihaz Kaydı</h2>"))
        self.lbl_guv_title.setText(self.get_trans("<b>Security & Accessories:</b>", "<b>Güvenlik ve Aksesuar:</b>"))
        
        self.table_act.setHorizontalHeaderLabels(self.get_trans(["ID", "Reg No", "Customer", "Device", "Fault", "Price", "Time", "Status"], ["ID", "Kayıt No", "Müşteri", "Cihaz", "Arıza", "Fiyat", "Zaman", "Durum"]))
        self.table_ready.setHorizontalHeaderLabels(self.get_trans(["ID", "Reg No", "Customer", "Device", "Fault", "Price", "Time", "Status"], ["ID", "Kayıt No", "Müşteri", "Cihaz", "Arıza", "Fiyat", "Zaman", "Durum"]))
        self.table_done.setHorizontalHeaderLabels(self.get_trans(["ID", "Reg No", "Customer", "Device", "Action", "Price", "Date", "Status", "Delivery", "Payment"], ["ID", "Kayıt No", "Müşteri", "Cihaz", "İşlem", "Ücret", "Tarih", "Durum", "Teslim Durumu", "Ödeme Durumu"]))
        self.table_delivered.setHorizontalHeaderLabels(self.get_trans(["ID", "Reg No", "Customer", "Device", "Action", "Price", "Delivery Date", "Result", "Delivery", "Payment"], ["ID", "Kayıt No", "Müşteri", "Cihaz", "İşlem", "Ücret", "Teslim Tarihi", "Sonuç", "Teslim Durumu", "Ödeme Durumu"]))
        self.tune_service_table_columns(self.table_act, "active")
        self.tune_service_table_columns(self.table_ready, "ready")
        self.tune_service_table_columns(self.table_done, "done")
        self.tune_service_table_columns(self.table_delivered, "done")
        self.table_bayi.setHorizontalHeaderLabels(self.get_trans(["ID", "Reg No", "Device", "Action", "Price", "Status", "Payment", "Date"], ["ID", "Kayıt No", "Cihaz", "İşlem", "Ücret", "Durum", "Ödeme", "Tarih"]))
        self.table_kasa.setHorizontalHeaderLabels(self.get_trans(["ID", "Date", "Type", "Method", "Description", "Amount"], ["ID", "Tarih", "Tip", "Ödeme", "Açıklama", "Tutar"]))
        self.table_stok.setHorizontalHeaderLabels(self.get_trans(["ID", "Stock Code", "Barcode", "Part Name", "Buy Price", "Sell Price", "Stock Qty"], ["ID", "Stok Kodu", "Barkod", "Parça Adı", "Alış Fiyatı", "Satış Fiyatı", "Stok Adedi"]))
        self.table_trash.setHorizontalHeaderLabels(self.get_trans(["ID", "Module", "Content Summary", "Deleted Date", "Time Left"], ["ID", "Modül", "İçerik Özeti", "Silinme Tarihi", "Kalan Süre"]))
        
        self.lbl_kayitli_bayiler.setText(self.get_trans("<b>Registered Partners</b>", "<b>Kayıtlı Bayiler</b>"))
        if "İşlemleri" not in self.lbl_secili_bayi.text() and "Transactions" not in self.lbl_secili_bayi.text(): 
            self.lbl_secili_bayi.setText(self.get_trans("<h2>Select a Partner</h2>", "<h2>Bir Bayi Seçin</h2>"))
            
        self.firm_in.setPlaceholderText(self.get_trans("Supplier Name...", "Toptancı Adı..."))
        self.b_f.setText(self.get_trans("Add Supplier", "Toptancı Ekle"))
        self.lbl_cur_title.setText(self.get_trans("<h2>Live Currency</h2>", "<h2>Canlı Döviz Çevirici</h2>"))
        self.lbl_cur_desc.setText(self.get_trans("Automatically converts.", "Miktarı yazdığınız an otomatik çevirir."))
        self.lbl_set_theme.setText(self.get_trans("<b>UI Theme:</b>", "<b>Arayüz Teması:</b>"))
        self.lbl_set_lang.setText(self.get_trans("<b>System Language:</b>", "<b>Sistem Dili:</b>"))
        self.lbl_ui_scale.setText(self.get_trans("<b>UI Scale (Requires Restart):</b>", "<b>Arayüz Boyutu (Yeniden Başlatma Gerektirir):</b>"))
        self.lbl_font_weight.setText(self.get_trans("<b>Font Weight (Requires Restart):</b>", "<b>Yazı Kalınlığı (Yeniden Başlatma Gerektirir):</b>"))
        if hasattr(self, "lbl_print_format"):
            self.lbl_print_format.setText(self.get_trans("<b>🖨️ Printer Output Format:</b>", "<b>🖨️ Yazıcı Çıktı Formatı:</b>"))
        if hasattr(self, "lbl_record_start_title"):
            self.lbl_record_start_title.setText(self.get_trans("<b>🔢 Record Number Start:</b>", "<b>🔢 Kayıt No Geçiş Ayarı:</b>"))
        if hasattr(self, "lbl_receipt_shop_title"):
            self.lbl_receipt_shop_title.setText(self.get_trans("<b>🏪 Receipt Shop Details:</b>", "<b>🏪 Fiş Bayi Bilgileri:</b>"))
        if hasattr(self, "lbl_wholesaler_cash_title"):
            self.lbl_wholesaler_cash_title.setText(self.get_trans("<b>🏭 Supplier / Cash Settings:</b>", "<b>🏭 Toptancı / Kasa Ayarı:</b>"))
        self.btn_logo.setText(self.get_trans("Change Shop Logo", "Dükkan Logosunu Değiştir"))
        self.shop_name_in.setPlaceholderText(self.get_trans("Shop name on receipt", "Fişte görünecek bayi adı"))
        self.shop_address_in.setPlaceholderText(self.get_trans("Address on receipt", "Fişte görünecek adres"))
        self.btn_shop_save.setText(self.get_trans("Save Shop Details", "Bayi Bilgilerini Kaydet"))
        if hasattr(self, "receipt_simple_cb"):
            self.receipt_simple_cb.setText(self.get_trans("Use simple receipt design", "Basit fiş tasarımını kullan"))
        self.receipt_qr_cb.setText(self.get_trans("Show customer tracking QR on receipt", "Fişte müşteri takip QR göster"))
        if hasattr(self, "record_start_help"):
            self.record_start_help.setText(self.get_trans(
                "If you are moving from another program, enter the last record number used there. Example: entering 4000 makes the next record MF-2026-004001.",
                "Başka programdan geçişte eski programdaki son kayıt numarasını yazın. Örn: 4000 yazılırsa bir sonraki kayıt MF-2026-004001 olur."
            ))
        if hasattr(self, "record_start_in"):
            self.record_start_in.setPlaceholderText(self.get_trans("Last used record no: 4000", "Son kullanılan kayıt no: 4000"))
        if hasattr(self, "btn_record_start_save"):
            self.btn_record_start_save.setText(self.get_trans("Continue After This Number", "Bu Numaradan Sonra Devam Et"))
        self.whl_cash_cb.setText(self.get_trans("Deduct supplier payments from cash", "Toptancı ödemeleri kasadan düşsün"))
        self.finance_visible_cb.setText(self.get_trans("Show income/cash cards on dashboard", "Ana panelde kazanç/kasa kutularını göster"))
        self.btn_finance_password.setText(self.get_trans("Change Income Password", "Kazanç Şifresini Değiştir"))
        self.btn_finance_password_reset.setText(self.get_trans("I Forgot My Income Password", "Kazanç Şifremi Unuttum"))
        self.tray_cb.setText(self.get_trans("Minimize to tray on close", "Kapatıldığında simge durumuna küçülsün"))
        self.startup_cb.setText(self.get_trans("Run automatically at startup", "Bilgisayar açıldığında otomatik başlat"))
        self.btn_renew.setText(self.get_trans("Renew License", "Lisans Yenile (Online / WhatsApp)"))
        self.btn_logout.setText(self.get_trans("Log Out", "Sistemden Çıkış Yap"))
        
        tit = self.get_trans("License Status", "Lisans Durumu")
        acc = self.get_trans("Account", "Hesap")
        exp = self.get_trans("Expiry Date", "Bitiş Tarihi")
        rem = self.get_trans("Remaining Time", "Kalan Süre")
        day = self.get_trans("Days", "Gün")
        
        self.lbl_lic_text.setText(f"<h2>{tit}</h2><p style='font-size:18px;'><b>{acc}:</b> {self.user_email}<br><b>{exp}:</b> {self.bitis_tarihi}<br><b>{rem}:</b> <span style='color:#ef4444;'>{self.lisans_kalan} {day}</span></p>")
        
        for s in self.search_boxes: 
            s.setPlaceholderText(self.get_trans("🔍 Search...", "🔍 Müşteri, Kayıt No veya Cihaz Ara..."))
        for l in self.filter_labels: 
            l.setText(self.get_trans("<b>Filter:</b>", "<b>Filtre:</b>"))
        self.refresh_table_filter_labels()
        self.refresh_party_legend_labels()

    def load_bayi_detay(self, item):
        bayi_adi = item.text()
        bayi_tel = self.partner_phone_by_name(bayi_adi)
        tel_text = f" - {bayi_tel}" if bayi_tel else ""
        self.lbl_secili_bayi.setText(f"<h2>{bayi_adi}{tel_text} İşlemleri</h2>")
        self.table_bayi.setRowCount(0)
        
        toplam_is, top_odenen, top_kalan, cihaz_adeti = 0.0, 0.0, 0.0, 0
        for k, v in self.bayi_records_for_name(bayi_adi):
            cihaz_adeti += 1
            ucret = safe_float(v.get("masraf", "0"))
            odeme = v.get("odeme_durumu", "Ödenmedi")
            durum = v.get("d", "Bilinmiyor")
            c_text = self.device_display_text(v)
            
            m_str = "" if ucret == 0 else f"{format_money(ucret, '')}"
            color = QColor("#2ecc71") if "Teslim" in durum else QColor("#e67e22") 
            if odeme == "Ödendi": 
                color = QColor("#2ecc71")
            elif odeme == "Ödenmedi" and "Teslim" in durum: 
                color = QColor("#ef4444")
            
            o_durum_metin = f"{odeme} ({v.get('odeme_tipi','Nakit')})" if odeme == "Ödendi" else odeme
            self.add_row_to_table(self.table_bayi, [k, v.get("c_no"), c_text, v.get("yapilan_islem", "-"), f"{m_str} ₺" if m_str else "", durum, o_durum_metin, v.get("z")], [color]*8)
            
            if "İade" not in durum and "İptal" not in durum:
                toplam_is += ucret
                if odeme == "Ödendi": 
                    top_odenen += ucret
                else: 
                    top_kalan += ucret
                    
        self.lbl_bayi_adet.setText(f"<b>Toplam Cihaz:</b> {cihaz_adeti}")
        self.lbl_bayi_total.setText(f"<b>Toplam Cari Hacim:</b> {format_money(toplam_is, '₺')}")
        self.lbl_bayi_odenen.setText(f"<b>Kazandırdığı (Ödenen):</b> {format_money(top_odenen, '₺')}")
        self.lbl_bayi_kalan.setText(f"<b>Kalan Borç:</b> {format_money(top_kalan, '₺')}")

    def toggle_blink(self):
        if self.central_widget.isHidden() or self.manager.isHidden(): 
            return
            
        self.blink_state = not self.blink_state
        for tbl in [self.table_act, self.table_ready, self.table_done, self.table_bayi]:
            st_idx = 5 if tbl == self.table_bayi else 7 if tbl in [self.table_act, self.table_ready] else 7
            for r in range(tbl.rowCount()):
                st_item = tbl.item(r, st_idx)
                if st_item:
                    st_text = st_item.text()
                    if tbl == self.table_act:
                        if "Bekliyor" in st_text and "Parça" not in st_text: 
                            st_item.setForeground(QColor("#f1c40f") if self.blink_state else QColor("#888888")) 
                        elif "Parça Bekliyor" in st_text: 
                            st_item.setForeground(QColor("#3584e4") if self.blink_state else QColor("#888888")) 
                    elif tbl == self.table_ready: 
                        st_item.setForeground(QColor("#f59e0b") if self.blink_state else QColor("#888888"))

    def load_wholesalers(self):
        idx = self.w_tabs.currentIndex()
        current_firm = self.w_tabs.tabText(idx) if idx >= 0 else None
        
        self.w_tabs.clear()
        self.w_tables = []
        firms = safe_dict_parse(self.read_user_section("firmalar", default={}))
        if not isinstance(firms, dict):
            firms = {}
        parts = safe_dict_parse(self.read_user_section("toptanci", default={}))
        payments = safe_dict_parse(self.read_user_section("toptanci_odemeler", default={}))
        records = safe_dict_parse(getattr(self, "kayitlar_data", {}) or self.read_user_section("kayitlar", default={}))
        if not isinstance(parts, dict):
            parts = {}
        if not isinstance(payments, dict):
            payments = {}
        if not isinstance(records, dict):
            records = {}
        self.toptanci_data = parts
        
        for fid, fv in firms.items():
            if not isinstance(fv, dict):
                continue
            name = fv.get("ad")
            if not name:
                continue
            tab = QWidget()
            layout = QVBoxLayout(tab)
            top = QHBoxLayout()
            top.addWidget(QLabel(f"<h3>{name}</h3>"))
            
            f_combo = QComboBox()
            f_combo.addItems(["Tümü", "Son 7 Gün", "Son 30 Gün", "Bu Yıl"])
            b_print = QPushButton("Raporu PDF/Yazdır")
            b_print.setStyleSheet("background-color: #9b59b6;")
            b_excel = QPushButton("Excel'e Aktar")
            b_bulk_pay = QPushButton("Toplu Ödeme")
            b_edit = QPushButton("İsmi Düzenle")
            b_del = QPushButton("Sil")
            b_del.setStyleSheet("background-color: #ef4444;")
            
            b_edit.clicked.connect(lambda ch, f=fid, n=name: self.edit_wholesaler(f, n))
            b_del.clicked.connect(lambda ch, f=fid: self.delete_wholesaler(f))
            
            top.addStretch()
            top.addWidget(QLabel("Filtre:"))
            top.addWidget(f_combo)
            top.addWidget(b_print)
            top.addWidget(b_excel)
            top.addWidget(b_bulk_pay)
            top.addWidget(b_edit)
            top.addWidget(b_del)
            layout.addLayout(top)
            
            tbl = self.create_wholesaler_table(["ID", "Parça", "Kullanıldığı Cihaz", "Fiyat ($/₺)", "Durum", "Ödeme", "TL Karşılığı", "Ödeme Tarihi", "Zaman"], name)
            self.w_tables.append(tbl)
            layout.addWidget(tbl)
            cari = QHBoxLayout()
            lbl_total = QLabel("")
            lbl_paid = QLabel("")
            lbl_debt = QLabel("")
            lbl_total.setStyleSheet("color:#38bdf8; font-weight:bold;")
            lbl_paid.setStyleSheet("color:#22c55e; font-weight:bold;")
            lbl_debt.setStyleSheet("color:#ef4444; font-weight:bold;")
            cari.addWidget(lbl_total)
            cari.addSpacing(16)
            cari.addWidget(lbl_paid)
            cari.addSpacing(16)
            cari.addWidget(lbl_debt)
            cari.addStretch()
            layout.addLayout(cari)
            self.w_tabs.addTab(tab, name)
            
            def populate_table(filter_text="Tümü", current_tbl=tbl, current_name=name, l_total=lbl_total, l_paid=lbl_paid, l_debt=lbl_debt):
                current_tbl.setRowCount(0)
                total_tl = 0.0
                paid_tl = 0.0
                paid_nakit = 0.0
                paid_kart = 0.0
                paid_eft = 0.0
                bugun = datetime.datetime.now()
                q_start = self.whl_date_start.date() if hasattr(self, "whl_date_start") else QDate.currentDate().addMonths(-1)
                q_end = self.whl_date_end.date() if hasattr(self, "whl_date_end") else QDate.currentDate()
                
                for pid, pv in parts.items():
                    if not isinstance(pv, dict):
                        continue
                    if pv.get("firma") == current_name:
                        tarih_str = pv.get("zaman", "")
                        gecerli = True
                        if not self.is_qdate_in_range(tarih_str, q_start, q_end):
                            gecerli = False
                        try:
                            fark = (bugun - datetime.datetime.strptime(tarih_str.split(" ")[0], "%d.%m.%Y")).days
                            if filter_text == "Son 7 Gün" and fark > 7: gecerli = False
                            if filter_text == "Son 30 Gün" and fark > 30: gecerli = False
                            if filter_text == "Bu Yıl" and tarih_str.split(".")[2].split(" ")[0] != str(bugun.year): gecerli = False
                        except: pass
                        if not gecerli: continue
                        
                        st = pv.get("durum", "Bilinmiyor")
                        t_str = str(pv.get("tutar", "0"))
                        if "TL" in t_str and "$" not in t_str: 
                            tl_v = safe_float(t_str)
                            d_usd = "- $"
                        else: 
                            tl_v = self.wholesaler_part_tl_value(t_str)
                            d_usd = f"{format_money(safe_float(t_str), '$')}"
                        odeme = pv.get("odeme_durumu", "Ödenmedi")
                        o_tip = pv.get("odeme_tipi", "")
                        odeme_metin = f"{odeme} ({o_tip})" if odeme == "Ödendi" and o_tip else odeme
                        odeme_tarihi = pv.get("odeme_tarihi", "")
                        rec_id = str(pv.get("kid") or pv.get("record_id") or pv.get("kayit_id") or "")
                        rec = records.get(rec_id, {}) if rec_id else {}
                        if not isinstance(rec, dict):
                            rec = {}
                        usage_text = " - "
                        customer = str(pv.get("musteri") or rec.get("m") or "").strip()
                        device = str(pv.get("cihaz") or rec.get("ci") or "").strip()
                        code = str(pv.get("record_code") or rec.get("c_no") or rec_id or "").strip()
                        usage_parts = [x for x in [customer, device, code] if x]
                        if usage_parts:
                            usage_text = " / ".join(usage_parts)
                            
                        row_color = QColor("#22c55e") if odeme == "Ödendi" else QColor("#ef4444")
                        self.add_row_to_table(current_tbl, [pid, pv.get("parca"), usage_text, d_usd, st, odeme_metin, f"{format_money(tl_v, '₺')}", odeme_tarihi, tarih_str], [row_color]*9)
                        if "İade" not in st: 
                            total_tl += tl_v
                            if odeme == "Ödendi":
                                part_paid = safe_float(pv.get("odenen_tutar", tl_v))
                                paid_tl += part_paid
                                if "Kart" in o_tip:
                                    paid_kart += part_paid
                                elif "EFT" in o_tip or "Havale" in o_tip:
                                    paid_eft += part_paid
                                else:
                                    paid_nakit += part_paid
                for pay_id, pay in payments.items():
                    if not isinstance(pay, dict):
                        continue
                    if pay.get("firma") == current_name and self.is_qdate_in_range(pay.get("zaman", ""), q_start, q_end):
                        pay_amount = safe_float(pay.get("tutar", "0"))
                        paid_tl += pay_amount
                        pay_time = pay.get("zaman", "")
                        pay_method = pay.get("odeme_tipi", "Belirtilmemiş")
                        if "Kart" in pay_method:
                            paid_kart += pay_amount
                        elif "EFT" in pay_method or "Havale" in pay_method:
                            paid_eft += pay_amount
                        else:
                            paid_nakit += pay_amount
                        self.add_row_to_table(
                            current_tbl,
                            [f"PAYMENT|{pay_id}", "TOPLU ÖDEME", "-", "-", "Ödeme", f"Ödendi ({pay_method})", f"{format_money(pay_amount, '₺')}", pay_time, pay_time],
                            [QColor("#38bdf8")] * 9
                        )
                l_total.setText(f"Toplam Alım: {format_money(total_tl, '₺')}")
                l_paid.setText(
                    f"Ödenen: {format_money(paid_tl, '₺')}  |  "
                    f"<span style='color:#22c55e;'>Nakit: {format_money(paid_nakit, '₺')}</span>  "
                    f"<span style='color:#38bdf8;'>Kart: {format_money(paid_kart, '₺')}</span>  "
                    f"<span style='color:#f59e0b;'>EFT: {format_money(paid_eft, '₺')}</span>"
                )
                l_debt.setText(f"Kalan: {format_money(total_tl - paid_tl, '₺')}")
                return total_tl, paid_tl
                
            populate_table()
            f_combo.currentTextChanged.connect(lambda text, t=tbl, n=name: populate_table(text, t, n))
            b_print.clicked.connect(lambda ch, t=tbl, n=name, fc=f_combo: self.print_wholesaler_report(t, n, fc.currentText()))
            b_excel.clicked.connect(lambda ch, t=tbl, n=name: self.export_table_to_excel_csv(t, f"{n}_Toptanci_Raporu"))
            b_bulk_pay.clicked.connect(lambda ch, n=name: self.add_wholesaler_bulk_payment(n))
            
        if current_firm:
            for i in range(self.w_tabs.count()):
                if self.w_tabs.tabText(i) == current_firm: 
                    self.w_tabs.setCurrentIndex(i)
                    break

    def print_wholesaler_report(self, table, firm_name, period):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(96)
        secim = QMessageBox.question(self, "Çıktı Türü", "PDF olarak mı kaydetmek istersiniz?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if secim == QMessageBox.StandardButton.Yes:
            path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", f"{firm_name}_Rapor.pdf", "PDF Files (*.pdf)")
            if not path: return
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
        else:
            if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted: return
            
        doc = QTextDocument()
        html = f"<h2>{self.firma_adi} - Toptanci Cari Raporu: {firm_name}</h2><p>Dönem: {period}</p><hr><table border='1' cellpadding='5' style='width:100%; border-collapse:collapse;'>"
        html += "<tr><th>Tarih</th><th>Parça</th><th>Kullanıldığı Cihaz</th><th>Fiyat</th><th>TL</th><th>Durum</th><th>Ödeme</th></tr>"
        for r in range(table.rowCount()): 
            if table.isRowHidden(r):
                continue
            html += f"<tr><td>{table.item(r, 8).text()}</td><td>{table.item(r, 1).text()}</td><td>{table.item(r, 2).text()}</td><td>{table.item(r, 3).text()}</td><td>{table.item(r, 6).text()}</td><td>{table.item(r, 4).text()}</td><td>{table.item(r, 5).text()}</td></tr>"
        
        html += "</table>"
        doc.setHtml(html)
        doc.print(printer)

    def edit_wholesaler(self, fid, old_name):
        d = CustomEditDialog("Düzenle", "Yeni Firma Adı:", old_name, self)
        if d.exec() == QDialog.DialogCode.Accepted: 
            new_name = self.normalize_upper(d.get_text()).strip()
            db.child("users").child(self.user_id).child("firmalar").child(fid).update({"ad": new_name}, self.token)
            self.audit_log("Toptancı Güncelleme", f"{old_name} -> {new_name}", "firmalar", fid, before={"ad": old_name}, after={"ad": new_name})
            self.load_wholesalers()
            
    def delete_wholesaler(self, fid):
        if QMessageBox.question(self, "Uyarı", "Silinsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: 
            self.soft_delete("firmalar", fid)
            self.load_wholesalers()

    def add_wholesaler_bulk_payment(self, firm_name):
        amount_text, ok_amount = QInputDialog.getText(self, "Toplu Ödeme", "Ödenen tutar (₺):")
        amount = safe_float(amount_text)
        if not ok_amount or amount <= 0:
            return
        method, ok_method = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
        if not ok_method:
            return
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        payload = {
            "firma": firm_name,
            "tutar": str(amount),
            "odeme_tipi": method,
            "zaman": now
        }
        res = db.child("users").child(self.user_id).child("toptanci_odemeler").push(payload, self.token)
        payment_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Toptancı Ödemesi", f"{firm_name}: {format_money(amount, '₺')} ({method})", "toptanci_odemeler", payment_id, after=payload)
        self.record_payment_to_cash(f"Toptancı toplu ödeme: {firm_name} ({method})", amount, method, f"toptanci:{firm_name}")
        self.refresh_all_tables()

    def add_wholesaler_part(self, firm_name, default_part="", default_cost=""):
        if not self.require_staff_permission("wholesale", "Toptancı parça ekleme"):
            return
        d_p = CustomEditDialog("Parça Ekle", "Parça Adı:", default_part, self)
        if d_p.exec() != QDialog.DialogCode.Accepted:
            return
        d_c = CustomEditDialog("Parça Ekle", "Maliyet ($):", default_cost, self)
        if d_c.exec() != QDialog.DialogCode.Accepted:
            return
        pay_now = QMessageBox.question(
            self,
            "Ödeme Durumu",
            "Bu parça için ödeme yapıldı mı?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) == QMessageBox.StandardButton.Yes
        data = {
            "firma": firm_name,
            "parca": self.normalize_upper(d_p.get_text()).strip(),
            "tutar": str(safe_float(d_c.get_text())),
            "durum": "Kullanıldı",
            "odeme_durumu": "Ödenmedi",
            "zaman": datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        if pay_now:
            method, ok_method = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
            if ok_method:
                tl_amount = self.wholesaler_part_tl_value(data["tutar"])
                now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
                data.update({"odeme_durumu": "Ödendi", "odeme_tipi": method, "odeme_tarihi": now, "odenen_tutar": str(tl_amount)})
                self.record_payment_to_cash(f"Toptancı ödemesi: {firm_name} - {data['parca']} ({method})", tl_amount, method, f"toptanci:{firm_name}")
        res = db.child("users").child(self.user_id).child("toptanci").push(data, self.token)
        part_id = res.get("name", "") if isinstance(res, dict) else ""
        self.audit_log("Toptancı Parça Ekleme", f"{firm_name} - {data.get('parca', '')}", "toptanci", part_id, after=data)
        self.load_wholesalers()

    def edit_wholesaler_payment(self, payment_id):
        if not self.require_staff_permission("wholesale", "Toptancı ödeme düzenleme"):
            return
        pay = db.child("users").child(self.user_id).child("toptanci_odemeler").child(payment_id).get(self.token).val() or {}
        amount_text, ok_amount = QInputDialog.getText(self, "Ödeme Düzenle", "Ödenen tutar (₺):", text=str(pay.get("tutar", "")))
        amount = safe_float(amount_text)
        if not ok_amount or amount <= 0:
            return
        current_method = pay.get("odeme_tipi", "Nakit")
        methods = ["Nakit", "Kredi Kartı", "EFT / Havale"]
        method, ok_method = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme yöntemi:", methods, methods.index(current_method) if current_method in methods else 0, False)
        if not ok_method:
            return
        update_data = {
            "tutar": str(amount),
            "odeme_tipi": method,
            "zaman": pay.get("zaman", datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))
        }
        db.child("users").child(self.user_id).child("toptanci_odemeler").child(payment_id).update(update_data, self.token)
        self.audit_log("Toptancı Ödeme Güncelleme", f"{pay.get('firma', '')}: {format_money(amount, '₺')} ({method})", "toptanci_odemeler", payment_id, before=pay, after=update_data)
        self.load_wholesalers()

    def delete_wholesaler_payment(self, payment_id):
        if not self.require_staff_permission("wholesale", "Toptancı ödeme silme"):
            return
        if QMessageBox.question(self, "Ödemeyi Sil", "Bu ödeme kaydı silinsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            pay = db.child("users").child(self.user_id).child("toptanci_odemeler").child(payment_id).get(self.token).val() or {}
            db.child("users").child(self.user_id).child("toptanci_odemeler").child(payment_id).remove(self.token)
            self.audit_log("Toptancı Ödeme Silme", f"{pay.get('firma', '')} ödemesi silindi", "toptanci_odemeler", payment_id, before=pay)
            self.load_wholesalers()

    def wholesaler_menu(self, pos, table, firm_name):
        if not self.require_staff_permission("wholesale", "Toptancı işlemi"):
            return
        row = table.rowAt(pos.y())
        m = QMenu(self)
        add_new = None
        add_similar = None
        show_payment = None
        m_kul = m_pay = i_bas = i_tes = p_sil = None
        pid = ""
        if row >= 0:
            pid_item = table.item(row, 0)
            pid = pid_item.text() if pid_item else ""
            if pid.startswith("PAYMENT|"):
                edit_payment = m.addAction("✏️ Ödeme Bilgisini Düzenle")
                delete_payment = m.addAction("🗑️ Ödemeyi Sil")
            elif pid:
                add_similar = m.addAction("➕ Bu parçaya benzer yeni parça ekle")
                m.addSeparator()
                m_kul = m.addAction("✅ Kullanıldı Olarak İşaretle")
                m_pay = m.addAction("💳 Ödeme Durumunu Değiştir")
                i_bas = m.addAction("🔄 İade Başlat")
                i_tes = m.addAction("✅ İade Teslim Edildi")
                m.addSeparator()
                p_sil = m.addAction("🗑️ Parçayı Sil (Çöp Kutusuna Gönder)")
            else:
                row = -1
        else:
            add_new = m.addAction("➕ Yeni Parça Ekle")
            
        action = m.exec(QCursor.pos())
        if action == add_new:
            self.add_wholesaler_part(firm_name)
        elif row >= 0 and pid.startswith("PAYMENT|"):
            payment_id = pid.split("|", 1)[1]
            if action == edit_payment:
                self.edit_wholesaler_payment(payment_id)
            elif action == delete_payment:
                self.delete_wholesaler_payment(payment_id)
        elif action == add_similar:
            part_name = table.item(row, 1).text() if table.item(row, 1) else ""
            self.add_wholesaler_part(firm_name, part_name)
        elif row >= 0 and pid:
            if action == m_kul: 
                db.child("users").child(self.user_id).child("toptanci").child(pid).update({"durum": "Kullanıldı"}, self.token)
                self.audit_log("Toptancı Parça Durumu", f"{firm_name}: parça kullanıldı", "toptanci", pid, after={"durum": "Kullanıldı"})
                self.load_wholesalers()
            elif action == m_pay:
                p_data = db.child("users").child(self.user_id).child("toptanci").child(pid).get(self.token).val() or {}
                durum, ok_durum = QInputDialog.getItem(self, "Ödeme Durumu", "Ödeme durumu:", ["Ödendi", "Ödenmedi"], 0 if p_data.get("odeme_durumu") == "Ödendi" else 1, False)
                if ok_durum:
                    update_data = {"odeme_durumu": durum}
                    if durum == "Ödendi":
                        method, ok_method = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
                        if not ok_method:
                            return
                        tl_amount = self.wholesaler_part_tl_value(p_data.get("tutar", "0"))
                        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
                        update_data.update({"odeme_tipi": method, "odeme_tarihi": now, "odenen_tutar": str(tl_amount)})
                        self.record_payment_to_cash(f"Toptancı ödemesi: {firm_name} - {p_data.get('parca', '')} ({method})", tl_amount, method, f"toptanci:{pid}")
                    db.child("users").child(self.user_id).child("toptanci").child(pid).update(update_data, self.token)
                    self.audit_log("Toptancı Ödeme Durumu", f"{firm_name} - {p_data.get('parca', '')}: {durum}", "toptanci", pid, before={"odeme_durumu": p_data.get("odeme_durumu")}, after=update_data)
                    self.refresh_all_tables()
            elif action == i_bas: 
                d_n = CustomEditDialog("İade", "Not:", "", self)
                if d_n.exec() == QDialog.DialogCode.Accepted: 
                    update_data = {"durum": "İade Bekliyor", "not": d_n.get_text()}
                    db.child("users").child(self.user_id).child("toptanci").child(pid).update(update_data, self.token)
                    self.audit_log("Toptancı İade", f"{firm_name}: iade başlatıldı", "toptanci", pid, after=update_data)
                    self.load_wholesalers()
            elif action == i_tes: 
                db.child("users").child(self.user_id).child("toptanci").child(pid).update({"durum": "İade Edildi"}, self.token)
                self.audit_log("Toptancı İade", f"{firm_name}: iade teslim edildi", "toptanci", pid, after={"durum": "İade Edildi"})
                self.load_wholesalers()
            elif action == p_sil: 
                self.soft_delete("toptanci", pid)
                self.load_wholesalers()

    def wholesaler_double_click(self, row, col, table):
        if not self.require_staff_permission("wholesale", "Toptancı düzenleme"):
            return
        pid = table.item(row, 0).text()
        if not pid:
            return
        p_data = db.child("users").child(self.user_id).child("toptanci").child(pid).get(self.token).val()
        h = table.horizontalHeaderItem(col).text()
        
        if h == "Parça":
            if p_data and p_data.get("kid"):
                c_data = db.child("users").child(self.user_id).child("kayitlar").child(p_data.get("kid")).get(self.token).val()
                if c_data: 
                    QMessageBox.information(self, "Parça Cihaz Bilgisi", f"Müşteri: {c_data.get('m')}\nCihaz: {c_data.get('ci')}")
            d = CustomEditDialog("Düzenle", "Parça:", p_data.get("parca",""), self)
            if d.exec() == QDialog.DialogCode.Accepted: 
                db.child("users").child(self.user_id).child("toptanci").child(pid).update({"parca": d.get_text()}, self.token)
                self.load_wholesalers()
        elif "Fiyat" in h:
            d = CustomEditDialog("Düzenle", "Maliyet ($):", str(safe_float(p_data.get("tutar","0"))), self)
            if d.exec() == QDialog.DialogCode.Accepted: 
                db.child("users").child(self.user_id).child("toptanci").child(pid).update({"tutar": str(safe_float(d.get_text()))}, self.token)
                self.load_wholesalers()

    def open_readonly_record_menu(self, kid, record):
        menu = QMenu(self)
        b_info = menu.addAction(self.get_trans("👁️ Show Device Info", "👁️ Cihaz Bilgilerini Göster"))
        b_dossier = menu.addAction(self.get_trans("📁 Smart Device File", "📁 Akıllı Cihaz Dosyası"))
        b_gallery = menu.addAction(self.get_trans("📷 View Photos", "📷 Fotoğrafları Görüntüle"))
        b_note = menu.addAction(self.get_trans("📝 View Note", "📝 Notu Görüntüle"))
        action = menu.exec(QCursor.pos())
        if action == b_info:
            InfoDialog(record, kid, self, self).exec()
        elif action == b_dossier:
            self.show_device_dossier(kid, record)
        elif action == b_gallery:
            ViewImageDialog(record, kid, self, 1, self).exec()
        elif action == b_note:
            ReadOnlyDialog(self.get_trans("Device Note", "Cihaz Notu"), self.format_record_note_text(record.get("not", "")), self).exec()

    def open_menu(self, pos, table):
        if table == self.table_stok: return self.open_stok_menu(pos, table)
        if table == self.table_kasa: return self.open_kasa_menu(pos, table)
        if table == self.table_trash: return self.open_trash_menu(pos, table)
        
        row = table.rowAt(pos.y())
        if row < 0: return
        col = table.columnAt(pos.x())
        
        kid = table.item(row, 0).text()
        v = self.get_local_record(kid)
        if not v: 
            return self.refresh_all_tables()
        if not self.staff_can(self.record_edit_permission_for_table(table, v)):
            return self.open_readonly_record_menu(kid, v)
        header = table.horizontalHeaderItem(col).text() if col >= 0 and table.horizontalHeaderItem(col) else ""
        service_context_tables = [self.table_act, self.table_ready, self.table_done]
        if table not in service_context_tables and self.open_cell_context_menu(table, row, col, kid, v, header):
            return
            
        m = QMenu(self)
        
        if table in [self.table_musteri_gecmis, self.table_dokum]:
            b_info = m.addAction(self.get_trans("👁️ Show Device Info", "👁️ Cihaz Bilgilerini Göster"))
            b_adv_report = m.addAction(self.get_trans("📋 Detailed View", "📋 Detaylı Görüntüle"))
            action = m.exec(QCursor.pos())
            if action == b_info:
                InfoDialog(v, kid, self, self).exec()
            elif action == b_adv_report: 
                self.show_advanced_device_report(kid)
            return
            
        b_wp = m.addAction(self.get_trans("💬 Send WhatsApp Message", "💬 WhatsApp Mesajı Gönder"))
        b_status_link = m.addAction(self.get_trans("🔎 Customer Tracking Link", "🔎 Müşteri Takip Linki"))
        b_dossier = m.addAction(self.get_trans("📁 Smart Device File", "📁 Akıllı Cihaz Dosyası"))
        approval_menu = m.addMenu(self.get_trans("✅ Customer Approval", "✅ Müşteri Onayı"))
        b_approval_request = approval_menu.addAction(self.get_trans("Send Approval Message", "Onay Mesajı Gönder"))
        b_approval_ok = approval_menu.addAction(self.get_trans("Mark Approved", "Onaylandı İşaretle"))
        b_approval_reject = approval_menu.addAction(self.get_trans("Mark Rejected", "Reddedildi İşaretle"))
        m.addSeparator()
        photo_menu = m.addMenu(self.get_trans("📷 Photos", "📷 Fotoğraflar"))
        b_gallery = photo_menu.addAction(self.get_trans("View Photos", "Fotoğrafları Görüntüle"))
        b_photo_add = photo_menu.addAction(self.get_trans("Add Photo", "Fotoğraf Ekle"))
        b_inf = m.addAction(self.get_trans("👁️ Show Device Info", "👁️ Cihaz Bilgilerini Göster"))
        m.addSeparator()
        finance_allowed = self.staff_can("finance")
        receipt_menu = m.addMenu(self.get_trans("🧾 Receipt", "🧾 Fiş")) if finance_allowed else None
        b_receipt_print = receipt_menu.addAction(self.get_trans("Print Receipt", "Fişi Yazdır")) if receipt_menu else None
        b_receipt_preview = receipt_menu.addAction(self.get_trans("Show Receipt", "Fişi Göster")) if receipt_menu else None
        b_receipt_pdf = receipt_menu.addAction(self.get_trans("Save Receipt PDF", "Fişi PDF Kaydet")) if receipt_menu else None
        label_menu = m.addMenu(self.get_trans("🏷️ Label", "🏷️ Etiket"))
        b_label_print = label_menu.addAction(self.get_trans("Print Label", "Etiketi Yazdır"))
        b_label_preview = label_menu.addAction(self.get_trans("Show Label", "Etiketi Göster"))
        b_label_pdf = label_menu.addAction(self.get_trans("Save Label PDF", "Etiketi PDF Kaydet"))
        m.addSeparator()
        note_menu = m.addMenu(self.get_trans("📝 Notes", "📝 Notlar"))
        b_not_add = note_menu.addAction(self.get_trans("Add Note", "Not Ekle"))
        b_not_gor = note_menu.addAction(self.get_trans("View Note", "Notu Görüntüle"))
        b_not_duz = note_menu.addAction(self.get_trans("Edit Note", "Notu Düzenle"))
        b_not_gec = note_menu.addAction(self.get_trans("Note History", "Not Geçmişi"))
        b_audit = m.addAction(self.get_trans("🕘 Activity History", "🕘 İşlem Geçmişi"))
        b_fault_add = m.addAction(self.get_trans("⚠️ Add Extra Fault", "⚠️ Ek Arıza Ekle"))
        m.addSeparator()
        
        if table == self.table_bayi:
            b_add_bayi_device = m.addAction(self.get_trans("➕ Add New Device for This Partner", "➕ Bu Bayiye Yeni Cihaz Ekle"))
            m.addSeparator()
        else: 
            b_add_bayi_device = None
            
        is_done_table = table in [self.table_done, getattr(self, "table_delivered", None)]
        upd = m.addAction(self.get_trans("🔄 Update Status", "🔄 Durumu Güncelle")) if not is_done_table else None
        done_status_action = m.addAction(self.get_trans("🔄 Change Service Result", "🔄 Servis Sonucunu Değiştir")) if is_done_table else None
        edit_price = m.addAction(self.get_trans("💰 Enter / Edit Price Info", "💰 Fiyat Bilgisi Gir / Düzenle")) if finance_allowed and table in [self.table_act, self.table_ready, self.table_done] else None
        part_menu = m.addMenu(self.get_trans("🧩 Add Part", "🧩 Parça Ekle"))
        use_stock_part = part_menu.addAction(self.get_trans("From Stock", "Stoktan"))
        add_p = part_menu.addAction(self.get_trans("From Supplier", "Toptancıdan")) if self.staff_can("wholesale") else None
        add_other_part = part_menu.addAction(self.get_trans("Other", "Diğer"))
        delivery_status_action = m.addAction(self.get_trans("📦 Delivery Status", "📦 Teslim Durumu")) if is_done_table else None
        delivery_date_action = m.addAction(self.get_trans("📅 Edit Delivery Date", "📅 Teslim Tarihini Düzenle")) if is_done_table else None
        tog_pay = m.addAction(self.get_trans("💳 Change Payment Status / Type", "💳 Ödeme Durumunu / Tipi Değiştir")) if finance_allowed and table in [self.table_done, getattr(self, "table_delivered", None), self.table_bayi, self.table_ready] else None
        m.addSeparator()
        del_rec = m.addAction(self.get_trans("🗑️ Delete Record (Move to Trash)", "🗑️ Kaydı Sil (Çöp Kutusuna Gönder)")) if self.staff_can("trash") else None
        
        action = m.exec(QCursor.pos())
        
        if b_add_bayi_device and action == b_add_bayi_device:
            self.cb_bayi_kayit.setChecked(True)
            for idx in range(self.combo_bayi.count()):
                if self.combo_bayi.itemText(idx) == v.get("m"): 
                    self.combo_bayi.setCurrentIndex(idx)
                    break
            self.tabs.setCurrentIndex(1)
            return
            
        if del_rec and action == del_rec:
            if QMessageBox.question(self, "Emin misiniz?", "Kayıt silinsin mi?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes: 
                if self.soft_delete("kayitlar", kid):
                    self.refresh_all_tables()
        elif action == b_wp: 
            self.send_whatsapp(kid)
        elif action == b_gallery: 
            ViewImageDialog(v, kid, self, 1, self).exec()
        elif action == b_photo_add:
            PhotoDialog(kid, self.user_id, NETLIFY_URL, self, 1).exec()
            self.touch_record_sync_meta(kid, "upsert")
            try:
                fresh_record = db.child("users").child(self.user_id).child("kayitlar").child(kid).get(self.token).val()
                if isinstance(fresh_record, dict):
                    self.apply_stream_record_change(kid, fresh_record, replace=True)
                    self.refresh_record_views_after_stream()
            except Exception:
                pass
        elif action == b_inf: 
            InfoDialog(v, kid, self, self).exec()
        elif b_receipt_print and action == b_receipt_print:
            self.print_receipt(v, "print")
        elif b_receipt_pdf and action == b_receipt_pdf:
            self.print_receipt(v, "pdf")
        elif b_receipt_preview and action == b_receipt_preview:
            self.print_receipt(v, "preview")
        elif action == b_label_print:
            label_data = dict(v)
            label_data["record_id"] = kid
            self.print_device_label(label_data, "print")
        elif action == b_label_preview:
            label_data = dict(v)
            label_data["record_id"] = kid
            self.print_device_label(label_data, "preview")
        elif action == b_label_pdf:
            label_data = dict(v)
            label_data["record_id"] = kid
            self.print_device_label(label_data, "pdf")
        elif action == b_status_link:
            self.publish_public_status(kid)
            self.show_customer_status_link(kid, v)
        elif action == b_dossier:
            self.show_device_dossier(kid)
        elif action == b_approval_request:
            self.request_customer_approval(kid, v)
        elif action == b_approval_ok:
            self.set_customer_approval_status(kid, v, "Onaylandı")
        elif action == b_approval_reject:
            self.set_customer_approval_status(kid, v, "Reddedildi")
        elif action == b_not_add:
            self.add_record_note(kid, v)
        elif action == b_not_gor: 
            if self.update_record_fields(kid, {"not_okundu": True}, "Not okundu işaretleme"):
                self.refresh_all_tables()
            not_metni = v.get("not", "") or ""
            ReadOnlyDialog("Cihaz Notu", self.format_record_note_text(not_metni), self).exec()
        elif action == b_not_duz:
            eski_not = v.get("not", "") or ""
            dlg = CustomEditDialog("Not Düzenle", "Cihaz Notu:", str(eski_not), self, is_multiline=True)
            if dlg.exec() == QDialog.DialogCode.Accepted: 
                text = self.normalize_upper(dlg.get_text()).strip()
                try:
                    if not self.update_record_fields(kid, {"not": text, "not_okundu": False}, "Not düzenleme"):
                        return
                    self.append_note_history(kid, text, "Düzenlendi")
                    self.log_record_action(kid, "Not düzenlendi", audit=False)
                    self.refresh_all_tables()
                except Exception as e:
                    QMessageBox.warning(self, "Not Düzenlenemedi", f"Not kaydedilemedi:\n{e}")
        elif action == b_not_gec:
            ReadOnlyDialog("Not Geçmişi", self.format_note_history_text(v.get("not_gecmisi", {})), self).exec()
        elif action == b_audit:
            ReadOnlyDialog("İşlem Geçmişi", self.format_record_activity_text(kid, v), self).exec()
        elif action == b_fault_add:
            dlg_fault = CustomEditDialog("Ek Arıza", "Eklenecek arıza:", "", self)
            if dlg_fault.exec() == QDialog.DialogCode.Accepted:
                fault = self.normalize_upper(dlg_fault.get_text()).strip()
            else:
                fault = ""
            if fault:
                faults = self.get_faults(v)
                if fault not in faults:
                    faults.append(fault)
                if not self.update_record_fields(kid, {"a": faults[0] if faults else "", "arizalar": faults}, "Ek arıza"):
                    return
                self.publish_public_status(kid)
                self.refresh_all_tables()
        elif upd and action == upd: 
            if table in [self.table_act, self.table_ready]:
                status_options = ["İşlem Bekliyor", "Tamirde", "Parça Bekliyor", "İşlemleri Tamamlandı", "Müşteriye Teslim Edildi"]
            else:
                status_options = ["Teslim Bekliyor", "İade Bekliyor", "Müşteriye Teslim Edildi"]
            new_s, ok = QInputDialog.getItem(self, "Güncelle", "Durum:", status_options, 0, False)
            if ok:
                status_update = {"d": new_s}
                if new_s == "Teslim Bekliyor":
                    status_update["d"] = "Teslim Bekliyor"
                    status_update["teslim_durumu"] = "Teslim Bekliyor"
                    status_update["teslim_tarihi"] = ""
                elif new_s == "İade Bekliyor":
                    status_update["d"] = "İade Bekliyor"
                    status_update["teslim_durumu"] = "Teslim Bekliyor"
                    status_update["teslim_tarihi"] = ""
                elif new_s == "İşlemleri Tamamlandı":
                    status_update["teslim_durumu"] = "Teslim Bekliyor"
                    status_update["teslim_tarihi"] = ""
                elif new_s == "Müşteriye Teslim Edildi":
                    status_plain = self.normalize_upper(str(v.get("d", "") or "")).replace("İ", "I")
                    is_iade_flow = "IADE" in status_plain
                    payment_update = self.ask_delivery_payment_update(v)
                    if payment_update is None:
                        return
                    status_update["d"] = "İade Edildi" if is_iade_flow else "Teslim Edildi"
                    status_update["teslim_durumu"] = "Müşteriye Teslim Edildi"
                    status_update["teslim_tarihi"] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
                    status_update.update(payment_update)
                elif new_s == "İade Edildi":
                    status_update["teslim_durumu"] = "Teslim Bekliyor"
                    status_update["teslim_tarihi"] = ""
                if not self.update_record_fields(kid, status_update, "Durum güncelleme"):
                    return
                self.log_record_action(kid, f"Durum güncellendi: {new_s}")
                if new_s in ["Hazır", "İşlemleri Tamamlandı", "Teslim Bekliyor", "Müşteriye Teslim Edildi"]:
                    dlg_i = self.create_operation_dialog("İşlem", v.get("yapilan_islem",""))
                    if dlg_i.exec() == QDialog.DialogCode.Accepted:
                        operation_text = self.remember_operation_text(dlg_i.get_text())
                        m_val = safe_float(v.get("masraf", "0"))
                        dlg_u = CustomEditDialog("Ücret", "Ücret (₺):", "" if m_val == 0 else f"{m_val:.2f}", self)
                        if dlg_u.exec() == QDialog.DialogCode.Accepted:
                            odeme_durumu = "Ödenmedi"
                            o_tip = v.get("odeme_tipi", "Nakit")
                            if new_s == "Teslim Edildi":
                                odeme_durumu, ok_odeme = QInputDialog.getItem(self, "Ödeme Durumu", "Ödeme durumu:", ["Ödendi", "Ödenmedi"], 0, False)
                                if ok_odeme and odeme_durumu == "Ödendi":
                                    o_tip, ok_tip = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme Yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
                                    if not ok_tip:
                                        o_tip = v.get("odeme_tipi", "Nakit")
                                elif not ok_odeme:
                                    odeme_durumu = "Ödenmedi"
                            extra_update = {"yapilan_islem": operation_text, "masraf": str(safe_float(dlg_u.get_text()))}
                            if new_s != "Müşteriye Teslim Edildi":
                                extra_update.update({"odeme_durumu": odeme_durumu, "odeme_tipi": o_tip})
                            if not self.update_record_fields(kid, extra_update, "İşlem/ücret güncelleme"):
                                return
                            self.log_record_action(kid, f"İşlem/ücret güncellendi: {operation_text} - {safe_float(dlg_u.get_text())} ₺")
                self.publish_public_status(kid)
                self.refresh_all_tables()
        elif done_status_action and action == done_status_action:
            status_options = ["İşlemleri Tamamlandı", "İade Edildi"]
            current_status = v.get("d", "İşlemleri Tamamlandı")
            idx = status_options.index(current_status) if current_status in status_options else 0
            new_s, ok = QInputDialog.getItem(self, "Servis Sonucu", "Servis sonucu:", status_options, idx, False)
            if ok:
                update_data = {"d": new_s, "teslim_durumu": "Teslim Bekliyor", "teslim_tarihi": ""}
                if not self.update_record_fields(kid, update_data, "Servis sonucu güncelleme"):
                    return
                self.log_record_action(kid, f"Servis sonucu güncellendi: {new_s}")
                self.publish_public_status(kid)
                self.refresh_all_tables()
        elif edit_price and action == edit_price:
            self.edit_record_price(kid, v)
        elif delivery_status_action and action == delivery_status_action:
            self.change_record_delivery_status(kid, v)
        elif delivery_date_action and action == delivery_date_action:
            self.edit_record_delivery_date(kid, v)
        elif add_p and action == add_p: 
            self.add_supplier_part_for_record(kid)
        elif action == use_stock_part:
            self.use_stock_part_for_record(kid)
        elif action == add_other_part:
            self.add_other_part_for_record(kid)
        elif tog_pay and action == tog_pay:
            mevcut = v.get("odeme_durumu", "Ödenmedi")
            default_idx = 0 if mevcut == "Ödendi" else 1
            yeni_durum, ok_durum = QInputDialog.getItem(self, "Ödeme Durumu", "Ödeme durumu:", ["Ödendi", "Ödenmedi"], default_idx, False)
            if ok_durum:
                update_data = {"odeme_durumu": yeni_durum}
                if yeni_durum == "Ödendi":
                    o_tip, ok_tip = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme Yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
                    update_data["odeme_tipi"] = o_tip if ok_tip else v.get("odeme_tipi", "Nakit")
                if not self.update_record_fields(kid, update_data, "Ödeme durumu güncelleme"):
                    return
                self.log_record_action(kid, f"Ödeme durumu güncellendi: {yeni_durum}")
                self.publish_public_status(kid)
                self.refresh_all_tables()

    def add_record_note(self, kid, record):
        dlg = CustomEditDialog("Not Ekle", "Eklenecek not:", "", self, is_multiline=True)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        text = self.normalize_upper(dlg.get_text()).strip()
        if not text:
            return
        old_note = str(record.get("not", "") or "").strip()
        new_note = f"{old_note}\n{text}".strip() if old_note else text
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        try:
            if not self.update_record_fields(kid, {"not": new_note, "not_okundu": False}, "Not ekleme"):
                return
        except Exception as e:
            QMessageBox.warning(self, "Not Eklenemedi", f"Not kaydedilemedi:\n{e}")
            return
        self.append_note_history(kid, text, "Eklendi")
        self.log_record_action(kid, "Not eklendi", audit=False)
        self.refresh_all_tables()

    def add_supplier_part_for_record(self, kid):
        if not self.require_staff_permission("wholesale", "Toptancıdan parça ekleme"):
            return
        f_d = safe_dict_parse(db.child("users").child(self.user_id).child("firmalar").get(self.token).val() or {})
        if not isinstance(f_d, dict):
            f_d = {}
        f_n = [val.get("ad") for val in f_d.values() if isinstance(val, dict) and val.get("ad")]
        if not f_n:
            QMessageBox.information(self, "Toptancı", "Önce Toptancı sekmesinden bir toptancı ekleyin.")
            return
        dlg = PartDialog(f_n, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            p, c, f = dlg.get_data()
            p = self.normalize_upper(p).strip()
            record = safe_dict_parse(db.child("users").child(self.user_id).child("kayitlar").child(kid).get(self.token).val() or {})
            if not isinstance(record, dict):
                record = {}
            db.child("users").child(self.user_id).child("toptanci").push({
                "firma": f,
                "parca": p,
                "tutar": str(safe_float(c)),
                "durum": "Kullanıldı",
                "odeme_durumu": "Ödenmedi",
                "zaman": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
                "kid": kid,
                "record_code": str(record.get("c_no", "") or ""),
                "musteri": str(record.get("m", "") or ""),
                "cihaz": str(record.get("ci", "") or "")
            }, self.token)
            self.log_record_action(kid, f"Toptancıdan parça eklendi: {p}")
            self.load_wholesalers()
            self.refresh_all_tables()

    def add_other_part_for_record(self, kid):
        part_dlg = CustomEditDialog("Diğer Parça", "Parça / işlem adı:", "", self)
        if part_dlg.exec() != QDialog.DialogCode.Accepted:
            return
        part_name = self.normalize_upper(part_dlg.get_text()).strip()
        if not part_name:
            return
        qty_text, ok_qty = QInputDialog.getText(self, "Diğer Parça", "Adet:", text="1")
        if not ok_qty:
            return
        cost_text, ok_cost = QInputDialog.getText(self, "Diğer Parça", "Tutar (₺, opsiyonel):", text="0")
        if not ok_cost:
            return
        qty = safe_float(qty_text, 1)
        cost = safe_float(cost_text, 0)
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        db.child("users").child(self.user_id).child("kayitlar").child(kid).child("kullanilan_parcalar").push({
            "parca": part_name,
            "adet": qty if qty > 0 else 1,
            "alis": cost,
            "satis": cost,
            "birim": "₺",
            "zaman": now,
            "source": "diger"
        }, self.token)
        self.touch_record_sync_meta(kid, "upsert")
        self.log_record_action(kid, f"Diğer parça eklendi: {part_name} x {self.format_quantity(qty)}")
        self.refresh_all_tables()

    def open_cell_context_menu(self, table, row, col, kid, record, header):
        if table in [self.table_musteri_gecmis, self.table_dokum] or col <= 0:
            return False
        h = self.normalize_upper(header)
        action_title = None
        action_kind = None
        if "MÜŞTERİ" in h or "CUSTOMER" in h:
            if self.is_bayi_record(record):
                action_title, action_kind = "Bayi Adı Bayiler Sekmesinden Düzenlenir", "bayi_info"
            else:
                action_title, action_kind = "Müşteri Adını Değiştir", "double"
        elif "CİHAZ" in h or "DEVICE" in h:
            action_title, action_kind = "Cihaz Adını Değiştir", "double"
        elif "ARIZA" in h or "FAULT" in h:
            action_title, action_kind = "Arızayı Düzenle", "double"
        elif "İŞLEM" in h or "ACTION" in h:
            action_title, action_kind = "Yapılan İşlemi Düzenle", "double"
        elif "ÜCRET" in h or "FİYAT" in h or "PRICE" in h:
            action_title, action_kind = "Fiyat Bilgisini Düzenle", "double"
        elif "ÖDEME" in h or "PAYMENT" in h:
            action_title, action_kind = "Ödeme Durumunu Değiştir", "payment"
        elif ("TESL" in h and ("TAR" in h or "DATE" in h)) or "DELIVERY DATE" in h:
            action_title, action_kind = self.get_trans("Edit Delivery Date", "Teslim Tarihini Düzenle"), "delivery_date"
        elif "TESL" in h or "DELIVERY" in h:
            action_title, action_kind = self.get_trans("Change Delivery Status", "Teslim Durumunu Değiştir"), "delivery"
        elif "DURUM" in h or "STATUS" in h:
            is_done_table = table in [self.table_done, getattr(self, "table_delivered", None)]
            action_title = "Servis Sonucunu Değiştir" if is_done_table else "Durumu Güncelle"
            action_kind = "done_status" if is_done_table else "status"
        else:
            return False

        menu = QMenu(self)
        primary = menu.addAction(action_title)
        delivery_date = None
        if action_kind == "delivery":
            delivery_date = menu.addAction(self.get_trans("Edit Delivery Date", "Teslim Tarihini Düzenle"))
        menu.addSeparator()
        dossier = menu.addAction("Akıllı Cihaz Dosyası")
        approval = menu.addAction("Müşteri Onay Mesajı Gönder")
        info = menu.addAction("Cihaz Bilgilerini Göster")
        action = menu.exec(QCursor.pos())
        if action == primary:
            if action_kind == "double":
                self.handle_double_click(row, col, table)
            elif action_kind == "bayi_info":
                QMessageBox.information(self, "Bayi Düzenleme", "Bayi adı işlem, bekleyen ve teslim/iade listelerinden değiştirilemez. Bayi bilgisi yalnızca Bayiler sekmesinden düzenlenebilir.")
            elif action_kind == "payment":
                self.change_record_payment(kid, record)
            elif action_kind == "delivery":
                self.change_record_delivery_status(kid, record)
            elif action_kind == "delivery_date":
                self.edit_record_delivery_date(kid, record)
            elif action_kind == "done_status":
                self.change_done_service_status(kid, record)
            elif action_kind == "status":
                self.change_record_status(kid, record, table)
            return True
        if delivery_date and action == delivery_date:
            self.edit_record_delivery_date(kid, record)
            return True
        if action == info:
            InfoDialog(record, kid, self, self).exec()
            return True
        if action == dossier:
            self.show_device_dossier(kid)
            return True
        if action == approval:
            self.request_customer_approval(kid, record)
            return True
        return True

    def change_record_payment(self, kid, record):
        if not self.require_staff_permission("finance", "Ödeme düzenleme"):
            return
        mevcut = record.get("odeme_durumu", "Ödenmedi")
        default_idx = 0 if mevcut == "Ödendi" else 1
        yeni_durum, ok_durum = QInputDialog.getItem(self, "Ödeme Durumu", "Ödeme durumu:", ["Ödendi", "Ödenmedi"], default_idx, False)
        if not ok_durum:
            return
        update_data = {"odeme_durumu": yeni_durum}
        if yeni_durum == "Ödendi":
            o_tip, ok_tip = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme Yöntemi:", ["Nakit", "Kredi Kartı", "EFT / Havale"], 0, False)
            update_data["odeme_tipi"] = o_tip if ok_tip else record.get("odeme_tipi", "Nakit")
        if not self.update_record_fields(kid, update_data, "Ödeme durumu güncelleme"):
            return
        self.log_record_action(kid, f"Ödeme durumu güncellendi: {yeni_durum}")
        self.publish_public_status(kid)
        self.refresh_all_tables()

    def ask_delivery_payment_update(self, record):
        mevcut = record.get("odeme_durumu", "Ödenmedi")
        default_idx = 0 if mevcut == "Ödendi" else 1
        yeni_durum, ok_durum = QInputDialog.getItem(
            self,
            "Teslim Ödemesi",
            "Teslim sırasında ücret alındı mı?",
            ["Ödendi", "Ödenmedi"],
            default_idx,
            False
        )
        if not ok_durum:
            return None
        update_data = {"odeme_durumu": yeni_durum}
        if yeni_durum == "Ödendi":
            mevcut_tip = record.get("odeme_tipi", "Nakit")
            tipler = ["Nakit", "Kredi Kartı", "EFT / Havale"]
            tip_idx = tipler.index(mevcut_tip) if mevcut_tip in tipler else 0
            o_tip, ok_tip = QInputDialog.getItem(self, "Ödeme Tipi", "Ödeme yöntemi:", tipler, tip_idx, False)
            update_data["odeme_tipi"] = o_tip if ok_tip else mevcut_tip
        return update_data

    def change_record_delivery_status(self, kid, record):
        mevcut_teslim = record.get("teslim_durumu", "Müşteriye Teslim Edildi" if "Teslim" in record.get("d", "") else "Teslim Bekliyor")
        opts = ["Teslim Bekliyor", "Müşteriye Teslim Edildi"]
        new_delivery, ok_delivery = QInputDialog.getItem(self, "Teslim Durumu", "Müşteriye teslim durumu:", opts, opts.index(mevcut_teslim) if mevcut_teslim in opts else 0, False)
        if ok_delivery:
            update_data = {"teslim_durumu": new_delivery}
            update_data["teslim_tarihi"] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M") if new_delivery == "Müşteriye Teslim Edildi" else ""
            current_status = str(record.get("d", "") or "")
            is_iade_flow = "İade" in current_status or "Iade" in current_status
            if new_delivery == "Müşteriye Teslim Edildi":
                update_data["d"] = "İade Edildi" if is_iade_flow else "Teslim Edildi"
            else:
                update_data["d"] = "İade Bekliyor" if is_iade_flow else "Teslim Bekliyor"
            if new_delivery == "Müşteriye Teslim Edildi":
                payment_update = self.ask_delivery_payment_update(record)
                if payment_update is None:
                    return
                update_data.update(payment_update)
            if not self.update_record_fields(kid, update_data, "Teslim durumu güncelleme"):
                return
            self.log_record_action(kid, f"Teslim durumu güncellendi: {new_delivery}")
            self.publish_public_status(kid)
            self.refresh_all_tables()

    def edit_record_delivery_date(self, kid, record):
        if not isinstance(record, dict):
            return

        current_text = str(record.get("teslim_tarihi", "") or "").strip()
        fallback_text = str(self.delivery_date_for_record(record) or "").strip()
        parsed_current = self.parse_date_value(current_text or fallback_text)
        if parsed_current == datetime.datetime.min:
            parsed_current = datetime.datetime.now()

        dlg = QDialog(self)
        dlg.setWindowTitle(self.get_trans("Edit Delivery Date", "Teslim Tarihini Düzenle"))
        dlg.setModal(True)
        dlg.setMinimumWidth(390)
        lay = QVBoxLayout(dlg)

        info = QLabel(self.get_trans(
            "Only the delivery date will change. The original service registration date stays the same.",
            "Sadece teslim tarihi değişir. Cihazın servise giriş/kayıt tarihi aynı kalır."
        ))
        info.setWordWrap(True)
        lay.addWidget(info)

        row = QHBoxLayout()
        lbl_date = QLabel(self.get_trans("Date:", "Tarih:"))
        date_edit = QDateEdit()
        self.setup_calendar_date_edit(date_edit)
        date_edit.setDate(QDate(parsed_current.year, parsed_current.month, parsed_current.day))
        date_edit.setMaximumDate(QDate.currentDate())

        lbl_time = QLabel(self.get_trans("Time:", "Saat:"))
        time_edit = QLineEdit(parsed_current.strftime("%H:%M"))
        time_edit.setInputMask("00:00")
        time_edit.setFixedWidth(78)
        row.addWidget(lbl_date)
        row.addWidget(date_edit, 1)
        row.addWidget(lbl_time)
        row.addWidget(time_edit)
        lay.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.get_trans("Save", "Kaydet"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.get_trans("Cancel", "Vazgeç"))
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        time_text = time_edit.text().replace(" ", "").strip()
        if not re.fullmatch(r"\d{2}:\d{2}", time_text):
            QMessageBox.warning(self, self.get_trans("Delivery Date", "Teslim Tarihi"), self.get_trans(
                "Please enter the time as HH:mm.",
                "Saati SS:dd formatında yazın. Örnek: 14:30"
            ))
            return
        hour, minute = [int(part) for part in time_text.split(":")]
        if hour > 23 or minute > 59:
            QMessageBox.warning(self, self.get_trans("Delivery Date", "Teslim Tarihi"), self.get_trans(
                "The selected time is not valid.",
                "Seçilen saat geçerli değil."
            ))
            return

        q_date = date_edit.date()
        selected_dt = datetime.datetime(q_date.year(), q_date.month(), q_date.day(), hour, minute)
        if selected_dt > datetime.datetime.now() + datetime.timedelta(minutes=2):
            QMessageBox.warning(self, self.get_trans("Delivery Date", "Teslim Tarihi"), self.get_trans(
                "Delivery date cannot be in the future.",
                "Teslim tarihi bugünden ileri olamaz."
            ))
            return

        created_dt = self.parse_date_value(record.get("z", ""))
        if created_dt != datetime.datetime.min and selected_dt.date() < created_dt.date():
            if QMessageBox.question(
                self,
                self.get_trans("Delivery Date", "Teslim Tarihi"),
                self.get_trans(
                    "The selected delivery date is before the service registration date. Continue?",
                    "Seçilen teslim tarihi cihazın kayıt tarihinden önce. Devam edilsin mi?"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

        old_status_delivered, old_is_iade = self.is_delivered_record(record)
        current_status = str(record.get("d", "") or "")
        status_plain = self.normalize_upper(current_status).replace("İ", "I")
        is_iade_flow = old_is_iade or "IADE" in status_plain
        formatted = selected_dt.strftime("%d.%m.%Y %H:%M")
        update_data = {
            "d": "İade Edildi" if is_iade_flow else "Teslim Edildi",
            "teslim_durumu": "Müşteriye Teslim Edildi",
            "teslim_tarihi": formatted
        }

        if not old_status_delivered:
            payment_update = self.ask_delivery_payment_update(record)
            if payment_update is None:
                return
            update_data.update(payment_update)

        if not self.update_record_fields(kid, update_data, "Teslim tarihi düzenleme"):
            return

        old_text = current_text or fallback_text or "-"
        self.log_record_action(kid, f"Teslim tarihi düzenlendi: {old_text} -> {formatted}")
        self.publish_public_status(kid)
        self.refresh_all_tables()

    def change_done_service_status(self, kid, record):
        status_options = ["İşlemleri Tamamlandı", "İade Edildi"]
        current_status = record.get("d", "İşlemleri Tamamlandı")
        idx = status_options.index(current_status) if current_status in status_options else 0
        new_s, ok = QInputDialog.getItem(self, "Servis Sonucu", "Servis sonucu:", status_options, idx, False)
        if ok:
            update_data = {"d": new_s, "teslim_durumu": "Teslim Bekliyor", "teslim_tarihi": ""}
            if not self.update_record_fields(kid, update_data, "Servis sonucu güncelleme"):
                return
            self.log_record_action(kid, f"Servis sonucu güncellendi: {new_s}")
            self.publish_public_status(kid)
            self.refresh_all_tables()

    def change_record_status(self, kid, record, table):
        status_options = ["İşlem Bekliyor", "Tamirde", "Parça Bekliyor", "İşlemleri Tamamlandı", "Müşteriye Teslim Edildi"] if table in [self.table_act, self.table_ready] else ["Teslim Bekliyor", "İade Bekliyor", "Müşteriye Teslim Edildi"]
        current_status = record.get("d", status_options[0])
        idx = status_options.index(current_status) if current_status in status_options else 0
        new_s, ok = QInputDialog.getItem(self, "Güncelle", "Durum:", status_options, idx, False)
        if not ok:
            return
        status_update = {"d": new_s}
        if new_s == "Teslim Bekliyor":
            status_update["d"] = "Teslim Bekliyor"
            status_update["teslim_durumu"] = "Teslim Bekliyor"
            status_update["teslim_tarihi"] = ""
        elif new_s == "İade Bekliyor":
            status_update["d"] = "İade Bekliyor"
            status_update["teslim_durumu"] = "Teslim Bekliyor"
            status_update["teslim_tarihi"] = ""
        elif new_s in ["İşlemleri Tamamlandı", "İade Edildi"]:
            status_update["teslim_durumu"] = "Teslim Bekliyor"
            status_update["teslim_tarihi"] = ""
        elif new_s == "Müşteriye Teslim Edildi":
            status_plain = self.normalize_upper(str(record.get("d", "") or "")).replace("İ", "I")
            is_iade_flow = "IADE" in status_plain
            payment_update = self.ask_delivery_payment_update(record)
            if payment_update is None:
                return
            status_update["d"] = "İade Edildi" if is_iade_flow else "Teslim Edildi"
            status_update["teslim_durumu"] = "Müşteriye Teslim Edildi"
            status_update["teslim_tarihi"] = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
            status_update.update(payment_update)
        if not self.update_record_fields(kid, status_update, "Durum güncelleme"):
            return
        self.log_record_action(kid, f"Durum güncellendi: {new_s}")
        self.publish_public_status(kid)
        self.refresh_all_tables()

    def edit_record_price(self, kid, record):
        if not self.require_staff_permission("finance", "Fiyat düzenleme"):
            return
        current_net = safe_float(record.get("masraf", "0"))
        current_approx = safe_float(record.get("yaklasik_ucret", "0"))
        price_type, ok_type = QInputDialog.getItem(
            self,
            "Fiyat Bilgisi",
            "Fiyat türü:",
            ["Net Ücret", "Yaklaşık Ücret"],
            0 if current_net > 0 else 1,
            False
        )
        if not ok_type:
            return
        default_value = current_net if price_type == "Net Ücret" else current_approx
        dlg = CustomEditDialog("Fiyat Bilgisi", f"{price_type} (₺):", "" if default_value == 0 else f"{default_value:.2f}", self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        value = safe_float(dlg.get_text())
        if price_type == "Net Ücret":
            update_data = {"masraf": str(value)}
            if value > 0:
                update_data["yaklasik_ucret"] = ""
        else:
            update_data = {"yaklasik_ucret": str(value) if value > 0 else ""}
        if not self.update_record_fields(kid, update_data, "Fiyat güncelleme"):
            return
        self.log_record_action(kid, f"{price_type} güncellendi: {format_money(value, '₺')}")
        self.publish_public_status(kid)
        self.refresh_all_tables()

    def use_stock_part_for_record(self, kid):
        if not self.require_staff_permission("edit_stock", "Stoktan parça kullanma"):
            return
        stok_data = safe_dict_parse(getattr(self, "stok_data", {}))
        if not isinstance(stok_data, dict) or not stok_data:
            stok_data = safe_dict_parse(db.child("users").child(self.user_id).child("stok").get(self.token).val() or {})
        if not isinstance(stok_data, dict) or not stok_data:
            QMessageBox.information(self, "Stok", "Stokta kayıtlı parça bulunamadı.")
            return

        choices = []
        choice_map = {}
        for sid, item in stok_data.items():
            if not isinstance(item, dict):
                continue
            qty = safe_float(item.get("adet", "0"))
            if qty <= 0:
                continue
            name = str(item.get("ad", "")).strip()
            if not name:
                continue
            code = self.stock_code_for_item(sid, item)
            label = f"{code} | {name} | Stok: {self.format_quantity(qty)} | Satış: {format_money(safe_float(item.get('satis', '0')), item.get('birim', '₺'))}"
            choices.append(label)
            choice_map[label] = (sid, item, qty)

        if not choices:
            QMessageBox.warning(self, "Stok", "Stokta adedi olan parça bulunamadı.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Stoktan Parça Kullan")
        dlg.setMinimumSize(560, 420)
        lay = QVBoxLayout(dlg)
        search = QLineEdit()
        search.setPlaceholderText("Parça ara...")
        part_list = QListWidget()
        qty_input = QLineEdit()
        qty_input.setPlaceholderText("Kullanılacak adet")
        qty_input.setText("1")
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(search)
        lay.addWidget(part_list, 1)
        lay.addWidget(qty_input)
        lay.addWidget(buttons)

        def fill_parts(term=""):
            part_list.clear()
            term = self.normalize_upper(term)
            for label in choices:
                if not term or term in self.normalize_upper(label):
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, label)
                    part_list.addItem(item)
            if part_list.count() > 0:
                part_list.setCurrentRow(0)

        search.textChanged.connect(fill_parts)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        fill_parts()
        if dlg.exec() != QDialog.DialogCode.Accepted or not part_list.currentItem():
            return

        selected = part_list.currentItem().data(Qt.ItemDataRole.UserRole)
        if selected not in choice_map:
            return
        sid, item, current_qty = choice_map[selected]
        used_qty = safe_float(qty_input.text())
        if used_qty <= 0:
            QMessageBox.warning(self, "Miktar", "Kullanılacak adet 0'dan büyük olmalı.")
            return
        if used_qty > current_qty:
            QMessageBox.warning(self, "Stok Yetersiz", "Kullanılacak adet mevcut stoktan fazla olamaz.")
            return

        new_qty = max(0.0, current_qty - used_qty)
        part_name = str(item.get("ad", ""))
        unit = item.get("birim", "₺")
        sale_price = safe_float(item.get("satis", "0"))
        buy_price = safe_float(item.get("alis", "0"))
        now = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

        db.child("users").child(self.user_id).child("stok").child(sid).update({"adet": new_qty}, self.token)
        db.child("users").child(self.user_id).child("kayitlar").child(kid).child("kullanilan_parcalar").push({
            "stok_id": sid,
            "parca": part_name,
            "adet": used_qty,
            "alis": buy_price,
            "satis": sale_price,
            "birim": unit,
            "zaman": now,
            "source": "stok"
        }, self.token)
        self.touch_record_sync_meta(kid, "upsert")
        self.log_record_action(kid, f"Stoktan parça kullanıldı: {part_name} x {self.format_quantity(used_qty)}")
        self.refresh_all_tables()
        QMessageBox.information(self, "Stok", f"{part_name} stoktan düşüldü. Kalan: {self.format_quantity(new_qty)}")

    def handle_double_click(self, row, col, table):
        if table in [self.table_kasa, self.table_trash, self.table_musteri_gecmis, self.table_dokum]: return
        kid = table.item(row, 0).text()
        h = table.horizontalHeaderItem(col).text()
        
        if table == self.table_stok:
            if not self.require_staff_permission("edit_stock", "Stok düzenleme"):
                return
            stok_data = safe_dict_parse(getattr(self, "stok_data", {}))
            v = stok_data.get(kid) if isinstance(stok_data, dict) else None
            if not isinstance(v, dict):
                v = db.child("users").child(self.user_id).child("stok").child(kid).get(self.token).val()
            if not isinstance(v, dict): return
            if "Stok Kodu" in h or "Stock Code" in h:
                dlg = CustomEditDialog("Düzenle", "Stok Kodu:", self.stock_code_for_item(kid, v), self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    code = self.normalize_upper(dlg.get_text()).strip()
                    if code:
                        db.child("users").child(self.user_id).child("stok").child(kid).update({"stok_kodu": code}, self.token)
                        self.audit_log("Stok Güncelleme", f"Stok kodu güncellendi: {self.stock_code_for_item(kid, v)} -> {code}", "stok", kid, before={"stok_kodu": self.stock_code_for_item(kid, v)}, after={"stok_kodu": code})
                        self.refresh_all_tables()
            elif "Barkod" in h or "Barcode" in h:
                dlg = CustomEditDialog("Düzenle", "Barkod:", str(v.get("barkod", "") or v.get("barcode", "")), self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    new_value = self.normalize_upper(dlg.get_text()).strip()
                    db.child("users").child(self.user_id).child("stok").child(kid).update({"barkod": new_value}, self.token)
                    self.audit_log("Stok Güncelleme", f"{v.get('ad', '')} barkod güncellendi", "stok", kid, before={"barkod": v.get("barkod", "") or v.get("barcode", "")}, after={"barkod": new_value})
                    self.refresh_all_tables()
            elif "Alış" in h:
                dlg = CustomEditDialog("Düzenle", "Alış Fiyatı:", str(v.get("alis", "")), self)
                if dlg.exec() == QDialog.DialogCode.Accepted: 
                    new_value = safe_float(dlg.get_text())
                    db.child("users").child(self.user_id).child("stok").child(kid).update({"alis": new_value}, self.token)
                    self.audit_log("Stok Güncelleme", f"{v.get('ad', '')} alış fiyatı güncellendi", "stok", kid, before={"alis": v.get("alis", "")}, after={"alis": new_value})
                    self.refresh_all_tables()
            elif "Satış" in h:
                dlg = CustomEditDialog("Düzenle", "Satış Fiyatı:", str(v.get("satis", "")), self)
                if dlg.exec() == QDialog.DialogCode.Accepted: 
                    new_value = safe_float(dlg.get_text())
                    db.child("users").child(self.user_id).child("stok").child(kid).update({"satis": new_value}, self.token)
                    self.audit_log("Stok Güncelleme", f"{v.get('ad', '')} satış fiyatı güncellendi", "stok", kid, before={"satis": v.get("satis", "")}, after={"satis": new_value})
                    self.refresh_all_tables()
            elif "Adet" in h:
                dlg = CustomEditDialog("Düzenle", "Stok Adedi:", self.format_quantity(v.get("adet", "")), self)
                if dlg.exec() == QDialog.DialogCode.Accepted: 
                    new_value = safe_float(dlg.get_text())
                    db.child("users").child(self.user_id).child("stok").child(kid).update({"adet": new_value}, self.token)
                    self.audit_log("Stok Güncelleme", f"{v.get('ad', '')} adedi güncellendi", "stok", kid, before={"adet": v.get("adet", "")}, after={"adet": new_value})
                    self.refresh_all_tables()
            elif "Parça" in h:
                dlg = CustomEditDialog("Düzenle", "Parça Adı:", str(v.get("ad", "")), self)
                if dlg.exec() == QDialog.DialogCode.Accepted: 
                    new_value = self.normalize_upper(dlg.get_text()).strip()
                    db.child("users").child(self.user_id).child("stok").child(kid).update({"ad": new_value}, self.token)
                    self.audit_log("Stok Güncelleme", f"Parça adı güncellendi: {v.get('ad', '')} -> {new_value}", "stok", kid, before={"ad": v.get("ad", "")}, after={"ad": new_value})
                    self.refresh_all_tables()
            return
            
        v = self.get_local_record(kid)
        if not isinstance(v, dict): return
        if not self.staff_can(self.record_edit_permission_for_table(table, v)):
            InfoDialog(v, kid, self, self).exec()
            return

        header_key = self.normalize_search_text(h)
        if ("teslim" in header_key and ("tarih" in header_key or "date" in header_key)) or "delivery date" in header_key:
            self.edit_record_delivery_date(kid, v)
            return
        if "odeme" in header_key or "payment" in header_key:
            if not self.require_staff_permission("finance", "Ödeme düzenleme"):
                return
            self.change_record_payment(kid, v)
            return
        if "sonuc" in header_key or "result" in header_key:
            if table in [self.table_done, getattr(self, "table_delivered", None)]:
                self.change_done_service_status(kid, v)
            return
        if header_key in {"tarih", "zaman", "date", "time"} or ("tarih" in header_key or "zaman" in header_key or "time" in header_key):
            return

        if "Müşteri" in h or "Customer" in h:
            if self.is_bayi_record(v):
                QMessageBox.information(self, "Bayi Düzenleme", "Bayi adı işlem, bekleyen ve teslim/iade listelerinden değiştirilemez. Bayi bilgisi yalnızca Bayiler sekmesinden düzenlenebilir.")
                return
            old_name = v.get("m", "")
            dlg = CustomEditDialog("Müşteri Düzenle", "Müşteri Adı:", old_name, self)
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_name = self.normalize_upper(dlg.get_text()).strip()
                if new_name and new_name != old_name:
                    data = safe_dict_parse(self.kayitlar_data)
                    if not isinstance(data, dict):
                        data = {}
                    phone = "".join(filter(str.isdigit, str(v.get("t", ""))))
                    updates = {}
                    for rec_id, rec in data.items():
                        if not isinstance(rec, dict):
                            continue
                        if self.is_bayi_record(rec):
                            continue
                        same_phone = phone and "".join(filter(str.isdigit, str(rec.get("t", "")))) == phone
                        if same_phone:
                            updates[rec_id] = {"m": new_name}
                    if not updates:
                        updates[kid] = {"m": new_name}
                    scope = f"Telefon eşleşmesi: {phone[-10:]}" if phone else "Telefon yok; sadece seçili kayıt"
                    if not self.confirm_bulk_name_update("Müşteri Adı Değişikliği", old_name, new_name, updates, scope):
                        return
                    for rec_id, update_data in updates.items():
                        if not self.update_record_fields(rec_id, update_data, "Müşteri adı güncelleme"):
                            return
                        self.log_record_action(rec_id, f"Müşteri adı güncellendi: {old_name} -> {new_name}")
                        self.publish_public_status(rec_id)
                    self.refresh_all_tables()
        elif "İşlem" in h or "Action" in h:
            dlg = self.create_operation_dialog("Düzenle", v.get("yapilan_islem",""))
            if dlg.exec() == QDialog.DialogCode.Accepted: 
                new_value = self.remember_operation_text(dlg.get_text())
                if not self.update_record_fields(kid, {"yapilan_islem": new_value}, "İşlem bilgisi güncelleme"):
                    return
                self.log_record_action(kid, f"İşlem bilgisi güncellendi: {new_value}")
                self.publish_public_status(kid)
                self.refresh_all_tables()
        elif "Ücret" in h or "Price" in h:
            if not self.require_staff_permission("finance", "Fiyat düzenleme"):
                return
            self.edit_record_price(kid, v)
        elif "Fiyat" in h:
            if not self.require_staff_permission("finance", "Fiyat düzenleme"):
                return
            self.edit_record_price(kid, v)
        elif "Teslim" in h or "Delivery" in h:
            self.change_record_delivery_status(kid, v)
        elif "Durum" in h or "Status" in h:
            if table in [self.table_done, getattr(self, "table_delivered", None)]:
                self.change_done_service_status(kid, v)
            else:
                self.change_record_status(kid, v, table)
        elif "Arıza" in h or "Fault" in h:
            mevcut = "\n".join(self.get_faults(v))
            dlg_faults = CustomEditDialog("Arıza Düzenle", "Her arızayı ayrı satıra yazın:", mevcut, self, is_multiline=True)
            if dlg_faults.exec() == QDialog.DialogCode.Accepted:
                text = dlg_faults.get_text()
                faults = [self.normalize_upper(line).strip() for line in text.splitlines() if line.strip()]
                if not self.update_record_fields(kid, {"a": faults[0] if faults else "", "arizalar": faults}, "Arıza bilgisi güncelleme"):
                    return
                self.log_record_action(kid, f"Arıza bilgisi güncellendi: {', '.join(faults) if faults else '-'}")
                self.publish_public_status(kid)
                self.refresh_all_tables()
        elif "Cihaz" in h or "Device" in h:
            dlg = CustomEditDialog("Düzenle", "Cihaz Marka/Model:", v.get("ci",""), self)
            if dlg.exec() == QDialog.DialogCode.Accepted: 
                new_value = self.normalize_upper(dlg.get_text()).strip()
                if not self.update_record_fields(kid, {"ci": new_value}, "Cihaz bilgisi güncelleme"):
                    return
                self.log_record_action(kid, f"Cihaz bilgisi güncellendi: {new_value}")
                self.publish_public_status(kid)
                self.refresh_all_tables()
        else:
            return

    def get_receipt_layout(self):
        fmt = str(self.user_setting_value("print_format", "80mm (Standart Fiş)"))
        simple_style = str(self.user_setting_value("receipt_simple_style", "false")) == "true"
        if "A5" in fmt or "Yarım" in fmt or "Yarim" in fmt:
            return {
                "page": QSizeF(148, 210),
                "width_mm": 148,
                "min_height_mm": 210,
                "max_height_mm": 210,
                "dpi": 203,
                "margins": QMarginsF(0, 0, 0, 0),
                "content_mm": 138,
                "label_mm": 34,
                "font_size": "9pt",
                "small_font_size": "7pt",
                "title_size": "14pt",
                "qr": 210,
                "compact": False,
                "wide": True,
                "simple": simple_style,
                "fixed_page": True
            }
        if "56mm" in fmt or "58mm" in fmt:
            return {
                "page": QSizeF(56, 125),
                "width_mm": 56,
                "min_height_mm": 125,
                "max_height_mm": 220,
                "dpi": 203,
                "margins": QMarginsF(0, 0, 0, 0),
                "content_mm": 53,
                "label_mm": 14,
                "font_size": "6pt",
                "small_font_size": "5.3pt",
                "title_size": "9.2pt",
                "qr": 176,
                "compact": True,
                "simple": simple_style
            }
        return {
            "page": QSizeF(80, 110),
            "width_mm": 80,
            "min_height_mm": 110,
            "max_height_mm": 230,
            "dpi": 203,
            "margins": QMarginsF(0, 0, 0, 0),
            "content_mm": 72,
            "label_mm": 25,
            "font_size": "8pt",
            "small_font_size": "6.5pt",
            "title_size": "13pt",
            "qr": 224,
            "compact": False,
            "simple": simple_style
        }

    def configure_receipt_printer(self, printer, height_mm=None):
        layout = self.get_receipt_layout()
        page_height = layout["page"].height() if layout.get("fixed_page", False) else (height_mm or layout["page"].height())
        page = QSizeF(float(layout.get("width_mm", 80)), float(page_height))
        printer.setFullPage(True)
        printer.setPageSize(QPageSize(page, QPageSize.Unit.Millimeter, "Receipt"))
        printer.setPageMargins(layout["margins"], QPageLayout.Unit.Millimeter)
        return layout

    def configure_label_printer(self, printer):
        page = QSizeF(56, 32)
        printer.setFullPage(True)
        printer.setPageSize(QPageSize(page, QPageSize.Unit.Millimeter, "DeviceLabel"))
        printer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
        return {"width_mm": 56, "height_mm": 32, "dpi": 203}

    def label_font(self, size, bold=False):
        try:
            from PIL import ImageFont
            fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
            font_names = (
                ["segoeuib.ttf", "seguisb.ttf", "arialbd.ttf", "tahomabd.ttf", "calibrib.ttf"]
                if bold else
                ["segoeui.ttf", "arial.ttf", "tahoma.ttf", "calibri.ttf"]
            )
            for font_name in font_names:
                font_path = os.path.join(fonts_dir, font_name)
                if os.path.exists(font_path):
                    return ImageFont.truetype(font_path, size=size, encoding="unic")
        except Exception:
            try:
                from PIL import ImageFont
                return ImageFont.load_default()
            except Exception:
                return None

    def fit_label_text(self, draw, text, font, max_width):
        text = str(text or "-")
        if draw.textlength(text, font=font) <= max_width:
            return text
        ellipsis = "..."
        while text and draw.textlength(text + ellipsis, font=font) > max_width:
            text = text[:-1]
        return (text + ellipsis) if text else ellipsis

    def device_label_image_base64(self, data, layout):
        from PIL import Image, ImageDraw
        dpi = layout.get("dpi", 203)
        width = int(layout.get("width_mm", 56) / 25.4 * dpi)
        height = int(layout.get("height_mm", 32) / 25.4 * dpi)
        img = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(img)
        margin = 10
        code = str(data.get("c_no", "") or data.get("record_code", "") or "").strip()
        phone = "".join(filter(str.isdigit, str(data.get("t", "") or "")))
        phone_tail = phone[-4:] if phone else "-"
        shop = self.receipt_display_company_name()
        customer = str(data.get("m", "") or "-")
        device = str(data.get("ci", "") or "-")
        status = str(data.get("d", "") or "-")
        date_text = str(data.get("z", "") or datetime.datetime.now().strftime("%d.%m.%Y %H:%M"))

        title_font = self.label_font(18, True)
        code_font = self.label_font(20, True)
        label_font = self.label_font(14, True)
        value_font = self.label_font(14, True)
        small_font = self.label_font(12, False)

        shop_text = self.fit_label_text(draw, shop, title_font, width - margin * 2)
        draw.text(((width - draw.textlength(shop_text, font=title_font)) / 2, 4), shop_text, fill="black", font=title_font)
        draw.line((margin, 28, width - margin, 28), fill="black", width=1)

        barcode = self.code39_barcode_image(code, height=72, narrow=2, wide=5)
        if barcode is not None:
            max_barcode_w = width - margin * 2
            if barcode.width > max_barcode_w:
                ratio = max_barcode_w / barcode.width
                barcode = barcode.resize((max_barcode_w, max(48, int(barcode.height * ratio))))
            img.paste(barcode, ((width - barcode.width) // 2, 34))
            barcode_bottom = 34 + barcode.height
        else:
            barcode_bottom = 36

        code_text = self.fit_label_text(draw, code or "-", code_font, width - margin * 2)
        draw.text(((width - draw.textlength(code_text, font=code_font)) / 2, barcode_bottom + 1), code_text, fill="black", font=code_font)

        y = barcode_bottom + 27
        left_w = 72
        rows = [
            ("Müşteri", customer),
            ("Cihaz", device),
            ("Tel", f"***{phone_tail}"),
            ("Durum", status),
        ]
        for label, value in rows:
            draw.text((margin, y), label, fill="black", font=label_font)
            value_text = self.fit_label_text(draw, value, value_font, width - margin * 2 - left_w)
            draw.text((margin + left_w, y), value_text, fill="black", font=value_font)
            y += 19

        date_text = self.fit_label_text(draw, date_text, small_font, width - margin * 2)
        draw.text((margin, height - 19), date_text, fill="black", font=small_font)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def device_label_html(self, data, layout):
        label_b64 = self.device_label_image_base64(data, layout)
        return f"""
        <html><body style="margin:0; padding:0;">
            <img src="data:image/png;base64,{label_b64}" style="width:{layout['width_mm']}mm; height:{layout['height_mm']}mm; display:block;" />
        </body></html>
        """

    def clean_receipt_text(self, value, fallback="-"):
        text = str(value if value is not None else "").replace("<br>", " ").replace("\r", " ").replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text or fallback

    def fit_receipt_line(self, draw, text, font, max_width):
        text = self.clean_receipt_text(text)
        if draw.textlength(text, font=font) <= max_width:
            return text
        ellipsis = "..."
        while text and draw.textlength(text + ellipsis, font=font) > max_width:
            text = text[:-1]
        return (text + ellipsis) if text else ellipsis

    def wrap_receipt_text(self, draw, text, font, max_width, max_lines=None):
        text = self.clean_receipt_text(text)
        words = text.split(" ")
        lines = []
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip() if line else word
            if draw.textlength(candidate, font=font) <= max_width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            while word and draw.textlength(word, font=font) > max_width:
                part = ""
                for ch in word:
                    if draw.textlength(part + ch, font=font) <= max_width:
                        part += ch
                    else:
                        break
                if not part:
                    part = word[:1]
                lines.append(part)
                word = word[len(part):]
            line = word
        if line:
            lines.append(line)
        if not lines:
            lines = ["-"]
        if max_lines and len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = self.fit_receipt_line(draw, lines[-1].rstrip(".") + "...", font, max_width)
        return lines

    def draw_receipt_center(self, draw, y, lines, font, width, fill="#111827", line_gap=2):
        if isinstance(lines, str):
            lines = [lines]
        for line in lines:
            text_w = draw.textlength(line, font=font)
            draw.text(((width - text_w) / 2, y), line, fill=fill, font=font)
            bbox = draw.textbbox((0, 0), line or "Ay", font=font)
            y += (bbox[3] - bbox[1]) + line_gap
        return y

    def simple_receipt_image_base64(self, data, layout):
        from PIL import Image, ImageDraw

        dpi = int(layout.get("dpi", 203))
        width_mm = float(layout.get("width_mm", 80))
        min_height_mm = float(layout.get("min_height_mm", 145))
        max_height_mm = float(layout.get("max_height_mm", 230))
        compact = bool(layout.get("compact", False))
        wide = bool(layout.get("wide", False))
        width = int(width_mm / 25.4 * dpi)
        min_height = int(min_height_mm / 25.4 * dpi)
        max_height = int(max_height_mm / 25.4 * dpi)
        img = Image.new("RGB", (width, max_height), "white")
        draw = ImageDraw.Draw(img)

        if wide:
            content_w = min(width - 120, int(94 / 25.4 * dpi))
            title_font = self.label_font(42, True)
            meta_font = self.label_font(21, True)
            section_font = self.label_font(25, True)
            value_font = self.label_font(24, True)
            small_font = self.label_font(19, True)
            row_gap = 11
            y = 34
        elif compact:
            content_w = width - int(8 / 25.4 * dpi)
            title_font = self.label_font(24, True)
            meta_font = self.label_font(15, True)
            section_font = self.label_font(17, True)
            value_font = self.label_font(18, True)
            small_font = self.label_font(14, True)
            row_gap = 7
            y = 16
        else:
            content_w = width - int(12 / 25.4 * dpi)
            title_font = self.label_font(34, True)
            meta_font = self.label_font(18, True)
            section_font = self.label_font(21, True)
            value_font = self.label_font(22, True)
            small_font = self.label_font(17, True)
            row_gap = 9
            y = 20

        margin = max(12, int((width - content_w) / 2))
        content_w = width - (margin * 2)
        text_color = "#000000"
        muted = "#111111"

        def font_height(font, sample="Ay"):
            bbox = draw.textbbox((0, 0), sample, font=font)
            return max(1, bbox[3] - bbox[1])

        def center_text(y_pos, lines, font, fill=text_color, line_gap=2):
            if isinstance(lines, str):
                lines = [lines]
            for line in lines:
                line = self.clean_receipt_text(line)
                text_w = draw.textlength(line, font=font)
                draw.text((margin + (content_w - text_w) / 2, y_pos), line, fill=fill, font=font)
                y_pos += font_height(font, line or "Ay") + line_gap
            return y_pos

        def separator(y_pos, dashed=True):
            if dashed:
                x = margin
                while x < width - margin:
                    draw.line((x, y_pos, min(x + 16, width - margin), y_pos), fill="#000000", width=2)
                    x += 26
            else:
                draw.line((margin, y_pos, width - margin, y_pos), fill="#000000", width=2)

        def section(y_pos, title, value, max_lines=2, value_bold=True):
            y_pos = center_text(y_pos, title, section_font, text_color, 2)
            value_lines = self.wrap_receipt_text(draw, value, value_font if value_bold else meta_font, content_w, max_lines)
            y_pos = center_text(y_pos + 1, value_lines, value_font if value_bold else meta_font, text_color, 2)
            y_pos += row_gap
            separator(y_pos, dashed=False)
            return y_pos + row_gap

        shop_title = self.clean_receipt_text(self.receipt_display_company_name(), "MetaFold Teknik Servis")
        shop_address = self.clean_receipt_text(self.receipt_shop_address, "")
        y = center_text(y, self.wrap_receipt_text(draw, shop_title, title_font, content_w, 2), title_font, text_color, 2)
        if shop_address:
            y = center_text(y + 2, self.wrap_receipt_text(draw, shop_address, meta_font, content_w, 2), meta_font, muted, 2)
        y += 8
        separator(y)
        y += 8
        y = center_text(y, datetime.datetime.now().strftime("%d.%m.%Y - %H:%M"), meta_font, text_color, 2)
        y = center_text(y, "SERVİS TESLİM FİŞİ", section_font, text_color, 2) + 4
        separator(y)
        y += 8

        record_no = self.clean_receipt_text(data.get("c_no", ""), "-")
        y = section(y, "Cihaz No", record_no, 2, True)
        y = section(y, "Müşteri Bilgileri", data.get("m", "-"), 2, True)

        phone_text = self.clean_receipt_text(data.get("t", ""), "Belirtilmemiş")
        y = section(y, "Müşteri Telefonu", phone_text, 1, True)
        y = section(y, "Cihaz Bilgileri", data.get("ci", "-"), 2, True)

        faults = " / ".join(self.get_faults(data)) or self.clean_receipt_text(data.get("a", ""), "-")
        y = section(y, "Beyan Edilen Arıza", faults, 3, True)

        password_text = self.clean_receipt_text(data.get("sifre", ""), "Belirtilmemiş")
        note_text = self.clean_receipt_text(data.get("not", ""), "Yok")
        y = section(y, "Şifre", password_text, 2, True)
        y = section(y, "Not", note_text, 2, False)

        ucret_tl = safe_float(data.get("masraf", "0"))
        yaklasik_tl = safe_float(data.get("yaklasik_ucret", "0"))
        fiyat_label = "Net Ücret" if ucret_tl > 0 else "Yaklaşık Ücret" if yaklasik_tl > 0 else "Ücret"
        fiyat_value = format_money(ucret_tl if ucret_tl > 0 else yaklasik_tl, "₺")
        price_h = font_height(value_font) + font_height(section_font) + 20
        draw.rectangle((margin, y, width - margin, y + price_h), fill="#ffffff", outline="#000000", width=2)
        py = y + 7
        py = center_text(py, fiyat_label, section_font, text_color, 0)
        center_text(py + 2, fiyat_value, value_font, text_color, 0)
        y += price_h + 10
        if ucret_tl <= 0 and yaklasik_tl > 0:
            y = center_text(y, "Arıza tespitine göre değişebilir.", small_font, text_color, 2) + 2

        b64_qr = self.receipt_status_qr_base64(data)
        qr_size = int(layout.get("qr", 104))
        if b64_qr and qr_size > 0:
            try:
                qr = Image.open(io.BytesIO(base64.b64decode(b64_qr))).convert("RGB")
                resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST", 0)
                qr = qr.resize((qr_size, qr_size), resampling)
                img.paste(qr, ((width - qr_size) // 2, y))
                y += qr_size + 4
                y = center_text(y, "Cihaz durumunu QR ile takip edin", small_font, text_color, 2) + 6
            except Exception:
                pass

        separator(y)
        y += 8
        y = center_text(y, "YASAL TEKNİK SERVİS UYARISI", section_font, text_color, 2)
        warning_text = "Teslim fişi ibraz edilmeden cihaz iade edilmez. Veri yedekleme müşteri sorumluluğundadır."
        y = center_text(y, self.wrap_receipt_text(draw, warning_text, small_font, content_w, 4), small_font, text_color, 2)
        y += 8
        separator(y)
        y += 8
        y = center_text(y, self.wrap_receipt_text(draw, shop_title, small_font, content_w, 2), small_font, text_color, 2)
        y = center_text(y, "MetaFold ERP Sistemleri", small_font, text_color, 2)

        final_height = max(min_height, min(max_height, y + margin))
        img = img.crop((0, 0, width, final_height))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8"), (final_height / dpi * 25.4)

    def receipt_image_base64(self, data, layout):
        from PIL import Image, ImageDraw

        if bool(layout.get("simple", False)):
            return self.simple_receipt_image_base64(data, layout)

        dpi = int(layout.get("dpi", 203))
        width_mm = float(layout.get("width_mm", 80))
        min_height_mm = float(layout.get("min_height_mm", 145))
        max_height_mm = float(layout.get("max_height_mm", 230))
        compact = bool(layout.get("compact", False))
        width = int(width_mm / 25.4 * dpi)
        min_height = int(min_height_mm / 25.4 * dpi)
        max_height = int(max_height_mm / 25.4 * dpi)
        img = Image.new("RGB", (width, max_height), "white")
        draw = ImageDraw.Draw(img)

        wide = bool(layout.get("wide", False))
        if wide:
            margin = 58
            title_font = self.label_font(42, True)
            meta_font = self.label_font(21, True)
            label_font = self.label_font(22, True)
            value_font = self.label_font(24, True)
            value_bold = self.label_font(25, True)
            small_font = self.label_font(19, True)
            label_w = 180
            row_gap = 14
        elif compact:
            margin = 18
            title_font = self.label_font(25, True)
            meta_font = self.label_font(15, True)
            label_font = self.label_font(17, True)
            value_font = self.label_font(18, True)
            value_bold = self.label_font(19, True)
            small_font = self.label_font(14, True)
            label_w = 88
            row_gap = 10
        else:
            margin = 28
            title_font = self.label_font(32, True)
            meta_font = self.label_font(18, True)
            label_font = self.label_font(19, True)
            value_font = self.label_font(20, True)
            value_bold = self.label_font(22, True)
            small_font = self.label_font(16, True)
            label_w = 140
            row_gap = 12

        accent = "#000000"
        muted = "#000000"
        line_color = "#000000"
        text_color = "#000000"
        y = 30 if wide else 14 if compact else 18
        usable_w = width - (margin * 2)

        def font_height(font, sample="Ay"):
            bbox = draw.textbbox((0, 0), sample, font=font)
            return max(1, bbox[3] - bbox[1])

        def separator(y_pos, dashed=False):
            if dashed:
                x = margin
                while x < width - margin:
                    draw.line((x, y_pos, min(x + 14, width - margin), y_pos), fill=line_color, width=2)
                    x += 24
            else:
                draw.line((margin, y_pos, width - margin, y_pos), fill=line_color, width=2)

        shop_title = self.clean_receipt_text(self.receipt_display_company_name(), "MetaFold Teknik Servis")
        shop_address = self.clean_receipt_text(self.receipt_shop_address, "")
        y = self.draw_receipt_center(draw, y, self.wrap_receipt_text(draw, shop_title, title_font, usable_w, 2), title_font, width, text_color, 2)
        if shop_address:
            y += 4
            y = self.draw_receipt_center(draw, y, self.wrap_receipt_text(draw, shop_address, meta_font, usable_w, 2), meta_font, width, muted, 2)
        y += 8
        separator(y, dashed=True)
        y += 8

        now_text = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
        service_text = "SERVİS TESLİM FİŞİ"
        draw.text((margin, y), now_text, fill=muted, font=meta_font)
        service_w = draw.textlength(service_text, font=meta_font)
        draw.text((width - margin - service_w, y), service_text, fill=accent, font=meta_font)
        y += font_height(meta_font) + 10

        record_no = self.clean_receipt_text(data.get("c_no", ""), "-")
        chip_h = font_height(value_bold) + (18 if wide else 14 if compact else 16)
        draw.rectangle((margin, y, width - margin, y + chip_h), fill="#ffffff", outline=accent, width=2)
        draw.text((margin + 12, y + (chip_h - font_height(label_font)) / 2), "Kayıt No", fill=accent, font=label_font)
        record_w = draw.textlength(record_no, font=value_bold)
        draw.text((width - margin - 12 - record_w, y + (chip_h - font_height(value_bold)) / 2), record_no, fill=text_color, font=value_bold)
        y += chip_h + 10

        value_x = margin + label_w + (18 if wide else 10 if compact else 14)
        value_w = width - margin - value_x

        def draw_row(y_pos, label, value, max_lines=2, bold_value=False):
            font = value_bold if bold_value else value_font
            value_lines = self.wrap_receipt_text(draw, value, font, value_w, max_lines)
            label_h = font_height(label_font)
            line_h = font_height(font) + 4
            row_h = max(label_h, len(value_lines) * line_h) + row_gap
            draw.text((margin, y_pos), self.clean_receipt_text(label), fill=muted, font=label_font)
            ty = y_pos
            for line in value_lines:
                draw.text((value_x, ty), line, fill=text_color, font=font)
                ty += line_h
            separator(y_pos + row_h - 2)
            return y_pos + row_h + 4

        faults = " / ".join(self.get_faults(data)) or self.clean_receipt_text(data.get("a", ""), "-")
        note_text = self.clean_receipt_text(data.get("not", ""), "Yok")
        password_text = self.clean_receipt_text(data.get("sifre", ""), "Belirtilmemiş")
        phone_text = self.clean_receipt_text(data.get("t", ""), "Belirtilmemiş")

        y = draw_row(y, "Müşteri", data.get("m", "-"), 2, True)
        y = draw_row(y, "Telefon", phone_text, 1)
        y = draw_row(y, "Cihaz", data.get("ci", "-"), 2, True)
        y = draw_row(y, "Arıza", faults, 3)
        y = draw_row(y, "Şifre", password_text, 2)
        y = draw_row(y, "Not", note_text, 2)

        ucret_tl = safe_float(data.get("masraf", "0"))
        yaklasik_tl = safe_float(data.get("yaklasik_ucret", "0"))
        fiyat_label = "Net Ücret" if ucret_tl > 0 else "Yaklaşık Ücret" if yaklasik_tl > 0 else "Ücret"
        fiyat_value = format_money(ucret_tl if ucret_tl > 0 else yaklasik_tl, "₺")
        price_h = font_height(value_bold) + (28 if wide else 20 if compact else 24)
        y += 2
        draw.rectangle((margin, y, width - margin, y + price_h), fill="#ffffff", outline="#000000", width=2)
        draw.text((margin + 12, y + (price_h - font_height(label_font)) / 2), fiyat_label, fill="#000000", font=label_font)
        price_w = draw.textlength(fiyat_value, font=value_bold)
        draw.text((width - margin - 12 - price_w, y + (price_h - font_height(value_bold)) / 2), fiyat_value, fill="#000000", font=value_bold)
        y += price_h + 10
        if ucret_tl <= 0 and yaklasik_tl > 0:
            y = self.draw_receipt_center(draw, y, "Arıza tespitine göre değişebilir.", small_font, width, muted, 2) + 2

        b64_qr = self.receipt_status_qr_base64(data)
        qr_size = int(layout.get("qr", 104))
        if b64_qr and qr_size > 0:
            try:
                qr = Image.open(io.BytesIO(base64.b64decode(b64_qr))).convert("RGB")
                resampling = getattr(getattr(Image, "Resampling", Image), "NEAREST", 0)
                qr = qr.resize((qr_size, qr_size), resampling)
                img.paste(qr, ((width - qr_size) // 2, y))
                y += qr_size + 3
                y = self.draw_receipt_center(draw, y, "Cihaz durumunu QR ile takip edin", small_font, width, muted, 2) + 8
            except Exception:
                pass

        separator(y, dashed=True)
        y += 8
        y = self.draw_receipt_center(draw, y, "YASAL TEKNİK SERVİS UYARISI", label_font, width, text_color, 2)
        warning_text = "Teslim fişi ibraz edilmeden cihaz iade edilmez. Veri yedekleme müşteri sorumluluğundadır."
        y = self.draw_receipt_center(draw, y, self.wrap_receipt_text(draw, warning_text, small_font, usable_w, 4), small_font, width, text_color, 2)
        y += 8
        separator(y, dashed=True)
        y += 8
        y = self.draw_receipt_center(draw, y, [shop_title, "MetaFold ERP Sistemleri"], small_font, width, text_color, 2)

        if wide:
            signature_block_h = 150
            if y + signature_block_h + margin < max_height:
                y = max(y + 30, max_height - margin - signature_block_h)
                separator(y, dashed=True)
                y += 28
                gap = 60
                sig_w = (width - (margin * 2) - gap) / 2
                left_x = margin
                right_x = margin + sig_w + gap
                line_y = y + 58

                def draw_signature_box(x_pos, title):
                    draw.line((x_pos, line_y, x_pos + sig_w, line_y), fill="#94a3b8", width=2)
                    title_w = draw.textlength(title, font=small_font)
                    draw.text((x_pos + (sig_w - title_w) / 2, line_y + 12), title, fill=muted, font=small_font)

                draw_signature_box(left_x, "Teslim Eden")
                draw_signature_box(right_x, "Teslim Alan")
                y = line_y + 44

        final_height = max(min_height, min(max_height, y + margin))
        img = img.crop((0, 0, width, final_height))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8"), (final_height / dpi * 25.4)

    def receipt_preview_html(self, receipt_b64, layout):
        preview_width = 520 if layout.get("wide", False) else 360 if not layout.get("compact", False) else 285
        return f"""
        <div style="background:#111827; padding:18px; text-align:center;">
            <img src="data:image/png;base64,{receipt_b64}" style="width:{preview_width}px; max-width:100%; height:auto; background:white; box-shadow:0 12px 30px rgba(0,0,0,.35);" />
        </div>
        """

    def print_device_label(self, data, mode="print"):
        if not isinstance(data, dict):
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(203)
        label_layout = self.configure_label_printer(printer)
        code = str(data.get("c_no", "") or "etiket").strip().replace("/", "-")

        if mode == "pdf":
            path, _ = QFileDialog.getSaveFileName(self, "Etiket PDF Kaydet", f"Etiket_{code}.pdf", "PDF Files (*.pdf)")
            if not path:
                return
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
        elif mode == "print":
            if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
                return

        label_b64 = self.device_label_image_base64(data, label_layout)
        label_pix = QPixmap()
        label_pix.loadFromData(base64.b64decode(label_b64), "PNG")
        if mode == "preview":
            ImagePreviewDialog(
                "Etiket Önizleme",
                label_pix,
                "56 x 32 mm barkodlu cihaz etiketi",
                self,
                initial_zoom=1.6,
            ).exec()
            return

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "Etiket", "Yazıcı/PDF başlatılamadı.")
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        painter.fillRect(page_rect, QColor("#ffffff"))
        painter.drawPixmap(page_rect, label_pix)
        painter.end()
        self.audit_log("Etiket Yazdırma", f"{data.get('c_no', '')} barkodlu etiket çıktısı alındı", "kayitlar", data.get("record_id", ""))
        if mode == "pdf":
            QMessageBox.information(self, "Etiket", "Etiket PDF çıktısı alındı.")

    def print_receipt(self, data, mode):
        if not isinstance(data, dict):
            return
        self.publish_public_status(str(data.get("record_id", "") or ""), data)
        receipt_layout = self.get_receipt_layout()
        try:
            receipt_b64, receipt_height_mm = self.receipt_image_base64(data, receipt_layout)
        except Exception as e:
            QMessageBox.warning(self, "Fiş", f"Fiş oluşturulamadı: {e}")
            return

        receipt_pix = QPixmap()
        if not receipt_pix.loadFromData(base64.b64decode(receipt_b64), "PNG"):
            QMessageBox.warning(self, "Fiş", "Fiş görseli önizlemeye hazırlanamadı.")
            return

        if mode == "preview":
            ImagePreviewDialog(
                "Fiş Önizleme",
                receipt_pix,
                "",
                self,
                initial_zoom=1.0,
            ).exec()
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(int(receipt_layout.get("dpi", 203)))

        if mode == "pdf":
            path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", f"Fis_{data.get('c_no')}.pdf", "PDF Files (*.pdf)")
            if not path:
                return
            if not path.lower().endswith(".pdf"):
                path += ".pdf"
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(path)
            self.configure_receipt_printer(printer, receipt_height_mm)
        elif mode == "print":
            self.configure_receipt_printer(printer, receipt_height_mm)
            if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
                return
            self.configure_receipt_printer(printer, receipt_height_mm)

        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "Fiş", "Yazıcı/PDF başlatılamadı.")
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        page_rect = printer.pageRect(QPrinter.Unit.DevicePixel).toRect()
        painter.fillRect(page_rect, QColor("#ffffff"))
        painter.drawPixmap(page_rect, receipt_pix)
        painter.end()
        if mode == "pdf":
            QMessageBox.information(self, "Başarılı", "PDF fiş çıktısı alındı.")
