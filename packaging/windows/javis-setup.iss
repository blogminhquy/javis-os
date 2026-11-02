; ============================================================
; JAVIS OS - Windows installer (Inno Setup 6), builds dist\JavisOS-Setup.exe
;
;   iscc /DAppVersion=0.439.0 packaging\windows\javis-setup.iss
;
; CI builds it in .github/workflows/desktop-installers.yml and publishes it on the
; "desktop" release. The .exe stays small: it carries bootstrap.ps1 and the icon only, and
; bootstrap.ps1 clones the newest Javis and runs install.ps1 (see the header of that file
; for why it is a git clone).
;
; Per user, no admin rights asked by the wizard itself (PrivilegesRequired=lowest). Installing
; Git, Python or Node through winget may still show one Windows permission prompt.
;
; This file is UTF-8 WITH BOM: Inno Setup reads a file without BOM in the ANSI codepage, and
; the Vietnamese messages below would turn into garbage.
; ============================================================

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{8F3C2A51-5D7E-4C0B-9E61-6A2D4B7C9E10}
AppName=JAVIS OS
AppVersion={#AppVersion}
AppVerName=JAVIS OS
AppPublisher=Nguyen Minh Quy
AppPublisherURL=https://github.com/blogminhquy/javis-os
AppSupportURL=https://github.com/blogminhquy/javis-os/issues
DefaultDirName={localappdata}\Programs\JAVIS OS
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=JavisOS-Setup
SetupIconFile=..\assets\javis.ico
UninstallDisplayIcon={app}\javis.ico
UninstallDisplayName=JAVIS OS
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=no
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
Name: "vi"; MessagesFile: "Vietnamese.isl"
#endif

[CustomMessages]
en.DesktopIconTask=Put a JAVIS OS icon on the Desktop
en.LaunchNow=Open JAVIS OS now
en.StopApp=Stop JAVIS OS
en.Bootstrapping=Checking this computer and installing what is missing (Git, Python, Node, AI brains). This takes a few minutes, follow the black window...
en.BootstrapFailed=Setup did not finish. The black window said what was missing.%n%nFix it, then run JavisOS-Setup.exe again: steps already done are skipped.%n%nLog: %1
en.DataKept=JAVIS OS was removed from this computer.%n%nYour brain (notes, memory, settings) is kept in:%n%1%n%nDelete that folder by hand if you want everything gone.
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
vi.DesktopIconTask=Đặt biểu tượng JAVIS OS ra Desktop
vi.LaunchNow=Mở JAVIS OS ngay
vi.StopApp=Tắt JAVIS OS
vi.Bootstrapping=Đang kiểm tra máy và cài những gì còn thiếu (Git, Python, Node, các bộ não AI). Mất vài phút, theo dõi ở cửa sổ đen...
vi.BootstrapFailed=Cài đặt chưa xong. Cửa sổ đen đã ghi rõ máy còn thiếu gì.%n%nSửa xong thì chạy lại JavisOS-Setup.exe, các bước đã xong sẽ được bỏ qua.%n%nNhật ký: %1
vi.DataKept=Đã gỡ JAVIS OS khỏi máy.%n%nBộ não của bạn (ghi chú, trí nhớ, cài đặt) vẫn được giữ ở:%n%1%n%nMuốn xoá sạch thì tự xoá thư mục đó.
#endif

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIconTask}"

[Files]
Source: "bootstrap.ps1"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\javis.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; wscript + open-javis.vbs: no console window, and a second click only reopens the window
; instead of restarting the server (see the header of open-javis.vbs).
Name: "{autoprograms}\JAVIS OS"; Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{code:CodeDir}\open-javis.vbs"""; WorkingDir: "{code:CodeDir}"; IconFilename: "{app}\javis.ico"
Name: "{autodesktop}\JAVIS OS"; Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{code:CodeDir}\open-javis.vbs"""; WorkingDir: "{code:CodeDir}"; IconFilename: "{app}\javis.ico"; Tasks: desktopicon
Name: "{autoprograms}\{cm:StopApp}"; Filename: "{code:CodeDir}\stop-javis.bat"; WorkingDir: "{code:CodeDir}"; IconFilename: "{app}\javis.ico"

[Run]
Filename: "{sys}\wscript.exe"; Parameters: "//nologo ""{code:CodeDir}\open-javis.vbs"""; Description: "{cm:LaunchNow}"; Flags: postinstall nowait skipifsilent; Check: BootstrapOk

[UninstallDelete]
Type: files; Name: "{app}\install.log"

[Code]
var
  BootOk: Boolean;

{ Where the git clone (code + the user's brain) lives. Must match the default -Dir of
  bootstrap.ps1. }
function CodeDir(Param: String): String;
begin
  Result := ExpandConstant('{%USERPROFILE}') + '\JavisOS';
end;

function BootstrapOk: Boolean;
begin
  Result := BootOk;
end;

function PowerShellExe: String;
begin
  Result := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
  args, log: String;
begin
  if CurStep = ssPostInstall then
  begin
    WizardForm.StatusLabel.Caption := CustomMessage('Bootstrapping');
    log := ExpandConstant('{app}\install.log');
    args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\bootstrap.ps1') +
            '" -Dir "' + CodeDir('') + '" -LogFile "' + log + '"';
    BootOk := Exec(PowerShellExe, args, '', SW_SHOW, ewWaitUntilTerminated, rc) and (rc = 0);
    if not BootOk then
      SuppressibleMsgBox(FmtMessage(CustomMessage('BootstrapFailed'), [log]), mbError, MB_OK, IDOK);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  rc: Integer;
  stop: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    stop := CodeDir('') + '\stop-javis.ps1';
    if FileExists(stop) then
      Exec(PowerShellExe, '-NoProfile -ExecutionPolicy Bypass -File "' + stop + '"', '', SW_HIDE, ewWaitUntilTerminated, rc);
    { Same entry install.ps1 and the dashboard toggle write (_AUTOSTART_NAME in server/main.py). }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'JavisOS');
  end;
  if CurUninstallStep = usPostUninstall then
    SuppressibleMsgBox(FmtMessage(CustomMessage('DataKept'), [CodeDir('')]), mbInformation, MB_OK, IDOK);
end;
