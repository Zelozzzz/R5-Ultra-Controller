; Inno Setup script for Dorsal's installer.
; Build dist\Dorsal first (python packaging\build.py), then:
;     iscc /DAppVersion=1.5 packaging\installer.iss
; GitHub Actions does this on every release tag.

#define AppName "Dorsal"
#ifndef AppVersion
  #define AppVersion "1.5"
#endif
#ifndef BuildDist
  #define BuildDist "..\dist"
#endif

[Setup]
; A fixed id lets new versions install over old ones and share one uninstaller.
AppId={{6D1F2B7A-3C4E-4A9B-8E21-5F0D9C7A4B13}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Zelozzzz
AppPublisherURL=https://github.com/Zelozzzz/R5-Ultra-Controller
AppSupportURL=https://github.com/Zelozzzz/R5-Ultra-Controller/issues
; Per-user install: no admin prompt. Users can still choose "all users".
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
OutputDir={#BuildDist}
OutputBaseFilename=Dorsal-Setup-{#AppVersion}
SetupIconFile=..\build\packaging\dorsal.ico
UninstallDisplayIcon={app}\Dorsal.exe
LicenseFile=..\LICENSE
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Dorsal holds this mutex while running, so Setup can ask to close it first.
AppMutex=Dorsal.SingleInstance
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Dorsal with Windows (hidden in the tray)"; Flags: unchecked

[Files]
Source: "{#BuildDist}\Dorsal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Dorsal.exe"; WorkingDir: "{app}"; Comment: "Attack Shark R5 Ultra mouse control"; AppUserModelID: "Dorsal.App"
Name: "{autoprograms}\Attack Shark R5 Ultra - Dorsal"; Filename: "{app}\Dorsal.exe"; WorkingDir: "{app}"; Comment: "Open Dorsal to control your Attack Shark R5 Ultra"; AppUserModelID: "Dorsal.App"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\Dorsal.exe"; WorkingDir: "{app}"; AppUserModelID: "Dorsal.App"; Tasks: desktopicon

[Registry]
; Register a normal application executable without changing the user's PATH.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\Dorsal.exe"; ValueType: string; ValueName: ""; ValueData: "{app}\Dorsal.exe"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\App Paths\Dorsal.exe"; ValueType: string; ValueName: "Path"; ValueData: "{app}"
; Same entry the app's own "Run on Windows startup" switch manages.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Dorsal"; ValueData: """{app}\Dorsal.exe"" --tray"; Flags: uninsdeletevalue; Tasks: startup
; Remove it on uninstall even if it was switched on from inside the app.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Dorsal"; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Dorsal.exe"; Description: "Launch Dorsal"; Flags: nowait postinstall skipifsilent
