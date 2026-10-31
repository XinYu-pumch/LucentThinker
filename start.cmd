@echo off
setlocal
cd /d "%~dp0"
set "UV_CACHE_DIR=%CD%\.cache\uv"
set "UV_PYTHON_INSTALL_DIR=%CD%\.runtime\python"
set "PYTHONUTF8=1"
set "TIKTOKEN_CACHE_DIR=%CD%\.cache\tiktoken"
where uv >nul 2>nul
if errorlevel 1 (
  echo Install uv first from https://docs.astral.sh/uv/getting-started/installation/
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  uv sync --frozen --python 3.12
  if errorlevel 1 exit /b 1
)
for /f %%P in ('.venv\Scripts\python.exe -c "from dotenv import dotenv_values; print(dotenv_values('.env').get('PORT') or '8765')"') do set "LUCENT_PORT=%%P"
.venv\Scripts\python.exe scripts\launch.py --port %LUCENT_PORT% --open %*
if errorlevel 1 pause
