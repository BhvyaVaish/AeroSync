@echo off
setlocal enabledelayedexpansion

title AeroSync — One-Time Setup & Constellation Config
color 0B

echo =====================================================================
echo                AEROSYNC — CELESTIAL WORKSPACE SYNC
echo                    One-Time Interactive Setup
echo =====================================================================
echo.

:: 1. Check Python
echo [1/6] Checking Python installation...
where python >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 3.10+ was not found on your PATH.
    echo Please install Python 3.10 or newer from https://www.python.org/
    pause
    exit /b 1
)
python --version
echo.

:: 2. Check / Create Virtual Environment
echo [2/6] Checking Virtual Environment (venv)...
if not exist "venv\Scripts\python.exe" (
    echo Creating virtual environment in .\venv...
    python -m venv venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)
echo Virtual environment ready.
echo.

:: 3. Upgrade pip and install requirements
echo [3/6] Installing dependencies from requirements.txt...
.\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if %ERRORLEVEL% neq 0 (
    echo [WARNING] Some dependencies failed to install cleanly. Retrying key packages...
    .\venv\Scripts\python.exe -m pip install psutil pystray pillow opencv-python mediapipe httpx fastapi uvicorn
)
echo Dependencies verified.
echo.

:: 4. Verify Chrome Installation
echo [4/6] Verifying Google Chrome auto-launcher...
.\venv\Scripts\python.exe -c "from services.chrome_launcher.chrome_manager import find_chrome_executable; p = find_chrome_executable(); print('Chrome located:', p if p else 'Standard fallback (cmd start chrome)')"
echo.

:: 5. Auto-Start at Windows Login
echo [5/6] Configuring Windows Auto-Start...
set /p AUTOSTART="Would you like AeroSync to start automatically when you log into Windows? (Y/N, default Y): "
if /i "%AUTOSTART%"=="N" (
    echo Auto-start skipped.
) else (
    .\venv\Scripts\python.exe apps\client\main.py --enable-autostart
    echo AeroSync registered in Windows startup.
)
echo.

:: 6. Setup Desktop Shortcut
echo [6/6] Creating Desktop shortcut for AeroSync...
set SCRIPT_DIR=%~dp0
set TARGET_PATH=%SCRIPT_DIR%start_aerosync.bat
set SHORTCUT_PATH=%USERPROFILE%\Desktop\AeroSync.lnk

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT_PATH%'); $s.TargetPath = '%TARGET_PATH%'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Description = 'AeroSync Desktop Constellation'; $s.Save()"
echo Desktop shortcut created: %SHORTCUT_PATH%
echo.

echo =====================================================================
echo                     SETUP COMPLETE!
echo =====================================================================
echo.
echo Quick Gestures:
echo   • FIST  [✊] facing camera: Arm Host A (Captures workspace)
echo   • THROW [🚀] facing camera: Claim Target B (Transfers to this PC)
echo.
echo Launching AeroSync System Tray & Frontend...
start "" "%SCRIPT_DIR%start_aerosync.bat"

echo Done. You may close this window.
pause
