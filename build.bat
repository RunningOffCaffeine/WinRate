@echo off
setlocal

rem ── Adjust this if your Python 3.13 path is different ────────────────
set "PYTHON_DIR=%UserProfile%\AppData\Local\Programs\Python\Python313"
if not exist "%PYTHON_DIR%\python.exe" (
  echo ERROR: Python not found at "%PYTHON_DIR%\python.exe"
  pause
  exit /b 1
)

rem ── Make sure we use Python 3.13’s pip & PyInstaller ──────────────────
set "PATH=%PYTHON_DIR%;%PYTHON_DIR%\Scripts;%PATH%"

rem ── Clean out any previous build artifacts ──────────────────────────
if exist build rd /s /q build
if exist dist  rd /s /q dist
if exist winrate.spec del winrate.spec

rem ── Build a one‐file console EXE from winrate.py ─────────────────────
echo Building winrate.py -> WinRate.exe ...
python -m PyInstaller ^
    --noconfirm ^
    --clean    ^
    --onefile  ^
    --console  ^
    --name WinRate  ^
    winrate.py

if errorlevel 1 (
  echo.
  echo BUILD FAILED.
  pause
  exit /b 1
)

echo.
echo BUILD SUCCEEDED!  Executable is at dist\WinRate.exe
pause
endlocal
