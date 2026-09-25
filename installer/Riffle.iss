; 버전은 릴리스 워크플로가 깃 태그에서 정해 /DAppVersion 으로 넘긴다.
; 아래 값은 그것 없이 수동 실행했을 때만 쓰이며, 진짜 버전이 아님이 드러나야 한다.
#ifndef AppVersion
  #define AppVersion "0.0.0-manual"
#endif

[Setup]
AppId={{D312FDF1-64A3-4985-AAB2-4FA95A24F8B0}
AppName=Riffle
AppVersion={#AppVersion}
AppPublisher=Riffle
DefaultDirName={autopf}\Riffle
DefaultGroupName=Riffle
OutputDir=..\release
OutputBaseFilename=Riffle-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\Riffle.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\Riffle\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Riffle"; Filename: "{app}\Riffle.exe"
Name: "{autodesktop}\Riffle"; Filename: "{app}\Riffle.exe"; Tasks: desktopicon

[InstallDelete]
; 로컬 웹 판은 2026-09-26 걷었다 — 예전 설치가 남긴 실행 파일과 바로가기를 지운다.
Type: files; Name: "{app}\RiffleLocalWeb.exe"
Type: files; Name: "{autoprograms}\Riffle 로컬 웹.lnk"
Type: files; Name: "{autodesktop}\Riffle 로컬 웹.lnk"

[Tasks]
Name: "desktopicon"; Description: "바탕화면 바로가기 만들기"; GroupDescription: "추가 바로가기:"; Flags: checkedonce

[Run]
Filename: "{app}\Riffle.exe"; Description: "Riffle 실행"; Flags: nowait postinstall skipifsilent
