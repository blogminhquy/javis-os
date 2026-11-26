@echo off
chcp 65001 >nul
title Javis OS watchdog
REM Restart Javis when /health stops answering. Use: javis-watchdog.bat install | uninstall | check | status
REM Logic lives in javis-watchdog.ps1 (per-user Task Scheduler task, no admin needed).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0javis-watchdog.ps1" %1
