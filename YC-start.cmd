@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"

echo === YCore CLI Launcher ===
echo.

if not exist "%PYTHON%" (
    echo Python virtual environment was not found:
    echo   %PYTHON%
    echo.
    echo Run these commands from the project root:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo Starting YCore CLI.
echo.
cd /d "%ROOT%" || exit /b 1
"%PYTHON%" main.py
exit /b %ERRORLEVEL%
