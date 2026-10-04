@echo off
:: ArchiBox Agent — Install Script
:: Run as Administrator (right-click > Run as administrator)
:: Downloads the latest release from GitHub and sets up the service.

echo ========================================
echo  ArchiBox Agent — Installation
echo ========================================
echo.

set "REPO=thecozmopolite/archibox-agent"
set "API_URL=https://api.github.com/repos/%REPO%/releases/latest"

:: Check admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please run as Administrator!
    echo Right-click this file ^> Run as administrator
    pause
    exit /b 1
)

echo [1/4] Fetching latest release info...
for /f "tokens=*" %%i in ('powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (Invoke-RestMethod -Uri '%API_URL%' -UseBasicParsing).assets | Where-Object { $_.name -like 'archibox-usb-watch.exe' } | Select-Object -First 1 | ConvertTo-Json"') do set "ASSET=%%i"

if "%ASSET%"=="" (
    echo [ERROR] Could not fetch release info. Check internet connection.
    pause
    exit /b 1
)

echo [2/4] Downloading archibox-usb-watch.exe...
for /f "tokens=*" %%i in ('powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (Invoke-RestMethod -Uri '%API_URL%' -UseBasicParsing).assets | Where-Object { $_.name -like 'archibox-usb-watch.exe' } | Select-Object -First 1 | Select-Object -ExpandProperty browser_download_url"') do set "DOWNLOAD_URL=%%i"

powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%DOWNLOAD_URL%' -OutFile '%~dp0archibox-usb-watch.exe' -UseBasicParsing"
if %errorLevel% neq 0 (
    echo [ERROR] Download failed.
    pause
    exit /b 1
)

echo [3/4] Installing startup shortcut...
:: Add to startup via registry (current user only)
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "ArchiBox USB Watch" /t REG_SZ /d "\"%~dp0archibox-usb-watch.exe\"" /f >nul 2>&1

:: Also create Start Menu shortcut
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%APPDATA%\Microsoft\Windows\Start Menu\Programs\ArchiBox USB Watch.lnk'); $s.TargetPath = '%~dp0archibox-usb-watch.exe'; $s.WorkingDirectory = '%~dp0'; $s.Save()"

echo [4/4] Done!
echo.
echo ========================================
echo  ArchiBox Agent installed!
echo ========================================
echo.
echo The USB watchdog is now watching for your
echo ArchiBox USB key. Insert it to activate.
echo.
echo To uninstall: run uninstall.bat
echo.
pause
