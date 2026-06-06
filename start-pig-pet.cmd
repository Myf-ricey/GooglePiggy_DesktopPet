@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0pig_pet.exe" (
  start "" "%~dp0pig_pet.exe"
  exit /b 0
)

where pyw >nul 2>nul
if not errorlevel 1 (
  start "" pyw -3 "%~dp0pig_pet.py"
  exit /b 0
)

where pythonw >nul 2>nul
if not errorlevel 1 (
  start "" pythonw "%~dp0pig_pet.py"
  exit /b 0
)

echo Python was not found. Use the Windows portable release or install Python 3.11+.
pause
