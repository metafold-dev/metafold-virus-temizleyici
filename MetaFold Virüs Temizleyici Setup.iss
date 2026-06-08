#define MyAppName "MetaFold Virüs Temizleyici"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "MetaFold"
#define MyAppURL "https://www.metafold.net"
#define MyAppExeName "MetaFold Virüs Temizleyici.exe"
#define SourceRoot "C:\Users\Acer\Desktop\MetaFold_Servis"

[Setup]
AppId={{7C3D3E2A-A8B8-4E69-91B0-4FE6E9BCF771}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
DisableProgramGroupPage=yes
OutputDir={#SourceRoot}\dist
OutputBaseFilename=MetaFold_Virus_Temizleyici_Setup_v{#MyAppVersion}
SetupIconFile={#SourceRoot}\assets\metafold_virus_logo_transparent.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}
RestartApplications=no
AppMutex=MetaFoldVirusCleanerStandalone

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Messages]
SetupAppRunningError=MetaFold Virüs Temizleyici şu anda açık.%n%nKuruluma devam etmek için programı kapatıp tekrar deneyin.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce
Name: "adbdriver"; Description: "ADB USB sürücüsünü kur"; GroupDescription: "Android bağlantısı:"; Flags: unchecked

[Files]
Source: "{#SourceRoot}\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceRoot}\platform-tools\*"; DestDir: "{app}\platform-tools"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourceRoot}\data\android_risk_db.json"; DestDir: "{app}\data"; Flags: ignoreversion
Source: "{#SourceRoot}\assets\metafold_virus_logo_transparent.png"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "{#SourceRoot}\assets\metafold_virus_logo_transparent.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "{#SourceRoot}\vendor\google-usb-driver\usb_driver\*"; DestDir: "{app}\drivers\google-usb-driver"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\MetaFold_Virus_Temizleyici_Setup_v*.exe"
Type: files; Name: "{app}\MetaFold Virüs Temizleyici*.old"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\pnputil.exe"; Parameters: "/add-driver ""{app}\drivers\google-usb-driver\android_winusb.inf"" /install"; StatusMsg: "ADB USB sürücüsü kuruluyor..."; Flags: runhidden waituntilterminated; Tasks: adbdriver
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
