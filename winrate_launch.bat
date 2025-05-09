@echo off
REM ─────────────────────────────────────────────────────────────────
REM  WinRate-launch.bat
REM  Batch wrapper for your PyInstaller exe that pauses on error
REM ─────────────────────────────────────────────────────────────────

REM Change to the folder where this script lives:
cd /d "%~dp0"

REM Launch your exe (adjust the name if yours is different):
"%~dp0dist\WinRate.exe" %*

REM Capture its exit code:
set EXITCODE=%ERRORLEVEL%

REM If it failed, print a message and pause so you can read the error:
if not "%EXITCODE%"=="0" (
    echo.
    echo --------------------------------------------------
    echo WinRate.exe exited with error code %EXITCODE%.
    echo See above for the full traceback.
    echo --------------------------------------------------
    pause
)

REM Otherwise just exit silently:
exit /b 0
