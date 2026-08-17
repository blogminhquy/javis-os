@echo off
chcp 65001 >nul
title JAVIS OS
cd /d "%~dp0"

REM ============================================================
REM  JAVIS OS - mo nhu mot app tren Windows (ban sao cua "JAVIS OS.app" ben Mac).
REM  Double-click: server tu chay nen (khong cua so den) roi dashboard tu mo
REM  thanh CUA SO RIENG (Edge/Chrome che do --app: khong thanh dia chi, co o
REM  rieng tren taskbar). Tu khoi dong cung may: javis-autostart.bat install.
REM ============================================================

if "%JAVIS_PORT%"=="" set JAVIS_PORT=7777
set "URL=http://127.0.0.1:%JAVIS_PORT%"

REM Server dang chay roi thi KHONG khoi dong lai (start-javis.vbs se kill instance
REM cu truoc - double-click lan hai ma restart thi mat het viec dang chay do).
REM Chi mo cua so.
curl -sf -m 2 -o nul %URL%/health 2>nul
if %errorlevel%==0 goto :open

echo Dang bat Javis OS (chay nen, log o server\javis.log)...
wscript //nologo start-javis.vbs

REM Cho server len (toi da ~45 giay) roi moi mo - mo som chi thay trang trang.
REM May thieu curl (Windows cu): khong tham do duoc thi cho 8 giay roi mo dai.
where curl >nul 2>&1
if not %errorlevel%==0 (
  timeout /t 8 >nul
  goto :open
)
set /a _thu=0
:wait
set /a _thu+=1
if %_thu% gtr 45 goto :open
timeout /t 1 >nul
curl -sf -m 2 -o nul %URL%/health 2>nul
if not %errorlevel%==0 goto :wait

:open
REM Uu tien cua so app (khong thanh dia chi). Edge co san tren moi Windows 10/11;
REM khong thay thi thu Chrome; cung khong co thi mo trinh duyet mac dinh.
set "EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" ( start "" "%EDGE%" --app=%URL% & goto :eof )
set "EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if exist "%EDGE%" ( start "" "%EDGE%" --app=%URL% & goto :eof )
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" ( start "" "%CHROME%" --app=%URL% & goto :eof )
set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"
if exist "%CHROME%" ( start "" "%CHROME%" --app=%URL% & goto :eof )
start "" %URL%
