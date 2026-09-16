@echo off
chcp 65001 >nul
title Javis OS
echo.
echo  ==========================================
echo   JAVIS OS
echo  ==========================================
echo   Muon cai MOT LUOT ca 4 bo nao CLI
echo   (claude, codex, agy, grok) thi chay:
echo     powershell -ExecutionPolicy Bypass -File install.ps1
echo  ==========================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
  echo [LOI] Python chua cai. Tai tai python.org roi tick "Add to PATH".
  echo.
  pause
  exit /b 1
)

REM Tao venv neu chua co
if not exist ".venv" (
  echo [1/4] Tao virtual environment...
  python -m venv .venv
)

REM Cai dependencies. KIEM MA LOI: pip hong ma di tiep thi server bat len roi moi chet vi
REM thieu claude-agent-sdk, va nguoi dung doc duoc mot loi "thieu SDK" o tan man dang nhap
REM chu khong biet goc benh nam o buoc cai nay (loi that, Windows 16/09).
echo [2/4] Kiem tra dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q
if errorlevel 1 (
  echo.
  echo  [LOI] Cai thu vien Python THAT BAI - Javis se thieu claude-agent-sdk va khong chay duoc.
  echo        Chay tay de doc loi day du:
  echo          .venv\Scripts\python.exe -m pip install -r requirements.txt
  echo.
  pause
  exit /b 1
)

REM ---- BON bo nao CLI chay bang GOI DANG DANG NHAP (khong can mua API key) ----
REM Bon engine nay can binary tren may moi hien o trang Models, va trong app KHONG cai ho duoc.
REM Hai cai dau cai bang npm, hai cai sau bang script cua nha cung cap.
REM BEST-EFFORT het: chua co Node thi bo qua hai cai dau, Javis van chay bang engine dung API key.
echo [3/4] Kiem tra cac bo nao CLI...
where npm >nul 2>&1
if errorlevel 1 (
  echo     [!] Chua co Node.js nen bo qua buoc nay.
  echo         Muon dung Claude Code hay Codex: cai Node LTS o nodejs.org roi chay lai file nay.
) else (
  call :cai_cli @anthropic-ai/claude-code claude "Claude Code"
  call :cai_cli @openai/codex codex "Codex - goi ChatGPT"
)
REM Hai engine con lai KHONG cai bang npm: moi nha mot script rieng. Best-effort, va KHONG
REM bao "cai hong" khi khong thay binary - PATH cua cua so cmd nay khong tu cap nhat sau khi
REM script cai ghi vao registry, nen "chua thay" o day khong co nghia la chua cai duoc.
call :cai_script agy "Antigravity CLI cua Google" https://antigravity.google/cli/install.ps1
call :cai_script grok "Grok Build cua xAI" https://x.ai/cli/install.ps1

REM Giai phong port 7777 neu dang bi chiem
echo [4/4] Giai phong port 7777...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7777" ^| findstr "LISTENING"') do (
  echo     Dang tat tien trinh cu PID %%a
  taskkill /F /PID %%a >nul 2>&1
)

echo.
echo  ==========================================
echo   Javis OS dang chay tai: http://localhost:7777
echo   (Chon bo nao o trang Models - khong bat buoc mua API key)
echo   Nhan Ctrl+C de dung.
echo  ==========================================
echo.

cd server
python main.py

REM Neu python thoat (loi), giu cua so de doc loi
echo.
echo  [!] Server da dung. Xem loi o tren (neu co).
pause
exit /b 0

REM ============================ Ham phu ============================
REM %1 = goi npm, %2 = ten binary, %3 = ten hien thi. Da co thi bo qua, hong thi chi bao mot
REM dong roi di tiep - mot engine cai hong khong duoc chan ca lan cai.
REM LUU Y khi them dong goi moi: ten hien thi KHONG duoc chua dau ngoac don. No bi echo ben
REM trong khoi if(...) duoi day, ma batch bung %~3 luc phan tich khoi, nen mot dau ')' trong
REM ten se dong khoi som va lam hong ca ham.
:cai_cli
where %2 >nul 2>&1
if not errorlevel 1 (
  echo     - %~3: da co san
  goto :eof
)
echo     - %~3: dang cai (npm install -g %1)...
call npm install -g %1 >nul 2>&1
if errorlevel 1 (
  echo       [!] Chua cai duoc. Cai tay khi ranh: npm install -g %1
) else (
  echo       OK
)
goto :eof

REM %1 = ten binary, %2 = ten hien thi, %3 = URL script cai cua nha cung cap.
REM Cung luat dat ten nhu :cai_cli - ten hien thi KHONG duoc chua dau ngoac don.
:cai_script
where %1 >nul 2>&1
if not errorlevel 1 (
  echo     - %~2: da co san
  goto :eof
)
echo     - %~2: dang cai tu %3 ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { irm %3 -UseBasicParsing | iex } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  echo       [!] Chua cai duoc. Cai tay: irm %3 ^| iex
) else (
  echo       Da chay script cai. Neu trang Models van bao chua cai thi khoi dong lai Javis.
)
goto :eof
