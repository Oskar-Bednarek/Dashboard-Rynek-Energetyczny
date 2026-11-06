@echo off
setlocal
cd /d "%~dp0\.."
python --version >nul 2>&1
if errorlevel 1 (
  echo Na komputerze budujacym paczke wymagany jest Python 3.12 x64.
  echo Odbiorca gotowej paczki nie musi go instalowac.
  pause
  exit /b 1
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1"
if errorlevel 1 (
  echo Budowanie nie powiodlo sie.
) else (
  echo Paczka znajduje sie w folderze dist.
)
pause
endlocal
