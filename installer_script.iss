[Setup]
AppName=IVR 2.5
AppVersion=2.5.0
DefaultDirName={commonpf}\IVR 2.5
DefaultGroupName=IVR 2.5
UninstallDisplayIcon={app}\IVR_2.5.exe
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=IVR_2.5_Setup
SetupIconFile=assets\icon.ico
WizardStyle=modern

[Files]
Source: "dist_final\IVR_2.5.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "cookies\*"; DestDir: "{app}\cookies"; Flags: recursesubdirs createallsubdirs
Source: "jobs\*"; DestDir: "{app}\jobs"; Flags: recursesubdirs createallsubdirs
Source: "meta_accounts\*"; DestDir: "{app}\meta_accounts"; Flags: recursesubdirs createallsubdirs
Source: "gentube_cookies\*"; DestDir: "{app}\gentube_cookies"; Flags: recursesubdirs createallsubdirs
Source: "grok-animator2.0\*"; DestDir: "{app}\grok-animator2.0"; Flags: recursesubdirs createallsubdirs
Source: "whisk_downloads\*"; DestDir: "{app}\whisk_downloads"; Flags: recursesubdirs createallsubdirs
Source: "Build and Instructions\*"; DestDir: "{app}\Build and Instructions"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\IVR 2.5"; Filename: "{app}\IVR_2.5.exe"; IconFilename: "{app}\IVR_2.5.exe"
Name: "{commondesktop}\IVR 2.5"; Filename: "{app}\IVR_2.5.exe"; IconFilename: "{app}\IVR_2.5.exe"

[Run]
Filename: "{app}\IVR_2.5.exe"; Description: "Ejecutar IVR 2.5"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
