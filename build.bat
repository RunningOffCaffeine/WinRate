@echo off
REM ────────────────────────────────────────────────────────────────────
REM build.bat  → builds Limbus_Auto_Bot.exe, bundling all .png files
REM ────────────────────────────────────────────────────────────────────

REM 1) Make sure PyInstaller is on PATH (install if missing)
where pyinstaller >nul 2>&1
if ERRORLEVEL 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM 2) Locate this script’s folder
set "BASEDIR=%~dp0"

REM 3) Build with --add-data to include every PNG in the same folder
echo Building Limbus_Auto_Bot.exe (this may take a minute...)
pyinstaller ^
    --clean ^
    --onefile ^
    --name "Limbus Auto Bot" ^
    --add-data "%BASEDIR%*.png;." ^
    "%BASEDIR%winrate.py"

if ERRORLEVEL 1 (
    echo.
    echo *** Build FAILED ***
    pause
    exit /b 1
)

echo.
echo *** Build SUCCEEDED ***
echo Your EXE is in: dist\Limbus_Auto_Bot.exe
pause
