@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3.11 -m venv .venv
  if errorlevel 1 (
    echo Install Python 3.11 or newer from python.org, including the Python launcher.
    echo For another installed version run: py -3.12 -m venv .venv
    pause
    exit /b 1
  )
)
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your connection and Python version.
  pause
  exit /b 1
)
if not exist models\vosk-model-small-en-us-0.15 (
  .venv\Scripts\python.exe scripts\download_voice_model.py
  if errorlevel 1 echo Offline model download failed. Manual Wake still works; retry scripts\download_voice_model.py later.
)
echo Setup complete. Start with Start-JARVIS.bat.
pause
