# AeroSync — One-Time Setup Script (PowerShell)
# Sets up Python virtual environment, dependencies, Chrome integration, and Windows Auto-Start

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "                AEROSYNC — CELESTIAL WORKSPACE SYNC                 " -ForegroundColor White
Write-Host "                     One-Time Setup Script                          " -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

# 1. Check Python
Write-Host "[1/6] Checking Python installation..." -ForegroundColor Green
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    Write-Host "[ERROR] Python 3.10+ was not found on PATH." -ForegroundColor Red
    Write-Host "Please install Python from https://www.python.org/ and re-run this script." -ForegroundColor Yellow
    Exit 1
}
& python --version

# 2. Check / Create Virtualenv
Write-Host "`n[2/6] Checking Virtual Environment..." -ForegroundColor Green
if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Creating venv in .\venv..." -ForegroundColor Gray
    & python -m venv venv
}
Write-Host "Virtual environment ready." -ForegroundColor Gray

# 3. Install Requirements
Write-Host "`n[3/6] Installing dependencies..." -ForegroundColor Green
& .\venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
Write-Host "Dependencies installed successfully." -ForegroundColor Gray

# 4. Check Chrome
Write-Host "`n[4/6] Verifying Google Chrome auto-launcher..." -ForegroundColor Green
& .\venv\Scripts\python.exe -c "from services.chrome_launcher.chrome_manager import find_chrome_executable; p = find_chrome_executable(); print('Chrome status:', p if p else 'Standard fallback')"

# 5. Auto-Start
Write-Host "`n[5/6] Auto-Start Configuration..." -ForegroundColor Green
$choice = Read-Host "Start AeroSync automatically when you log into Windows? (Y/N, default Y)"
if ($choice -ne "N" -and $choice -ne "n") {
    & .\venv\Scripts\python.exe apps\client\main.py --enable-autostart
    Write-Host "Auto-start enabled in Windows registry." -ForegroundColor Green
} else {
    Write-Host "Auto-start skipped." -ForegroundColor Gray
}

# 6. Create Desktop Shortcut
Write-Host "`n[6/6] Creating Desktop Shortcut..." -ForegroundColor Green
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "AeroSync.lnk"
$targetPath = Join-Path $scriptDir "start_aerosync.bat"

$wscript = New-Object -ComObject WScript.Shell
$shortcut = $wscript.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $scriptDir
$shortcut.Description = "AeroSync Desktop Constellation"
$shortcut.Save()
Write-Host "Desktop shortcut created at: $shortcutPath" -ForegroundColor Green

Write-Host "`n=====================================================================" -ForegroundColor Cyan
Write-Host "                     SETUP COMPLETE!                                 " -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "Gestures Cheatsheet:" -ForegroundColor White
Write-Host "  • FIST  [✊] facing camera: Arm Host A (Captures workspace)" -ForegroundColor Yellow
Write-Host "  • THROW [🚀] facing camera: Claim Target B (Transfers to this PC)" -ForegroundColor Cyan
Write-Host ""

$launch = Read-Host "Launch AeroSync now? (Y/N, default Y)"
if ($launch -ne "N" -and $launch -ne "n") {
    Start-Process $targetPath
}
