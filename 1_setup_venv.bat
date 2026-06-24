@echo off
setlocal
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"

echo [1/2] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
  echo ❌ Python not detected, please install Python and try again.
  exit /b 1
)

if not exist "%VENV%" (
  echo [2/2] Creating virtual environment: %VENV%
  python -m venv "%VENV%"
  if errorlevel 1 (
    echo ❌ Virtual environment creation failed, please ensure Python is properly installed.
    exit /b 1
  )
)

echo ✅ Virtual environment ready: %VENV%
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
  echo ❌ Activation failed: %VENV%\Scripts\activate.bat
  exit /b 1
)
echo Virtual environment activated
echo Current directory: %CD%
echo Tip: Run 2_pip_requirements.bat to install project dependencies