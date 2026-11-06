@echo off
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
if not exist "runtime\python.exe" (
  echo Brakuje plikow aplikacji. Najpierw rozpakuj cala paczke ZIP.
  pause
  exit /b 1
)
"runtime\python.exe" "launcher.py"
if errorlevel 1 pause
endlocal
