param(
    [string]$Version = "1.0.0",
    [string]$Repo = "metafold-dev/metafold-virus-temizleyici"
)

$ErrorActionPreference = "Stop"

$asset = "dist\MetaFold.Virus.Temizleyici.exe"
if (!(Test-Path $asset)) {
    throw "Release asset bulunamadı: $asset"
}

$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash.ToLower()
$manifest = [ordered]@{
    version = $Version
    url = "https://github.com/$Repo/releases/download/v$Version/MetaFold.Virus.Temizleyici.exe"
    sha256 = $hash
    notes = "OTA destekli sürüm."
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath "update\latest.json" -Encoding UTF8

git add adb_virus_temizleyici.py gui\adb_cleaner.py config.py database gui assets data platform-tools update README_VIRUS_CLEANER.md .gitignore scripts
git commit -m "Release v$Version"
git push -u origin main

gh release create "v$Version" $asset --repo $Repo --title "MetaFold Virüs Temizleyici v$Version" --notes "OTA destekli sürüm."
