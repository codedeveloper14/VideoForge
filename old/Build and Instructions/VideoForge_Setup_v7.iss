; ══════════════════════════════════════════════════════════════════
;  VideoForge — Instalador para Windows v7 (con icono)
;  Generado para Inno Setup 6.x
; ══════════════════════════════════════════════════════════════════

#define AppName      "VideoForge"
#define AppVersion   "2.2"
#define AppPublisher "David Estaban Bermudez"
#define AppURL       "https://github.com/codedeveloper14/VideoForge"
#define AppExeName   "VideoForge.exe"
#define BuildDir     "dist\VideoForge"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
OutputDir=installer_output
OutputBaseFilename=VideoForge_Setup_{#AppVersion}
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
MinVersion=10.0

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el &Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked
Name: "startupicon"; Description: "Iniciar VideoForge al arrancar Windows"; GroupDescription: "Opciones:"; Flags: unchecked

[Files]
; ── Ejecutable principal ───────────────────────────────────────
Source: "{#BuildDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; ── Carpeta _internal de PyInstaller ──────────────────────────
Source: "{#BuildDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── FFmpeg y FFprobe ───────────────────────────────────────────
Source: "ffmpeg.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "ffprobe.exe"; DestDir: "{app}"; Flags: ignoreversion

; ── VideoForgeUpdater ──────────────────────────────────────────
Source: "VideoForgeUpdater.exe"; DestDir: "{app}"; Flags: ignoreversion

; ── Icono ──────────────────────────────────────────────────────
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; ── Visual C++ Redistributable ────────────────────────────────
Source: "vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

; ── Python 3.13 ───────────────────────────────────────────────
Source: "python-3.13.1-amd64.exe"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

; ── Script de instalación de dependencias ─────────────────────
Source: "install_deps.bat"; DestDir: "{tmp}"; Flags: ignoreversion deleteafterinstall

[Dirs]
Name: "{app}\grok-animator2.0"; Flags: uninsneveruninstall
Name: "{app}\grok-animator2.0\accounts"; Flags: uninsneveruninstall
Name: "{app}\grok-animator2.0\downloads"; Flags: uninsneveruninstall

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: startupicon

[Registry]
Root: HKCU; Subkey: "Environment"; \
  ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}"; \
  Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; 0. Instalar Visual C++ Redistributable
Filename: "{tmp}\vc_redist.x64.exe"; Parameters: "/install /quiet /norestart"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Instalando componentes del sistema..."

; 1. Instalar Python 3.13 si no está
Filename: "{tmp}\python-3.13.1-amd64.exe"; \
  Parameters: "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Instalando Python 3.13..."; \
  Check: not IsPython313Installed()

; 2. Instalar dependencias
Filename: "cmd.exe"; Parameters: "/c ""{tmp}\install_deps.bat"""; \
  Flags: runhidden waituntilterminated; StatusMsg: "Instalando componentes de IA (varios minutos)..."

; 3. Abrir la app al terminar
Filename: "{app}\{#AppExeName}"; Description: "Iniciar {#AppName} ahora"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Type: filesandordirs; Name: "{app}\jobs"

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

function IsPython313Installed(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(ExpandConstant('{localappdata}\Programs\Python\Python313\python.exe'),
            '--version', '', SW_HIDE, ewWaitUntilTerminated, ResultCode)
            and (ResultCode = 0);
end;

procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Caption :=
    'Este instalador configurará VideoForge en su equipo.' + #13#10 + #13#10 +
    'Se instalarán automáticamente:' + #13#10 +
    '  • Python 3.13' + #13#10 +
    '  • Componentes de IA (torch, whisper)' + #13#10 +
    '  • Navegador integrado (Chromium)' + #13#10 + #13#10 +
    'Este proceso puede tardar varios minutos.' + #13#10 + #13#10 +
    'Haga clic en Siguiente para continuar.';
end;
