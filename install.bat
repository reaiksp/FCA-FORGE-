@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -All
if errorlevel 1 (
    echo Installation failed. See the error above.
    pause
    exit /b 1
)
pause
