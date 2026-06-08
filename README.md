# MetaFold Virüs Temizleyici

Android reklam virüslerini ADB üzerinden analiz eden ve MetaFold lisans sistemiyle çalışan bağımsız Windows uygulaması.

## Özellikler

- ADB tabanlı cihaz bulma ve uygulama tarama
- Resmi/sistem paketlerini koruyan temizlik akışı
- Tek bilgisayara kilitlenen Virüs Temizleyici lisansı
- Karanlık, Aydınlık, Okyanus, Zümrüt ve Grafit temaları
- TR/EN dil seçimi
- GitHub manifest tabanlı OTA güncelleme desteği

## OTA Güncelleme

Uygulama açılışta şu manifesti kontrol eder:

```text
https://raw.githubusercontent.com/metafold-dev/metafold-virus-temizleyici/main/update/latest.json
```

Manifest formatı:

```json
{
  "version": "1.0.1",
  "url": "https://github.com/metafold-dev/metafold-virus-temizleyici/releases/download/v1.0.1/MetaFold.Virus.Temizleyici.exe",
  "sha256": "EXE_SHA256_DEGERI",
  "notes": "Sürüm notu"
}
```

`version` değeri programdaki `APP_VERSION` değerinden büyükse EXE indirilir, SHA256 doğrulanır ve program kendini yenileyip yeniden başlatır.

## Build

```powershell
python -m PyInstaller --clean --noconsole --onefile `
  --name "MetaFold Virüs Temizleyici" `
  --icon assets\metafold_virus_logo_transparent.ico `
  --add-data "assets\metafold_virus_logo_transparent.png;assets" `
  --add-data "assets\metafold_virus_logo_dark.png;assets" `
  --add-data "data\android_risk_db.json;data" `
  --add-data "platform-tools;platform-tools" `
  adb_virus_temizleyici.py
```
