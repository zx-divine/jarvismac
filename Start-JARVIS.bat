@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\JARVIS\JARVIS.exe" (
  start "" "%~dp0dist\JARVIS\JARVIS.exe"
  exit /b
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo JARVIS needs a Python virtual environment. Run Setup-JARVIS.bat first.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -m jarvis
if errorlevel 1 pause
