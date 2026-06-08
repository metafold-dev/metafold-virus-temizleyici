# -*- coding: utf-8 -*-
import requests
from PyQt6.QtCore import QThread, pyqtSignal
from config import safe_float, get_firebase_config
import pyrebase

# Firebase ilklendirmesini buradan yapıyoruz
firebase = pyrebase.initialize_app(get_firebase_config())
auth = firebase.auth()
db = firebase.database()

class FetchRatesThread(QThread):
    rates_fetched = pyqtSignal(float, float)
    def run(self):
        try:
            r = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5).json()
            usd = safe_float(r["rates"]["TRY"], 32.50)
            eur = usd / safe_float(r["rates"]["EUR"], 0.92)
            self.rates_fetched.emit(usd, eur)
        except:
            self.rates_fetched.emit(32.50, 35.00)

class LoadImageThread(QThread):
    image_loaded = pyqtSignal(bytes)
    error_occurred = pyqtSignal()
    def __init__(self, url):
        super().__init__()
        self.url = url
    def run(self):
        try:
            req = requests.get(self.url, timeout=10)
            if req.status_code == 200:
                self.image_loaded.emit(req.content)
            else:
                self.error_occurred.emit()
        except:
            self.error_occurred.emit()

class FirebaseStreamWorker(QThread):
    update_signal = pyqtSignal()
    def __init__(self, user_id, token):
        super().__init__(); self.user_id = user_id; self.token = token; self.stream = None; self.running = True
    def run(self):
        db_url = get_firebase_config().get("databaseURL", "").rstrip("/")
        while self.running:
            try:
                probe = requests.get(
                    f"{db_url}/users/{self.user_id}.json",
                    params={"auth": self.token, "shallow": "true"},
                    timeout=8
                )
                if probe.status_code in [401, 402, 403]:
                    self.msleep(30000)
                    continue
                probe.raise_for_status()
                self.stream = db.child("users").child(self.user_id).stream(self.stream_handler, token=self.token)
                if self.running:
                    self.msleep(3000)
            except requests.exceptions.RequestException:
                self.msleep(30000)
            except Exception:
                self.msleep(10000)
    def stream_handler(self, message):
        if message and message.get('event') in ['put', 'patch']:
            self.update_signal.emit()
    def stop(self):
        self.running = False
        if self.stream: self.stream.close()
