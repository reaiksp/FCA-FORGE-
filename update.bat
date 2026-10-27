@echo off
setlocal
cd /d "%~dp0"
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo This folder is not a Git checkout. Download the new source release instead.
    pause
    exit /b 1
)
git pull --ff-only
if errorlevel 1 goto failed
if not exist ".venv\Scripts\python.exe" (
    echo Run install.bat first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements-app.lock
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -e . --no-deps
if errorlevel 1 goto failed
echo Update complete. Restart Cover Studio using start.bat.
pause
exit /b 0
:failed
echo Update failed. Existing models and recordings have not been removed.
pause
exit /b 1
