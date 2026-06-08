# -*- coding: utf-8 -*-
import os
import tempfile
import base64
import qrcode
import requests
from PyQt6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit, QDialogButtonBox, QComboBox, QFileDialog, QMessageBox, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, QPoint, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QCursor, QFont
from config import DARK_THEME, format_money, safe_float, get_photo_url, IMGBB_API_KEY, NETLIFY_URL
from database.threads import db

# GÖRSEL İNDİRME MOTORU (EKSİK OLAN PARÇA BURAYA EKLENDİ)
class LoadImageThread(QThread):
    image_loaded = pyqtSignal(bytes)
    error_occurred = pyqtSignal()
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            req = requests.get(self.url, timeout=15)
            if req.status_code == 200:
                self.image_loaded.emit(req.content)
            else:
                self.error_occurred.emit()
        except:
            self.error_occurred.emit()

class CustomEditDialog(QDialog):
    def __init__(self, title, label_text, default_text="", parent=None, is_multiline=False):
        super().__init__(parent); self.setWindowTitle(title); self.setMinimumWidth(400); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); layout.addWidget(QLabel(f"<b>{label_text}</b>"))
        self.is_multiline = is_multiline
        if is_multiline: self.inp = QTextEdit(); self.inp.setPlainText(str(default_text)); self.inp.setMinimumHeight(100)
        else: self.inp = QLineEdit(str(default_text))
        layout.addWidget(self.inp); btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept); btn_box.rejected.connect(self.reject); layout.addWidget(btn_box)
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
    def get_text(self): return self.inp.toPlainText().strip() if self.is_multiline else self.inp.text().strip()

class ViewImageDialog(QDialog):
    def __init__(self, urls_dict, current_idx=1, parent=None):
        super().__init__(parent); self.setWindowTitle("Cihaz Fotoğrafı"); self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.urls_dict = urls_dict; self.current_idx = current_idx
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); top_h = QHBoxLayout()
        self.title_lbl = QLabel(f"<b>Cihaz Fotoğrafı - {self.current_idx}</b>")
        top_h.addWidget(self.title_lbl); top_h.addStretch()
        self.btn_fs = QPushButton("⛶ Tam Ekran"); self.btn_fs.setStyleSheet("background-color: #3584e4; color: white; font-weight: bold;"); self.btn_fs.clicked.connect(self.toggle_fs); top_h.addWidget(self.btn_fs)
        btn_close = QPushButton("✕ Kapat"); btn_close.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;"); btn_close.clicked.connect(self.close); top_h.addWidget(btn_close)
        layout.addLayout(top_h)
        
        self.scroll_area = QScrollArea(); self.scroll_area.setWidgetResizable(True); self.scroll_area.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        self.img_lbl = QLabel("Fotoğraf yükleniyor..."); self.img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll_area.setWidget(self.img_lbl); layout.addWidget(self.scroll_area, 1)
        
        # ALT MENÜ (1-2-3 Butonları)
        bottom_h = QHBoxLayout(); bottom_h.addStretch()
        self.nav_buttons = {}
        for i in range(1, 4):
            if i in self.urls_dict:
                btn = QPushButton(f"📷 Fotoğraf {i}"); btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda ch, idx=i: self.load_photo(idx)); bottom_h.addWidget(btn); self.nav_buttons[i] = btn
        bottom_h.addStretch(); layout.addLayout(bottom_h)
        
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
        self.original_pixmap = None; self.is_fs = False; self.drag_pos = QPoint(); self.zoom_factor = 1.0; self.resize(850, 650)
        self.load_thread = None; self.load_photo(self.current_idx)

    def load_photo(self, idx):
        self.current_idx = idx; self.title_lbl.setText(f"<b>Cihaz Fotoğrafı - {idx}</b>")
        self.img_lbl.setText("Fotoğraf bulut sunucudan indiriliyor...\nLütfen bekleyin."); self.zoom_factor = 1.0; self.original_pixmap = None
        for k, b in self.nav_buttons.items():
            if k == idx: b.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px 20px;")
            else: b.setStyleSheet("background-color: #555; color: white; padding: 10px 20px;")
        url = self.urls_dict.get(idx)
        
        # Güvenli durdurma mekanizması eklendi
        if self.load_thread:
            try:
                self.load_thread.image_loaded.disconnect()
                self.load_thread.error_occurred.disconnect()
                self.load_thread.terminate()
            except: pass
            
        self.load_thread = LoadImageThread(url)
        self.load_thread.image_loaded.connect(self.on_image_loaded)
        self.load_thread.error_occurred.connect(self.on_image_error)
        self.load_thread.start()

    def on_image_loaded(self, data): self.original_pixmap = QPixmap(); self.original_pixmap.loadFromData(data); self.update_image()
    def on_image_error(self): self.img_lbl.setText("Fotoğraf yüklenemedi.\nBağlantı kalitesini kontrol edin.")
    def wheelEvent(self, event):
        if not self.original_pixmap or self.original_pixmap.isNull(): return
        if event.angleDelta().y() > 0: self.zoom_factor *= 1.2
        else: self.zoom_factor /= 1.2
        if self.zoom_factor < 0.2: self.zoom_factor = 0.2
        self.update_image()
    def toggle_fs(self):
        if self.is_fs: self.showNormal(); self.btn_fs.setText("⛶ Tam Ekran"); self.is_fs = False
        else: self.showMaximized(); self.btn_fs.setText("🗗 Pencereye Dön"); self.is_fs = True
        self.zoom_factor = 1.0; QTimer.singleShot(100, self.update_image)
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
                if self.zoom_factor < 1.0: p = p.scaled(int(p.width() * self.zoom_factor), int(p.height() * self.zoom_factor), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.img_lbl.setPixmap(p)
            else:
                self.scroll_area.setWidgetResizable(False)
                base_p = self.original_pixmap.scaled(scroll_w, scroll_h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                w = int(base_p.width() * self.zoom_factor); h = int(base_p.height() * self.zoom_factor)
                self.img_lbl.resize(w, h); self.img_lbl.setPixmap(self.original_pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

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
    def __init__(self, title, content, parent=None):
        super().__init__(parent); self.setMinimumWidth(400); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); layout.addWidget(QLabel(f"<b>{title}</b>")); text_edit = QTextEdit(); text_edit.setPlainText(content); text_edit.setReadOnly(True); text_edit.setMinimumHeight(150); layout.addWidget(text_edit)
        btn_ok = QPushButton("Kapat"); btn_ok.clicked.connect(self.close); layout.addWidget(btn_ok); main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)

class InfoDialog(QDialog):
    def __init__(self, data, parent=None):
        super().__init__(parent); self.setMinimumWidth(450); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); sif = data.get("sifre", "Belirtilmemiş"); sif = "Belirtilmemiş" if sif == "" else sif; aks = []
        if data.get("sim"): aks.append("SIM Kart")
        if data.get("sd"): aks.append("Hafıza Kartı")
        if data.get("kilif"): aks.append("Kılıf")
        aks_str = ", ".join(aks) if aks else "Yok"; bayi_str = " (Sürekli Bayi)" if data.get("is_bayi") else ""
        html = f"<h3 style='color:#3584e4;'>Müşteri: {data.get('m')}{bayi_str}</h3>"
        html += f"<b>Kayıt No:</b> {data.get('c_no')}<br><b>Telefon:</b> {data.get('t', 'Bilinmiyor')}<br><b>Cihaz:</b> {data.get('ci')}</b><br><b>Arıza:</b> {data.get('a')}<br><hr>"
        html += f"<b>Şifre / Desen:</b> <span style='color:#ef4444;'>{sif}</span><br><b>Aksesuarlar:</b> {aks_str}<br><b>Müşteri Notu:</b> {data.get('not', 'Not Yok')}<br><hr><b>Durum:</b> {data.get('d')}<br><b>Kayıt Tarihi:</b> {data.get('z')}"
        if data.get("yapilan_islem"):
            masraf = safe_float(data.get('masraf', '0'))
            html += f"<br><br><b>İşlem:</b> {data.get('yapilan_islem')}<br><b>Ücret:</b> {format_money(masraf, '₺')}<br><b>Ödeme:</b> {data.get('odeme_durumu', 'Bilinmiyor')}"
        layout.addWidget(QLabel(html)); btn_layout = QHBoxLayout()
        
        if "Desen" in sif: 
            btn_desen = QPushButton("📱 Deseni Göster"); btn_desen.setStyleSheet("background-color: #9b59b6; font-size: 14px; padding: 10px;")
            btn_desen.clicked.connect(lambda: ViewPatternDialog(sif, self).exec()); btn_layout.addWidget(btn_desen)
            
        # YENİ GALERİ ALTYAPISI
        urls_dict = {}
        for i in range(1, 4):
            k = "photo_url" if i == 1 else f"photo_url_{i}"
            if data.get(k): urls_dict[i] = data.get(k)
            
        for i, p_url in urls_dict.items():
            btn_pic = QPushButton(f"📷 Foto {i}")
            btn_pic.setStyleSheet("background-color: #e67e22; font-size: 14px; padding: 10px;")
            btn_pic.clicked.connect(lambda ch, u_dict=urls_dict, idx=i: ViewImageDialog(u_dict, idx, self).exec())
            btn_layout.addWidget(btn_pic)
                
        if btn_layout.count() > 0: layout.addLayout(btn_layout)
        btn_ok = QPushButton("Kapat"); btn_ok.clicked.connect(self.close); layout.addWidget(btn_ok); main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)

class PhotoDialog(QDialog):
    def __init__(self, record_id, user_id, base_url, main_app_ref=None, photo_index=1):
        super().__init__(); self.photo_index = photo_index
        self.setWindowTitle(f"QR Kamera - Fotoğraf {photo_index}"); self.setFixedSize(350, 480); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.main_app_ref = main_app_ref; self.record_id = record_id; self.user_id = user_id
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(main_app_ref.styleSheet() if main_app_ref else DARK_THEME)
        layout = QVBoxLayout(frame)
        
        info = QLabel(f"<b>Kamerayı Açmak İçin Kodu Okutun<br>(Fotoğraf {photo_index}/3)</b>")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(info)
        
        web_url = f"{base_url.rstrip('/')}/kamera.html?rid={record_id}&uid={user_id}&pidx={photo_index}"
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=2); qr.add_data(web_url); qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white"); qr_path = os.path.join(tempfile.gettempdir(), f"qr_{record_id}_{photo_index}.png"); img.save(qr_path)
        
        qr_label = QLabel(); qr_label.setPixmap(QPixmap(qr_path).scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio)); qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter); layout.addWidget(qr_label)
        
        btn_check = QPushButton("✅ Fotoğrafı Çektim (Kapat)"); btn_check.setStyleSheet("background-color: #2ecc71; color: white; padding: 12px; font-size: 14px; font-weight: bold;"); btn_check.clicked.connect(self.check_photo); layout.addWidget(btn_check)
        btn_manual = QPushButton("💻 Bilgisayardan Yükle"); btn_manual.setStyleSheet("background-color: #3498db; color: white; padding: 10px; font-size: 13px;"); btn_manual.clicked.connect(self.upload_manual); layout.addWidget(btn_manual)
        btn_close = QPushButton("İptal / Kapat"); btn_close.clicked.connect(self.close); layout.addWidget(btn_close)
        
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
        
    def check_photo(self):
        if self.main_app_ref: self.main_app_ref.refresh_all_tables()
        self.close()
        
    def upload_manual(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Fotoğraf Seç", "", "Resim (*.png *.jpg *.jpeg)")
        if file_path:
            try:
                with open(file_path, "rb") as file:
                    payload = {"key": IMGBB_API_KEY, "image": base64.b64encode(file.read()).decode('utf-8')}
                    res = requests.post("https://api.imgbb.com/1/upload", data=payload)
                    url = res.json()["data"]["url"]
                
                db_key = "photo_url" if self.photo_index == 1 else f"photo_url_{self.photo_index}"
                if self.main_app_ref: 
                    db.child("users").child(self.user_id).child("kayitlar").child(self.record_id).update({db_key: url}, self.main_app_ref.token)
                    QMessageBox.information(self, "Başarılı", f"Fotoğraf {self.photo_index} ImgBB üzerinden sisteme yüklendi!")
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
        super().__init__(parent); self.setFixedSize(350, 300); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        frame = QWidget(self); frame.setObjectName("DialogFrame"); frame.setStyleSheet(parent.styleSheet() if parent else DARK_THEME)
        layout = QVBoxLayout(frame); self.part_in = QLineEdit(); self.part_in.setPlaceholderText("Parça Adı (Örn: Ekran)"); self.cost_in = QLineEdit(); self.cost_in.setPlaceholderText("Maliyet (Dolar $)"); self.firm_combo = QComboBox(); self.firm_combo.addItems(firmalar)
        btn = QPushButton("Kullanıldı Olarak Kaydet"); btn.clicked.connect(self.accept); layout.addWidget(QLabel("<b>Kullanılan Parça:</b>")); layout.addWidget(self.part_in); layout.addWidget(QLabel("<b>Maliyet (Dolar $, Sadece Rakam):</b>")); layout.addWidget(self.cost_in); layout.addWidget(QLabel("<b>Alındığı Toptancı:</b>")); layout.addWidget(self.firm_combo); layout.addStretch(); layout.addWidget(btn)
        main_layout = QVBoxLayout(self); main_layout.addWidget(frame); main_layout.setContentsMargins(0, 0, 0, 0)
    def get_data(self): return self.part_in.text().strip(), self.cost_in.text().strip(), self.firm_combo.currentText()