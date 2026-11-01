
; Script do Inno Setup para o HexSound
; Gera: HexSoundSetup.exe (na mesma pasta do projeto)
; Pre-requisito: ter gerado dist\HexSound com o build_exe.bat

#define MyAppName "HexSound"
#define MyAppVersion "1.0.1"
#define MyAppExeName "HexSound.exe"

[Setup]
AppId={{0A271EAC-9529-420A-833D-969399758A67}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=.
OutputBaseFilename=HexSoundSetup
SetupIconFile=assets\installer_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Instala so para o usuario atual: nao pede senha de administrador
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Area de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\HexSound\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir o {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Remove a inicializacao automatica com o Windows, se o usuario tiver ativado no app
Filename: "reg.exe"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v HexSound /f"; Flags: runhidden; RunOnceId: "RemoveAutostart"
