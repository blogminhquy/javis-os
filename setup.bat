@echo off
chcp 65001 >nul
title Javis OS
echo.
echo  ==========================================
echo   JAVIS OS
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

REM Cai dependencies
echo [2/4] Kiem tra dependencies...
call .venv\Scripts\activate.bat
pip install -r requirements.txt -q

REM ---- Cac bo nao CLI chay bang GOI DANG DANG NHAP (khong can mua API key) ----
REM Ba engine nay can binary tren may moi hien o trang Models, va trong app KHONG cai ho duoc.
REM Truoc day setup.bat khong cai cai nao - nguoi dung Windows phai tu mo terminal go npm.
REM BEST-EFFORT het: chua co Node thi bo qua, Javis van chay bang cac engine dung API key.
echo [3/4] Kiem tra cac bo nao CLI...
where npm >nul 2>&1
if errorlevel 1 (
  echo     [!] Chua co Node.js nen bo qua buoc nay.
  echo         Muon dung Claude Code / ChatGPT / Gemini CLI: cai Node 22 o nodejs.org roi chay lai file nay.
) else (
  call :cai_cli @anthropic-ai/claude-code claude "Claude Code"
  call :cai_cli @openai/codex codex "Codex - goi ChatGPT"
)

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
