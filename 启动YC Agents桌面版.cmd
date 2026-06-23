@echo off
chcp 65001 >nul
setlocal

set "ROOT=%~dp0"
set "DESKTOP=%ROOT%desktop"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "URL=http://127.0.0.1:5173"

echo === YC Agents 桌面版启动器 ===
echo.

if not exist "%PYTHON%" (
    echo 没找到 Python 虚拟环境：
    echo   %PYTHON%
    echo.
    echo 请先在项目根目录执行：
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo 没找到 npm.cmd。请先安装 Node.js。
    echo.
    pause
    exit /b 1
)

if not exist "%DESKTOP%\node_modules" (
    echo 没找到桌面端依赖：
    echo   %DESKTOP%\node_modules
    echo.
    echo 请先执行：
    echo   cd /d "%DESKTOP%"
    echo   npm.cmd install
    echo.
    pause
    exit /b 1
)

echo [1/3] 启动 Python 后端，端口 8765...
start "YC Agents API" cmd /k "chcp 65001 >nul && cd /d ""%ROOT%"" && ""%PYTHON%"" -m yc_agents.desktop.server"

echo [2/3] 启动桌面前端，端口 5173...
start "YC Agents Frontend" cmd /k "chcp 65001 >nul && cd /d ""%DESKTOP%"" && npm.cmd run dev"

echo [3/3] 等待前端就绪...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%URL%'; $deadline=(Get-Date).AddSeconds(25); do { try { $response=Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 1; if ($response.StatusCode -lt 500) { exit 0 } } catch {}; Start-Sleep -Milliseconds 500 } while ((Get-Date) -lt $deadline); exit 1"

if errorlevel 1 (
    echo 前端可能还在启动。稍后请手动打开：
    echo   %URL%
) else (
    echo 打开浏览器：
    echo   %URL%
    start "" "%URL%"
)

echo.
echo 后端窗口和前端窗口保持开启时，YC Agents 才能使用。
echo 关闭这两个窗口即可停止服务。

endlocal
