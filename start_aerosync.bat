@echo off
setlocal
title AeroSync Constellation Launcher

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo Starting AeroSync Constellation Services...

:: 1. Start Relay Server in background if port 8000 is not in use
netstat -ano | findstr :8000 >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [1/3] Starting Relay Server on port 8000...
    start /b "" "%SCRIPT_DIR%venv\Scripts\python.exe" -m uvicorn apps.relay_server.main:app --host 127.0.0.1 --port 8000
    timeout /t 2 /nobreak >nul
) else (
    echo [1/3] Relay Server already running on port 8000.
)

:: 2. Start Frontend if port 5173 is not in use
netstat -ano | findstr :5173 >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [2/3] Starting Vite Frontend on port 5173...
    start /b cmd /c "cd apps\frontend && npm run dev"
    timeout /t 2 /nobreak >nul
) else (
    echo [2/3] Frontend already running on port 5173.
)

:: 3. Start AeroSync Client in background System Tray mode
echo [3/3] Launching AeroSync System Tray Client...
start /b "" "%SCRIPT_DIR%venv\Scripts\python.exe" apps\client\main.py --tray

:: 4. Auto-launch normal Chrome to dashboard
timeout /t 2 /nobreak >nul
"%SCRIPT_DIR%venv\Scripts\python.exe" -c "from services.chrome_launcher.chrome_manager import launch_normal_chrome; launch_normal_chrome(['http://localhost:5173'], new_window=True)"

echo AeroSync is running in your System Tray (bottom right taskbar)!
timeout /t 3 >nul
exit /b 0
