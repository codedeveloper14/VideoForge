[Setup]
AppName=IVR 2.5
AppVersion=2.5.0
DefaultDirName={userpf}\IVR 2.5
DefaultGroupName=IVR 2.5
UninstallDisplayIcon={app}\IVR_2.5.exe
Compression=lzma2
SolidCompression=yes
OutputDir=.
OutputBaseFilename=IVR_2.5_Setup
SetupIconFile=assets\icon.ico
WizardStyle=modern
PrivilegesRequired=lowest

[Files]
Source: "dist_final\IVR_2.5.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "cookies\account_1.txt"; DestDir: "{userappdata}\VideoForge\cookies"; Flags: ignoreversion
Source: ".env"; DestDir: "{userappdata}\VideoForge"; Flags: ignoreversion

[Icons]
Name: "{group}\IVR 2.5"; Filename: "{app}\IVR_2.5.exe"; IconFilename: "{app}\IVR_2.5.exe"
Name: "{userdesktop}\IVR 2.5"; Filename: "{app}\IVR_2.5.exe"; IconFilename: "{app}\IVR_2.5.exe"

[Run]
Filename: "{app}\IVR_2.5.exe"; Description: "Ejecutar IVR 2.5"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"