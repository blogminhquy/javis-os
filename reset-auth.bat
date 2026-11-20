@echo off
chcp 65001 >nul
title Xoa mat khau Javis
cd /d "%~dp0"
REM Xoa mat khau dang nhap Javis de dat lai tu dau (trang Tai khoan). Logic nam trong tools\reset_auth.py,
REM dung chung voi reset-auth.command cua macOS. Giu setup_done nen khong mo lai bo cai dat lan dau.
if not exist ".venv\Scripts\python.exe" (
  echo Khong thay .venv\Scripts\python.exe - hay cai Javis xong truoc.
  echo .venv\Scripts\python.exe not found - finish installing Javis first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" "tools\reset_auth.py"
echo.
pause
