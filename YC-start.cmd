@echo off
setlocal

if /i "%~1"=="--electron" goto run_electron

set "ROOT=%~dp0"
set "DESKTOP=%ROOT%desktop"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "LOG_DIR=%ROOT%outputs"
set "ELECTRON_LOG=%LOG_DIR%\desktop-electron.log"

echo === YCore Desktop Launcher ===
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

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo npm.cmd was not found. Please install Node.js first.
    echo.
    pause
    exit /b 1
)

if not exist "%DESKTOP%\node_modules" (
    echo Desktop dependencies were not found:
    echo   %DESKTOP%\node_modules
    echo.
    echo Run these commands:
    echo   cd /d "%DESKTOP%"
    echo   npm.cmd install
    echo.
    pause
    exit /b 1
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [1/3] Checking Python dependencies...
"%PYTHON%" -c "import fastapi, uvicorn, numpy, rank_bm25, pypdf" >nul 2>nul
if errorlevel 1 (
    echo Python dependencies are incomplete.
    echo.
    echo Run this command from the project root:
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo [2/3] Starting Electron desktop app...
echo Electron log: %ELECTRON_LOG%
start "YCore Desktop" "%ComSpec%" /k call "%~f0" --electron "%DESKTOP%" "%ELECTRON_LOG%"

echo [3/3] YCore desktop is launching.
echo Keep the YCore Desktop command window open while using the app.
echo If the desktop window does not appear, check:
echo   %ELECTRON_LOG%
echo.

endlocal
exit /b 0

:run_electron
set "DESKTOP=%~2"
set "ELECTRON_LOG=%~3"
echo Starting YCore Electron desktop app.
echo Output is also written to:
echo   %ELECTRON_LOG%
echo.
cd /d "%DESKTOP%" || exit /b 1
echo ==== YCore Electron start ====>>"%ELECTRON_LOG%"
npm.cmd run electron:start >>"%ELECTRON_LOG%" 2>>&1
echo ==== YCore Electron exited with %ERRORLEVEL% ====>>"%ELECTRON_LOG%"
exit /b %ERRORLEVEL%
