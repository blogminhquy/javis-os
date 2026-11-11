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
; No black window: bootstrap.ps1 runs hidden and every line it prints shows up in a box on the
; Installing page (ExecAndLogOutput, Inno Setup 6.3 or newer), under a moving progress bar and
; a "Step 2 of 5" line. The separate console used to hide behind the wizard, wait there for
; Enter after an error, or freeze when clicked, and the wizard then looked stuck for good.
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
; Javis logo in the wizard (packaging/make_icons.py draws them): the tall panel on the first and
; last page, the corner logo on the pages between. One file per display scale, Inno picks the
; closest, so the logo stays sharp on a 150% or 200% laptop screen.
WizardImageFile=..\assets\wizard-100.bmp,..\assets\wizard-125.bmp,..\assets\wizard-150.bmp,..\assets\wizard-175.bmp,..\assets\wizard-200.bmp,..\assets\wizard-225.bmp,..\assets\wizard-250.bmp
WizardSmallImageFile=..\assets\wizard-small-100.bmp,..\assets\wizard-small-125.bmp,..\assets\wizard-small-150.bmp,..\assets\wizard-small-175.bmp,..\assets\wizard-small-200.bmp,..\assets\wizard-small-225.bmp,..\assets\wizard-small-250.bmp
WizardImageStretch=no
VersionInfoCompany=Nguyen Minh Quy
VersionInfoDescription=JAVIS OS Setup
VersionInfoProductName=JAVIS OS
VersionInfoVersion={#AppVersion}
; Code signing, only when CI has a certificate (desktop-installers.yml passes /DSign and the
; matching /Sjavis=... command). Without it the build stays unsigned, exactly as before.
#ifdef Sign
SignTool=javis
SignedUninstaller=yes
#endif

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
Name: "vi"; MessagesFile: "Vietnamese.isl"
#endif

[CustomMessages]
en.DesktopIconTask=Put a JAVIS OS icon on the Desktop
en.LaunchNow=Open JAVIS OS now
en.StopApp=Stop JAVIS OS
en.Bootstrapping=Checking this computer and installing what is missing. This takes a few minutes.
en.StepGit=Step 1 of 5: checking Git
en.StepClone=Step 2 of 5: downloading Javis
en.StepPython=Step 3 of 5: checking Python
en.StepLibs=Step 4 of 5: installing Python libraries (the longest step)
en.StepBrains=Step 5 of 5: installing the AI brains (Claude Code, Codex, Antigravity, Grok)
en.StepFinish=Almost done: finishing up
en.BootstrapFailed=Setup did not finish:%n%n%1%n%nFix it, then run JavisOS-Setup.exe again: steps already done are skipped.%n%nFull log: %2
en.BootstrapNoDetail=One of the install steps reported an error.
en.NotFinishedTitle=JAVIS OS is not installed yet
en.NotFinishedText=One install step did not finish. Run JavisOS-Setup.exe again: steps already done are skipped.%n%nLog: %1
en.DataKept=JAVIS OS was removed from this computer.%n%nYour brain (notes, memory, settings) is kept in:%n%1%n%nDelete that folder by hand if you want everything gone.
#if FileExists(AddBackslash(SourcePath) + "Vietnamese.isl")
vi.DesktopIconTask=Đặt biểu tượng JAVIS OS ra Desktop
vi.LaunchNow=Mở JAVIS OS ngay
vi.StopApp=Tắt JAVIS OS
vi.Bootstrapping=Đang kiểm tra máy và cài những gì còn thiếu. Việc này mất vài phút.
vi.StepGit=Bước 1/5: kiểm tra Git
vi.StepClone=Bước 2/5: tải Javis về máy
vi.StepPython=Bước 3/5: kiểm tra Python
vi.StepLibs=Bước 4/5: cài thư viện Python (bước lâu nhất)
vi.StepBrains=Bước 5/5: cài các bộ não AI (Claude Code, Codex, Antigravity, Grok)
vi.StepFinish=Sắp xong: hoàn tất cài đặt
vi.BootstrapFailed=Cài đặt chưa xong:%n%n%1%n%nSửa xong thì chạy lại JavisOS-Setup.exe, các bước đã xong sẽ được bỏ qua.%n%nNhật ký đầy đủ: %2
vi.BootstrapNoDetail=Một bước cài đặt báo lỗi.
vi.NotFinishedTitle=JAVIS OS chưa cài xong
vi.NotFinishedText=Có một bước cài chưa xong. Chạy lại JavisOS-Setup.exe, các bước đã xong sẽ được bỏ qua.%n%nNhật ký: %1
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
const
  WM_VSCROLL = $0115;
  SB_BOTTOM = 7;

var
  BootOk: Boolean;
  BootMemo: TNewMemo;       { live output of bootstrap.ps1, on the Installing page }
  BootLogFile: String;      { the same lines on disk, for the error message and for support }
  BootLastError: String;    { last "[LOI] ..." line, quoted in the failure message }

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

{ The box that replaces the black window: under the progress bar, in the empty lower half of
  the Installing page. Hidden while Setup copies its own files, shown when bootstrap starts. }
procedure InitializeWizard;
begin
  BootMemo := TNewMemo.Create(WizardForm);
  BootMemo.Parent := WizardForm.InstallingPage;
  BootMemo.Left := WizardForm.ProgressGauge.Left;
  BootMemo.Top := WizardForm.ProgressGauge.Top + WizardForm.ProgressGauge.Height + ScaleY(12);
  BootMemo.Width := WizardForm.ProgressGauge.Width;
  BootMemo.Height := WizardForm.InnerNotebook.Height - BootMemo.Top;
  BootMemo.Anchors := [akLeft, akTop, akRight, akBottom];
  BootMemo.ScrollBars := ssVertical;
  BootMemo.ReadOnly := True;
  BootMemo.WordWrap := True;
  BootMemo.Font.Name := 'Consolas';
  BootMemo.Visible := False;
end;

{ bootstrap.ps1 and install.ps1 open each step with "[A] ...", "[1] ...". The wizard turns the
  marker into a line in the person's own language; the raw line still goes into the box. }
function StepCaption(const U: String): String;
begin
  Result := '';
  if Pos('[A]', U) = 1 then Result := CustomMessage('StepGit')
  else if Pos('[B]', U) = 1 then Result := CustomMessage('StepClone')
  else if Pos('[1]', U) = 1 then Result := CustomMessage('StepPython')
  else if Pos('[2]', U) = 1 then Result := CustomMessage('StepLibs')
  else if Pos('[3]', U) = 1 then Result := CustomMessage('StepBrains')
  else if (Pos('[4]', U) = 1) or (Pos('[5]', U) = 1) then Result := CustomMessage('StepFinish');
end;

{ Called by ExecAndLogOutput for every line the hidden bootstrap prints. }
procedure BootLine(const S: String; const Error, FirstLine: Boolean);
var
  T, U, Cap: String;
  A: TArrayOfString;
begin
  T := TrimRight(S);
  if (Length(T) > 0) and (Ord(T[1]) = $FEFF) then
    Delete(T, 1, 1);
  SetArrayLength(A, 1);
  A[0] := T;
  SaveStringsToUTF8File(BootLogFile, A, True);
  U := Trim(T);
  if U = '' then
    Exit;
  BootMemo.Lines.Add(T);
  SendMessage(BootMemo.Handle, WM_VSCROLL, SB_BOTTOM, 0);
  if Pos('[LOI]', U) = 1 then
    BootLastError := Trim(Copy(U, 6, Length(U)));
  Cap := StepCaption(U);
  if Cap <> '' then
    WizardForm.StatusLabel.Caption := Cap;
  WizardForm.FilenameLabel.Caption := U;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  rc: Integer;
  args, why: String;
  ran: Boolean;
begin
  if CurStep = ssPostInstall then
  begin
    BootLogFile := ExpandConstant('{app}\install.log');
    DeleteFile(BootLogFile);
    BootLastError := '';
    WizardForm.StatusLabel.Caption := CustomMessage('Bootstrapping');
    WizardForm.FilenameLabel.Caption := '';
    { Setup's own files are copied by now, so the bar would sit at 100% for minutes and look
      frozen. A moving bar says "still working". }
    WizardForm.ProgressGauge.Style := npbstMarquee;
    BootMemo.Lines.Clear;
    BootMemo.Visible := True;
    { -NoPause: nobody can press Enter in a hidden console. }
    args := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\bootstrap.ps1') +
            '" -Dir "' + CodeDir('') + '" -NoPause';
    rc := -1;
    try
      ran := ExecAndLogOutput(PowerShellExe, args, '', SW_SHOWNORMAL, ewWaitUntilTerminated, rc, @BootLine);
    except
      { Output redirection could not be set up (very rare): run it the old way, in its own
        window, so the install still happens. }
      Log(GetExceptionMessage);
      ran := Exec(PowerShellExe, args + ' -LogFile "' + BootLogFile + '"', '', SW_SHOW, ewWaitUntilTerminated, rc);
    end;
    BootOk := ran and (rc = 0);
    WizardForm.ProgressGauge.Style := npbstNormal;
    WizardForm.FilenameLabel.Caption := '';
    if not BootOk then
    begin
      why := BootLastError;
      if why = '' then
        why := CustomMessage('BootstrapNoDetail');
      SuppressibleMsgBox(FmtMessage(CustomMessage('BootstrapFailed'), [why, BootLogFile]), mbError, MB_OK, IDOK);
    end;
  end;
end;

{ The last page must not say "Setup has finished installing" after a failed bootstrap. }
procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and (not BootOk) then
  begin
    WizardForm.FinishedHeadingLabel.Caption := CustomMessage('NotFinishedTitle');
    WizardForm.FinishedLabel.Caption := FmtMessage(CustomMessage('NotFinishedText'), [BootLogFile]);
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
