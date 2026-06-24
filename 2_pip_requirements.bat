@echo off
setlocal
chcp 65001 >nul 2>&1

set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "REQ=%ROOT%requirements.txt"

if not exist "%VENV%" (
  echo Virtual environment not found: %VENV%
  echo Please run 1_setup_venv.bat first
  exit /b 1
)
call "%VENV%\Scripts\activate.bat"
if errorlevel 1 (
  echo Failed to activate: %VENV%\Scripts\activate.bat
  exit /b 1
)

if exist "%REQ%" (
  echo Installing dependencies from requirements.txt...
  pip install -r "%REQ%"
) else (
  echo requirements.txt not found, installing default packages..
)

if errorlevel 1 (
  echo Dependency installation failed, please check the error messages above
  exit /b 1
)
echo Dependencies installed successfully
