@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Run Setup-JARVIS.bat first.
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe -m pytest -q
if errorlevel 1 exit /b 1
if not exist models\vosk-model-small-en-us-0.15 (
  .venv\Scripts\python.exe scripts\download_voice_model.py
  if errorlevel 1 exit /b 1
)
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir --name JARVIS --collect-all vosk --add-data "models\vosk-model-small-en-us-0.15;models\vosk-model-small-en-us-0.15" run_jarvis.py
if errorlevel 1 exit /b 1
echo Built dist\JARVIS\JARVIS.exe. Copy the entire JARVIS folder, not only the executable.
