@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
if not exist ".venv\Scripts\python.exe" exit /b 0
.venv\Scripts\python.exe scripts\stop_app.py
if errorlevel 1 pause
