; Instalador de Windows para Studio IVR (VideoForge).
; Requiere: dist\StudioIVR\ ya generado (pyarmor gen + PyInstaller con studioivr.spec).
; Compilar con: "C:\Users\igaby\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer_windows.iss

#define MyAppName "Studio IVR"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Studio IVR"
#define MyAppExeName "StudioIVR.exe"
; Icono de PRUEBA -- el mismo diseno que se ve hoy en el puerto 8080 (favicon.svg),
; recreado como .ico porque Windows no acepta SVG para iconos de exe/instalador.
; Cambiar a assets\icon.ico (el oficial) cuando se confirme como se ve este primero.
#define MyAppIcon "assets\icon_test_8080.ico"

[Setup]
AppId={{B4B6B6D2-9C1E-4A3D-8F2E-VIDEOFORGE01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=StudioIVR-Setup-{#MyAppVersion}
SetupIconFile={#MyAppIcon}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\StudioIVR\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
// WebView2 se necesita para la ventana nativa (pywebview/EdgeChromium). Windows 11
// lo trae de fabrica; Windows 10 lo recibe por Windows Update pero no esta
// garantizado en toda instalacion. Sin esto la app sigue funcionando (cae a abrir
// el navegador normal, ver desktop/window.py), pero instalarlo de entrada evita esa
// degradacion y da la experiencia de ventana nativa real desde el primer arranque.
function IsWebView2Installed(): Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version);
end;

procedure InstallWebView2();
var
  ResultCode: Integer;
  BootstrapperPath: String;
  CurlPath: String;
begin
  // Sin plugins de terceros (Inno Setup base no trae descarga HTTP en Pascal
  // Script) -- se usa curl.exe, incluido de fabrica en Windows 10 1803+ y
  // Windows 11, para bajar el bootstrapper real de Microsoft (~1.5MB, no el
  // runtime completo) y correrlo en silencio.
  BootstrapperPath := ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe');
  CurlPath := ExpandConstant('{sys}\curl.exe');
  if not FileExists(CurlPath) then
    Exit; // Windows muy viejo sin curl -- se deja que la app caiga a su fallback de navegador
  Exec(CurlPath,
    '-L -s -o "' + BootstrapperPath + '" "https://go.microsoft.com/fwlink/p/?LinkId=2124703"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  if not FileExists(BootstrapperPath) then
    Exit;
  Exec(BootstrapperPath, '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if not IsWebView2Installed() then
    begin
      WizardForm.StatusLabel.Caption := 'Instalando Microsoft Edge WebView2 Runtime...';
      InstallWebView2();
    end;
  end;
end;
