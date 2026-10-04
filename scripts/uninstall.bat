@echo off
:: ArchiBox Agent — Uninstall Script
:: Run as Administrator

echo ========================================
echo  ArchiBox Agent — Uninstall
echo ========================================
echo.

:: Check admin
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [ERROR] Please run as Administrator!
    pause
    exit /b 1
)

:: Stop running agent and watchdog
taskkill /IM "archibox-agent.exe" /F >nul 2>&1
taskkill /IM "archibox-usb-watch.exe" /F >nul 2>&1
echo [OK] Processes stopped.

:: Remove startup registry entry
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "ArchiBox USB Watch" /f >nul 2>&1
echo [OK] Startup entry removed.

:: Remove Start Menu shortcut
del "%APPDATA%\Microsoft\Windows\Start Menu\Programs\ArchiBox USB Watch.lnk" >nul 2>&1
echo [OK] Start Menu shortcut removed.

echo.
echo ArchiBox Agent fully removed from this PC.
echo (Your USB key is untouched.)
echo.
pause
