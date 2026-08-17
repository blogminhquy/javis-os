@echo off
chcp 65001 >nul
title Tu khoi dong Javis OS
REM Tu khoi dong Javis cung Windows. Dung: javis-autostart.bat install | uninstall | status
REM Logic nam trong javis-autostart.ps1 (tao/xoa shortcut trong thu muc Startup cua user,
REM khong can quyen admin). Bat roi thi dang nhap may la server tu chay nen.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0javis-autostart.ps1" %1
