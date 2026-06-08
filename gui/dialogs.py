# -*- coding: utf-8 -*-
import os
import tempfile
import base64
import qrcode
import requests
import datetime
import mimetypes
import re
import html as html_lib
from PyQt6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QLineEdit, QTextEdit, QDialogButtonBox, 
                             QComboBox, QFileDialog, QMessageBox, QScrollArea, QSizePolicy, QMenu,
                             QApplication)
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal, QEvent
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QCursor, QFont
from config import DARK_THEME, format_money, safe_float, get_photo_url, IMGBB_API_KEY, NETLIFY_URL

def get_record_photos(record_data):
    photos = []
    raw_photos = record_data.get("photos", {}) if isinstance(record_data, dict) else {}
    if isinstance(raw_photos, dict):
        items = raw_photos.items()
    elif isinstance(raw_photos, list):
        items = [(str(i), v) for i, v in enumerate(raw_photos)]
    else:
        items = []
    for key, item in items:
        if isinstance(item, dict):
            url = item.get("url")
            created_at = item.get("created_at", "")
            provider = item.get("provider") or item.get("storage_provider") or ""
            thumb_url = item.get("thumb_url") or item.get("thumbnail_url") or url
            original_name = item.get("original_name", "")
            size_bytes = item.get("size_bytes", "")
            content_type = item.get("content_type", "")
        else:
            url = item
            created_at = ""
            provider = ""
            thumb_url = url
            original_name = ""
            size_bytes = ""
            content_type = ""
        if url:
            photos.append({
                "id": str(key),
                "url": str(url),
                "thumb_url": str(thumb_url or url),
                "created_at": str(created_at),
                "provider": str(provider),
                "original_name": str(original_name),
                "size_bytes": size_bytes,
                "content_type": str(content_type)
            })
    for idx, legacy_key in enumerate(["photo_url", "photo_url_2", "photo_url_3"], start=1):
        url = record_data.get(legacy_key) if isinstance(record_data, dict) else ""
        if url:
            photos.append({"id": legacy_key, "url": str(url), "thumb_url": str(url), "created_at": "", "provider": "legacy", "legacy_key": legacy_key, "legacy_index": idx})
    return photos

class LoadImageThread(QThread):
    image_loaded = pyqtSignal(bytes)
    error_occurred = pyqtSignal()
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            req = requests.get(self.url, timeout=15)
            if self.isInterruptionRequested():
                return
            if req.status_code == 200: self.image_loaded.emit(req.content)
            else: self.error_occurred.emit()
        except:
            if not self.isInterruptionRequested():
                self.error_occurred.emit()

class CustomEditDialog(QDialog):
    def __init__(self, title, label_text, default_text="", parent=None, is_multiline=False):
        super().__init__(parent); self.setWindowTitle(title); self.setMinimumWidth(400); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); layout.addWidget(QLabel(f"<b>{label_text}</b>"))
        self.is_multiline = is_multiline
        if is_multiline: self.inp = QTextEdit(); self.inp.setPlainText(str(default_text)); self.inp.setMinimumHeight(100)
        else: self.inp = QLineEdit(str(default_text))
        self.inp.setStyleSheet("""
            QLineEdit, QTextEdit {
                background-color: #ffffff;
                color: #111827;
                border: 1px solid #94a3b8;
                border-radius: 7px;
                padding: 9px;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
            }
            QLineEdit:focus, QTextEdit:focus {
                border: 2px solid #2563eb;
            }
        """)
        if is_multiline:
            self.inp.textChanged.connect(self.force_uppercase_textedit)
        else:
            self.inp.textEdited.connect(self.force_uppercase_lineedit)
        layout.addWidget(self.inp); btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept); btn_box.rejected.connect(self.reject); layout.addWidget(btn_box)
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)

    def normalize_upper(self, text):
        return str(text or "").replace("i", "İ").upper()

    def force_uppercase_lineedit(self, text):
        upper = self.normalize_upper(text)
        if text == upper:
            return
        pos = self.inp.cursorPosition()
        self.inp.blockSignals(True)
        self.inp.setText(upper)
        self.inp.setCursorPosition(min(pos, len(upper)))
        self.inp.blockSignals(False)

    def force_uppercase_textedit(self):
        text = self.inp.toPlainText()
        upper = self.normalize_upper(text)
        if text == upper:
            return
        cursor = self.inp.textCursor()
        pos = cursor.position()
        self.inp.blockSignals(True)
        self.inp.setPlainText(upper)
        cursor.setPosition(min(pos, len(upper)))
        self.inp.setTextCursor(cursor)
        self.inp.blockSignals(False)

    def get_text(self): return self.inp.toPlainText().strip() if self.is_multiline else self.inp.text().strip()

class ViewImageDialog(QDialog):
    def __init__(self, record_data, kid, main_app_ref, current_idx=1, parent=None):
        super().__init__(parent); self.setWindowTitle("Cihaz Fotoğraf Galerisi"); self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.record_data = record_data; self.kid = kid; self.main_app_ref = main_app_ref; self.current_idx = current_idx
        self.photos = get_record_photos(self.record_data)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); top_h = QHBoxLayout()
        self.title_lbl = QLabel(f"<b>Cihaz Fotoğrafları</b>")
        top_h.addWidget(self.title_lbl); top_h.addStretch()
        self.btn_fs = QPushButton("⛶ Tam Ekran"); self.btn_fs.setStyleSheet("background-color: #3584e4; color: white; font-weight: bold;"); self.btn_fs.clicked.connect(self.toggle_fs); top_h.addWidget(self.btn_fs)
        btn_close = QPushButton("✕ Kapat"); btn_close.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;"); btn_close.clicked.connect(self.close); top_h.addWidget(btn_close)
        layout.addLayout(top_h)
        
        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True); self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        self.img_lbl = QLabel("Fotoğraf yükleniyor..."); self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll_area.setWidget(self.img_lbl); layout.addWidget(self.scroll_area, 1)
        
        self.img_lbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.img_lbl.customContextMenuRequested.connect(self.show_context_menu)
        
        bottom_h = QHBoxLayout(); bottom_h.addStretch()
        self.nav_buttons = {}
        self.nav_bar = bottom_h
        self.add_batch_btn = QPushButton("➕ 3 Fotoğraf Ekle")
        self.add_batch_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.add_batch_btn.clicked.connect(self.open_photo_capture)
        bottom_h.addWidget(self.add_batch_btn)
        bottom_h.addStretch(); layout.addLayout(bottom_h)
        
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
        self.original_pixmap = None; self.is_fs = False; self.drag_pos = QPoint(); self.pan_pos = QPoint(); self.panning = False; self.zoom_factor = 1.0; self.resize(850, 680)
        self.scroll_area.viewport().installEventFilter(self)
        self.img_lbl.installEventFilter(self)
        self.load_thread = None; self.old_load_threads = []; self.setup_buttons(); self.load_photo(self.current_idx)

    def setup_buttons(self):
        for idx, btn in list(self.nav_buttons.items()):
            self.nav_bar.removeWidget(btn)
            btn.deleteLater()
        self.nav_buttons = {}
        self.photos = get_record_photos(self.record_data)
        insert_at = max(0, self.nav_bar.count() - 2)
        for i, _photo in enumerate(self.photos, start=1):
            btn = QPushButton(f"📷 {i}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda ch, idx=i: self.handle_nav_click(idx))
            self.nav_bar.insertWidget(insert_at + i - 1, btn)
            self.nav_buttons[i] = btn
        if not self.photos:
            self.title_lbl.setText("<b>Cihaz Fotoğrafları</b>")

    def handle_nav_click(self, idx):
        self.load_photo(idx)

    def open_photo_capture(self):
        PhotoDialog(self.kid, self.main_app_ref.user_id, NETLIFY_URL, self.main_app_ref, 1).exec()
        from database.threads import db
        v = db.child("users").child(self.main_app_ref.user_id).child("kayitlar").child(self.kid).get(self.main_app_ref.token).val()
        if v: self.record_data = v
        self.setup_buttons()
        self.load_photo(max(1, len(self.photos)))

    def show_context_menu(self, pos):
        if not self.photos or self.current_idx < 1 or self.current_idx > len(self.photos): return
        photo = self.photos[self.current_idx - 1]
        m = QMenu(self)
        b_del = m.addAction("🗑️ Fotoğrafı Sil")
        action = m.exec(QCursor.pos())
        if action == b_del:
            if QMessageBox.question(self, "Sil", f"{self.current_idx}. Fotoğraf silinecek?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
                try:
                    from database.threads import db
                    record_ref = db.child("users").child(self.main_app_ref.user_id).child("kayitlar").child(self.kid)
                    if photo.get("legacy_key"):
                        self.delete_firebase_path(f"users/{self.main_app_ref.user_id}/kayitlar/{self.kid}/{photo['legacy_key']}")
                    else:
                        self.delete_firebase_path(f"users/{self.main_app_ref.user_id}/kayitlar/{self.kid}/photos/{photo['id']}")
                    try:
                        if self.main_app_ref and hasattr(self.main_app_ref, "log_record_action"):
                            self.main_app_ref.log_record_action(self.kid, "Fotoğraf silindi", audit=False)
                    except Exception:
                        pass
                    v = record_ref.get(self.main_app_ref.token).val() or {}
                    self.record_data = v if isinstance(v, dict) else {}
                    self.main_app_ref.refresh_all_tables()
                    next_idx = min(self.current_idx, max(1, len(get_record_photos(self.record_data))))
                    self.setup_buttons()
                    self.load_photo(next_idx)
                except Exception as e:
                    QMessageBox.warning(self, "Silme Hatası", f"Fotoğraf silinemedi:\n{e}")

    def delete_firebase_path(self, path):
        token = getattr(self.main_app_ref, "token", "")
        if not token:
            raise RuntimeError("Oturum doğrulanamadı. Lütfen çıkış yapıp tekrar giriş yapın.")
        url = f"https://metafold-teknik-servis-default-rtdb.europe-west1.firebasedatabase.app/{path}.json"
        res = requests.delete(url, params={"auth": token}, timeout=20)
        if not res.ok:
            raise RuntimeError(f"{res.status_code} - {res.text}")

    def load_photo(self, idx):
        if not self.photos:
            self.current_idx = 1
            self.title_lbl.setText("<b>Cihaz Fotoğrafları</b>")
            for _k, b in self.nav_buttons.items():
                b.setStyleSheet("background-color: #555; color: white; padding: 12px 25px; border-radius: 6px;")
            self.img_lbl.setText("Bu kayıtta henüz fotoğraf yok.\nQR ile 3 fotoğraf eklemek için '3 Fotoğraf Ekle' butonuna tıklayın."); self.original_pixmap = None; self.img_lbl.setPixmap(QPixmap()); return
        if idx < 1 or idx > len(self.photos):
            idx = 1
        self.current_idx = idx; self.title_lbl.setText(f"<b>Cihaz Fotoğrafları - Aktif Olan: {idx}. Fotoğraf</b>")
        for k, b in self.nav_buttons.items():
            if k == idx: b.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 12px 25px; border-radius: 6px;")
            else: b.setStyleSheet("background-color: #555; color: white; padding: 12px 25px; border-radius: 6px;")
        url = self.photos[idx - 1].get("url")
        if not url:
            self.img_lbl.setText(f"Bu yuvada henüz fotoğraf yok.\nEklemek için aşağıdaki butona tıklayın."); self.original_pixmap = None; self.img_lbl.setPixmap(QPixmap()); return
        self.img_lbl.setText("Fotoğraf bulut sunucudan indiriliyor..."); self.zoom_factor = 1.0; self.original_pixmap = None
        if self.load_thread and self.load_thread.isRunning():
            old_thread = self.load_thread
            try:
                old_thread.image_loaded.disconnect()
                old_thread.error_occurred.disconnect()
            except:
                pass
            old_thread.requestInterruption()
            self.old_load_threads.append(old_thread)
            old_thread.finished.connect(lambda t=old_thread: self.cleanup_old_image_thread(t))
        self.load_thread = LoadImageThread(url); self.load_thread.image_loaded.connect(self.on_image_loaded); self.load_thread.error_occurred.connect(self.on_image_error); self.load_thread.start()

    def cleanup_old_image_thread(self, thread):
        try:
            if thread in self.old_load_threads:
                self.old_load_threads.remove(thread)
            thread.deleteLater()
        except:
            pass

    def on_image_loaded(self, data): self.original_pixmap = QPixmap(); self.original_pixmap.loadFromData(data); self.update_image()
    def on_image_error(self): self.img_lbl.setText("Fotoğraf yüklenemedi.")
    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton: self.toggle_fs()
    def eventFilter(self, obj, event):
        if obj in [self.scroll_area.viewport(), self.img_lbl]:
            if event.type() == QEvent.Type.Wheel:
                pos = event.position().toPoint()
                if obj == self.img_lbl:
                    pos = self.img_lbl.mapTo(self.scroll_area.viewport(), pos)
                self.apply_zoom(event.angleDelta().y(), pos)
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton and self.zoom_factor > 1.0:
                self.panning = True
                self.pan_pos = event.globalPosition().toPoint()
                self.img_lbl.setCursor(Qt.CursorShape.ClosedHandCursor)
                return True
            if event.type() == QEvent.Type.MouseMove and self.panning:
                new_pos = event.globalPosition().toPoint()
                delta = new_pos - self.pan_pos
                self.pan_pos = new_pos
                self.scroll_area.horizontalScrollBar().setValue(self.scroll_area.horizontalScrollBar().value() - delta.x())
                self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().value() - delta.y())
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self.panning:
                self.panning = False
                self.img_lbl.setCursor(Qt.CursorShape.OpenHandCursor if self.zoom_factor > 1.0 else Qt.CursorShape.ArrowCursor)
                return True
        return super().eventFilter(obj, event)
    def wheelEvent(self, event):
        self.apply_zoom(event.angleDelta().y(), event.position().toPoint())
    def apply_zoom(self, delta_y, pos=None):
        if not self.original_pixmap or self.original_pixmap.isNull(): return
        old_zoom = self.zoom_factor
        viewport = self.scroll_area.viewport()
        base_p = self.original_pixmap.scaled(
            viewport.width(),
            viewport.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        old_w = int(base_p.width() * old_zoom)
        old_h = int(base_p.height() * old_zoom)
        old_label_w = max(old_w, viewport.width())
        old_label_h = max(old_h, viewport.height())
        old_margin_x = max(0, (old_label_w - old_w) // 2)
        old_margin_y = max(0, (old_label_h - old_h) // 2)
        hbar = self.scroll_area.horizontalScrollBar()
        vbar = self.scroll_area.verticalScrollBar()
        if pos and old_zoom > 0:
            anchor_x = max(0, (hbar.value() + pos.x() - old_margin_x) / old_zoom)
            anchor_y = max(0, (vbar.value() + pos.y() - old_margin_y) / old_zoom)
        else:
            anchor_x = base_p.width() / 2
            anchor_y = base_p.height() / 2
            pos = viewport.rect().center()
        self.zoom_factor = self.zoom_factor * 1.15 if delta_y > 0 else self.zoom_factor / 1.15
        self.zoom_factor = max(1.0, min(6.0, self.zoom_factor))
        if abs(self.zoom_factor - old_zoom) < 0.001: return
        self.update_image()
        QApplication.processEvents()
        new_w = int(base_p.width() * self.zoom_factor)
        new_h = int(base_p.height() * self.zoom_factor)
        new_label_w = max(new_w, viewport.width())
        new_label_h = max(new_h, viewport.height())
        new_margin_x = max(0, (new_label_w - new_w) // 2)
        new_margin_y = max(0, (new_label_h - new_h) // 2)
        hbar.setValue(int(new_margin_x + anchor_x * self.zoom_factor - pos.x()))
        vbar.setValue(int(new_margin_y + anchor_y * self.zoom_factor - pos.y()))
    def toggle_fs(self):
        if self.is_fs: self.showNormal(); self.btn_fs.setText("⛶ Tam Ekran"); self.is_fs = False
        else: self.showMaximized(); self.btn_fs.setText("🗗 Pencereye Dön"); self.is_fs = True
        self.zoom_factor = 1.0; self.panning = False; QTimer.singleShot(100, self.update_image)
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 50: self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()
    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull() and not self.is_fs: self.move(event.globalPosition().toPoint() - self.drag_pos); event.accept()
    def mouseReleaseEvent(self, event): self.drag_pos = QPoint()
    def resizeEvent(self, event): super().resizeEvent(event); self.update_image()
    def update_image(self):
        if self.original_pixmap and not self.original_pixmap.isNull():
            scroll_w = self.scroll_area.width() - 2; scroll_h = self.scroll_area.height() - 2
            if self.zoom_factor <= 1.0:
                self.scroll_area.setWidgetResizable(True)
                p = self.original_pixmap.scaled(scroll_w, scroll_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.img_lbl.setPixmap(p)
                self.img_lbl.resize(self.scroll_area.viewport().size())
                self.img_lbl.setCursor(Qt.CursorShape.ArrowCursor)
            else:
                self.scroll_area.setWidgetResizable(False)
                base_p = self.original_pixmap.scaled(scroll_w, scroll_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                w = int(base_p.width() * self.zoom_factor); h = int(base_p.height() * self.zoom_factor)
                self.img_lbl.resize(max(w, self.scroll_area.viewport().width()), max(h, self.scroll_area.viewport().height()))
                self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.img_lbl.setPixmap(self.original_pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.img_lbl.setCursor(Qt.CursorShape.OpenHandCursor)

class ViewPatternDialog(QDialog):
    def __init__(self, pattern_str, parent=None):
        super().__init__(parent); self.setFixedSize(360, 420); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.frame = QWidget(self); self.frame.setObjectName("DialogFrame"); self.frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME); self.frame.setFixedSize(360, 420)
        btn_close = QPushButton("✕", self.frame); btn_close.setFixedSize(30, 30); btn_close.move(320, 10); btn_close.setStyleSheet("background: transparent; color: #888; border: none; font-size: 16px; border-radius: 0px;"); btn_close.clicked.connect(self.close)
        lbl_title = QLabel("<b>Kayıtlı Ekran Deseni</b>", self.frame); lbl_title.setStyleSheet("font-size: 16px;"); lbl_title.move(90, 20)
        self.canvas = QWidget(self.frame); self.canvas.setFixedSize(340, 340); self.canvas.move(10, 60); self.path = []
        try: self.path = [int(x)-1 for x in pattern_str.replace("Desen:", "").strip().split('-') if x.isdigit()]
        except: pass
        self.points = [QPoint(60 + c*110, 60 + r*110) for r in range(3) for c in range(3)]; self.canvas.paintEvent = self.canvas_paintEvent
        main_layout = QVBoxLayout(self); main_layout.addWidget(self.frame); main_layout.setContentsMargins(0, 0, 0, 0)
    def canvas_paintEvent(self, e):
        p = QPainter(self.canvas); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.path) > 0:
            p.setPen(QPen(QColor("#ef4444"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for i in range(len(self.path)-1):
                idx1, idx2 = self.path[i], self.path[i+1]
                if 0 <= idx1 < 9 and 0 <= idx2 < 9: p.drawLine(self.points[idx1], self.points[idx2])
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(self.points): p.setBrush(QColor("#ef4444" if i in self.path else "#555")); p.drawEllipse(pt, 12, 12)

class ReadOnlyDialog(QDialog):
    def __init__(self, title, content, parent=None, actions=None):
        super().__init__(parent); self.setMinimumWidth(500); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame)
        
        # BAŞLIK BÖLÜMÜ VE KAPATMA BUTONU
        top_h = QHBoxLayout(); top_h.addWidget(QLabel(f"<b>{title}</b>")); top_h.addStretch()
        for action_text, callback in (actions or []):
            action_btn = QPushButton(action_text)
            action_btn.setStyleSheet("background:#2563eb; color:white; font-weight:bold; border-radius:5px; padding:5px 10px;")
            action_btn.clicked.connect(callback)
            top_h.addWidget(action_btn)
        btn_close = QPushButton("✕"); btn_close.setFixedSize(25, 25); btn_close.setStyleSheet("background:#ef4444; color:white; font-weight:bold; border-radius:4px;"); btn_close.clicked.connect(self.close); top_h.addWidget(btn_close); layout.addLayout(top_h)
        
        self.text_edit = QTextEdit()
        theme = ""
        try:
            theme = str(parent.user_setting_value("theme", "Dark")) if parent and hasattr(parent, "user_setting_value") else "Dark"
        except Exception:
            theme = "Dark"
        is_light = "Light" in theme or "Açık" in theme or "Emerald" in theme or "Zümrüt" in theme
        bg = "#ffffff" if is_light else "#1f2329"
        text = "#0f172a" if is_light else "#f8fafc"
        border = "#cbd5e1" if is_light else "#475569"
        accent = "#2563eb" if is_light else "#60a5fa"
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ background-color: {bg}; color: {text}; font-size: 14px; "
            f"border: 1px solid {border}; border-radius: 6px; padding: 10px; }}"
            f"b {{ color: {accent}; }}"
        )
        content_text = str(content if content is not None else "")
        looks_html = bool(re.search(r"</?(html|body|div|span|p|br|b|strong|i|ul|ol|li|table|tr|td|h[1-6]|style|img)\b", content_text, re.IGNORECASE))
        if looks_html:
            self.text_edit.setHtml(content_text)
        else:
            self.text_edit.setPlainText(content_text)
        self.text_edit.setReadOnly(True)
        self.text_edit.setMinimumHeight(300)
        
        layout.addWidget(self.text_edit)
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)

class InfoDialog(QDialog):
    def __init__(self, data, kid, main_app_ref, parent=None):
        super().__init__(parent); self.setMinimumWidth(450); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); sif = data.get("sifre", "Belirtilmemiş"); sif = "Belirtilmemiş" if sif == "" else sif; aks = []
        if data.get("sim"): aks.append("SIM Kart")
        if data.get("sd"): aks.append("Hafıza Kartı")
        if data.get("kilif"): aks.append("Kılıf")
        aks_str = ", ".join(aks) if aks else "Yok"; bayi_str = " (Sürekli Bayi)" if data.get("is_bayi") else ""
        note_html = html_lib.escape(str(data.get("not", "") or "Not Yok")).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
        html = f"<h3 style='color:#3584e4;'>Müşteri: {data.get('m')}{bayi_str}</h3>"
        html += f"<b>Kayıt No:</b> {data.get('c_no')}<br><b>Telefon:</b> {data.get('t', 'Bilinmiyor')}<br><b>Cihaz:</b> {data.get('ci')}<br><b>Arıza:</b> {data.get('a')}<br><hr>"
        html += f"<b>Şifre / Desen:</b> <span style='color:#ef4444;'>{sif}</span><br><b>Aksesuarlar:</b> {aks_str}<br><b>Müşteri Notu:</b><br>{note_html}<br><hr><b>Durum:</b> {data.get('d')}<br><b>Ödeme Tipi:</b> {data.get('odeme_tipi', 'Belirtilmemiş')}<br><b>Kayıt Tarihi:</b> {data.get('z')}"
        if data.get("yapilan_islem"):
            masraf = safe_float(data.get('masraf', '0'))
            html += f"<br><br><b>İşlem:</b> {data.get('yapilan_islem')}<br><b>Ücret:</b> {format_money(masraf, '₺')}<br><b>Ödeme:</b> {data.get('odeme_durumu', 'Bilinmiyor')}"
        layout.addWidget(QLabel(html)); btn_layout = QHBoxLayout()
        if "Desen" in sif: 
            btn_desen = QPushButton("📱 Deseni Göster"); btn_desen.setStyleSheet("background-color: #9b59b6; font-size: 14px; padding: 10px;")
            btn_desen.clicked.connect(lambda: ViewPatternDialog(sif, self).exec()); btn_layout.addWidget(btn_desen)
        if get_record_photos(data):
            btn_pic = QPushButton("📷 Fotoğraflar"); btn_pic.setStyleSheet("background-color: #e67e22; font-size: 14px; padding: 10px;")
            btn_pic.clicked.connect(lambda ch, d=data, record_id=kid, ref=main_app_ref: ViewImageDialog(d, record_id, ref, 1, self).exec()); btn_layout.addWidget(btn_pic)
        if btn_layout.count() > 0: layout.addLayout(btn_layout)
        btn_ok = QPushButton("Kapat"); btn_ok.clicked.connect(self.close); layout.addWidget(btn_ok); main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)

class PhotoDialog(QDialog):
    def __init__(self, record_id, user_id, base_url, main_app_ref=None, photo_index=1):
        super().__init__(); self.photo_index = photo_index
        self.setWindowTitle("QR Kamera - 3 Fotoğraf"); self.setFixedSize(350, 480); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.main_app_ref = main_app_ref; self.record_id = record_id; self.user_id = user_id
        self.frame = QWidget(self); self.frame.setObjectName("DialogFrame"); self.frame.setStyleSheet(main_app_ref.styleSheet() if main_app_ref else DARK_THEME)
        layout = QVBoxLayout(self.frame)
        info = QLabel("<b>Kamerayı Açmak İçin Kodu Okutun<br>3 fotoğraf paneli açılacak</b>"); info.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(info)
        web_url = f"{base_url.rstrip('/')}/kamera.html?rid={record_id}&uid={user_id}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2); qr.add_data(web_url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white"); qr_path = os.path.join(tempfile.gettempdir(), f"qr_{record_id}.png"); img.save(qr_path)
        qr_label = QLabel(); qr_label.setPixmap(QPixmap(qr_path).scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio)); qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(qr_label)
        btn_check = QPushButton("✅ Fotoğrafı Çektim (Kapat)"); btn_check.setStyleSheet("background-color: #2ecc71; color: white; padding: 12px; font-size: 14px; font-weight: bold;"); btn_check.clicked.connect(self.check_photo); layout.addWidget(btn_check)
        btn_manual = QPushButton("💻 Bilgisayardan Yükle"); btn_manual.setStyleSheet("background-color: #3498db; color: white; padding: 10px; font-size: 13px;"); btn_manual.clicked.connect(self.upload_manual); layout.addWidget(btn_manual)
        btn_close = QPushButton("İptal / Kapat"); btn_close.clicked.connect(self.close); layout.addWidget(btn_close)
        main_layout = QVBoxLayout(self); main_layout.addWidget(self.frame); main_layout.setContentsMargins(0, 0, 0, 0)

    def check_photo(self):
        if self.main_app_ref: self.main_app_ref.refresh_all_tables()
        self.close()

    def upload_manual(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resim (*.png *.jpg *.jpeg)")
        if file_path:
            try:
                with open(file_path, "rb") as file:
                    raw_bytes = file.read()
                    payload = {"key": IMGBB_API_KEY, "image": base64.b64encode(raw_bytes).decode('utf-8')}
                    res = requests.post("https://api.imgbb.com/1/upload", data=payload, timeout=30)
                    res.raise_for_status()
                    payload_json = res.json()
                    image_data = payload_json.get("data", {})
                    url = image_data.get("url")
                    if not url:
                        raise RuntimeError(payload_json.get("error", {}).get("message", "ImgBB fotoğraf linki döndürmedi."))
                from database.threads import db
                if self.main_app_ref: 
                    token = getattr(self.main_app_ref, "token", "")
                    if not token:
                        raise RuntimeError("Oturum doğrulanamadı. Lütfen çıkış yapıp tekrar giriş yapın.")
                    staff = getattr(self.main_app_ref, "current_staff", {}) or {}
                    db.child("users").child(self.user_id).child("kayitlar").child(self.record_id).child("photos").push({
                        "url": url,
                        "thumb_url": image_data.get("thumb", {}).get("url") or image_data.get("medium", {}).get("url") or url,
                        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
                        "source": "desktop",
                        "provider": "imgbb",
                        "storage_provider": "imgbb",
                        "content_type": mimetypes.guess_type(file_path)[0] or "image/jpeg",
                        "size_bytes": len(raw_bytes),
                        "original_name": os.path.basename(file_path),
                        "delete_url": image_data.get("delete_url", ""),
                        "remote_id": image_data.get("id", ""),
                        "migratable": True,
                        "personel": str(staff.get("name", "YÖNETİCİ")),
                        "rol": str(staff.get("role", "Yönetici")),
                        "hesap": str(getattr(self.main_app_ref, "user_email", "") or "")
                    }, token)
                    QMessageBox.information(self, "Başarılı", f"Fotoğraf {self.photo_index} yüklendi!")
                    self.main_app_ref.refresh_all_tables()
                self.close()
            except Exception as e: QMessageBox.warning(self, "Yükleme Hatası", f"Bağlantı Hatası:\n{str(e)}")

class PatternLock(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent); self.setFixedSize(360, 420); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        self.path = []; self.current_pos = None; self.points = []; layout = QVBoxLayout(frame)
        layout.addWidget(QLabel("<b>Deseni Çizmek İçin Sürükleyin:</b>"), alignment=Qt.AlignmentFlag.AlignCenter); self.canvas = QWidget(); self.canvas.setFixedSize(340, 340); layout.addWidget(self.canvas)
        btn_clear = QPushButton("Temizle / Yeniden Çiz"); btn_clear.clicked.connect(self.clear_pattern); layout.addWidget(btn_clear)
        for r in range(3):
            for c in range(3): self.points.append(QPoint(60 + c*110, 60 + r*110))
        self.canvas.paintEvent = self.canvas_paintEvent; self.canvas.mousePressEvent = self.canvas_mousePressEvent; self.canvas.mouseMoveEvent = self.canvas_mouseMoveEvent; self.canvas.mouseReleaseEvent = self.canvas_mouseReleaseEvent
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
    def clear_pattern(self): self.path = []; self.canvas.update()
    def canvas_mousePressEvent(self, e): self.path = []; self.check_point(e.pos()); self.canvas.update()
    def canvas_mouseMoveEvent(self, e): self.current_pos = e.pos(); self.check_point(e.pos()); self.canvas.update()
    def canvas_mouseReleaseEvent(self, e):
        self.current_pos = None; self.canvas.update()
        if len(self.path) > 1: QTimer.singleShot(500, self.accept)
    def check_point(self, pos):
        for i, pt in enumerate(self.points):
            if i not in self.path and (pos - pt).manhattanLength() < 40: self.path.append(i)
    def canvas_paintEvent(self, e):
        p = QPainter(self.canvas); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if len(self.path) > 0:
            p.setPen(QPen(QColor("#3584e4"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            for i in range(len(self.path)-1): p.drawLine(self.points[self.path[i]], self.points[self.path[i+1]])
            if self.current_pos: p.drawLine(self.points[self.path[-1]], self.current_pos)
        p.setPen(Qt.PenStyle.NoPen)
        for i, pt in enumerate(self.points): p.setBrush(QColor("#2ecc71" if i in self.path else "#555")); p.drawEllipse(pt, 12, 12)
    def get_pattern(self): return "-".join([str(i+1) for i in self.path])

class PartDialog(QDialog):
    def __init__(self, firmalar, parent=None):
        super().__init__(parent); self.setFixedSize(350, 320); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.drag_pos = QPoint()
        self.frame = QWidget(self); self.frame.setObjectName("DialogFrame"); self.frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        self.frame.installEventFilter(self)
        layout = QVBoxLayout(self.frame)
        self.title_bar = QWidget(self.frame)
        self.title_bar.setCursor(Qt.CursorShape.ArrowCursor)
        self.title_bar.installEventFilter(self)
        title_row = QHBoxLayout(self.title_bar)
        title_row.setContentsMargins(0, 0, 0, 0)
        self.drag_handle = QLabel("<b>Kullanılan Parça</b>")
        self.drag_handle.setCursor(Qt.CursorShape.ArrowCursor)
        self.drag_handle.installEventFilter(self)
        btn_close = QPushButton("×")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet("background:#ef4444; color:white; font-weight:bold; border-radius:4px;")
        btn_close.clicked.connect(self.reject)
        title_row.addWidget(self.drag_handle)
        title_row.addStretch()
        title_row.addWidget(btn_close)
        layout.addWidget(self.title_bar)
        self.part_in = QLineEdit(); self.part_in.setPlaceholderText("Parça Adı (Örn: Ekran)"); self.part_in.textEdited.connect(lambda text, w=self.part_in: self.force_uppercase(w, text)); self.cost_in = QLineEdit(); self.cost_in.setPlaceholderText("Maliyet (Dolar $)"); self.firm_combo = QComboBox(); self.firm_combo.addItems(firmalar)
        btn = QPushButton("Kullanıldı Olarak Kaydet"); btn.clicked.connect(self.accept); layout.addWidget(QLabel("<b>Parça Adı:</b>")); layout.addWidget(self.part_in); layout.addWidget(QLabel("<b>Maliyet (Dolar $, Sadece Rakam):</b>")); layout.addWidget(self.cost_in); layout.addWidget(QLabel("<b>Alındığı Toptancı:</b>")); layout.addWidget(self.firm_combo); layout.addStretch(); layout.addWidget(btn)
        main_layout = QVBoxLayout(self); main_layout.addWidget(self.frame); main_layout.setContentsMargins(0, 0, 0, 0)

    def _is_drag_area(self, obj, event):
        if obj in [getattr(self, "drag_handle", None), getattr(self, "title_bar", None)]:
            return True
        if obj is getattr(self, "frame", None):
            try:
                return event.position().y() <= 48
            except Exception:
                return False
        return False

    def _handle_drag_event(self, obj, event):
        if not self._is_drag_area(obj, event):
            return False
        if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return True
        if event.type() == QEvent.Type.MouseMove and event.buttons() == Qt.MouseButton.LeftButton and not self.drag_pos.isNull():
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()
            return True
        if event.type() == QEvent.Type.MouseButtonRelease:
            self.drag_pos = QPoint()
            event.accept()
            return True
        return False

    def eventFilter(self, obj, event):
        if self._handle_drag_event(obj, event):
            return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if not self._handle_drag_event(self.frame, event):
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._handle_drag_event(self.frame, event):
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self._handle_drag_event(self.frame, event):
            super().mouseReleaseEvent(event)

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

    def get_data(self): return self.normalize_upper(self.part_in.text()).strip(), self.cost_in.text().strip(), self.firm_combo.currentText()
