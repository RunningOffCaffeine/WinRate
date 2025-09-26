@echo OFF
SETLOCAL EnableDelayedExpansion
ECHO Starting compile_bots.bat for ML (machine-learning) version...
ECHO.

REM --- Configuration ---
ECHO Setting configuration variables...
SET PYTHON_VERSION_SPECIFIER=-3.13
REM Paths for the ML version
SET ML_SCRIPT_NAME=ml_winrate.py
SET ML_EXE_NAME=LimbusBot_ML
SET ML_ICON_PATH=multi.ico
SET ML_TOOLS_PATH=ml_tools

SET DIST_FOLDER=dist
SET BUILD_FOLDER=build
SET TARGET_EXE_DIR=%DIST_FOLDER%\%ML_EXE_NAME%
ECHO Configuration variables set.
ECHO.

REM --- Clean Up Target Dist Folder ---
ECHO Cleaning up target directory '%TARGET_EXE_DIR%'...
IF EXIST "%TARGET_EXE_DIR%" (
    ECHO Deleting existing directory...
    RMDIR /S /Q "%TARGET_EXE_DIR%"
) ELSE (
    ECHO Target directory does not exist. No cleanup needed.
)
ECHO Cleanup complete.
ECHO.

REM --- Environment Diagnostics ---
ECHO Verifying Python executable for %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import sys; print(f'Using Python Executable: {sys.executable}')"
ECHO Checking if PyInstaller can be imported by %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import PyInstaller; print(f'PyInstaller version: {PyInstaller.__version__} from {PyInstaller.__file__}')"
IF %ERRORLEVEL% NEQ 0 ( ECHO WARNING: PyInstaller module could not be imported directly. )
ECHO.

REM --- Main Compilation Logic ---
ECHO Compiling ML version...

REM This command bundles the ml_tools folder (containing the model, etc.) into the executable.
REM The caret (^) allows us to write the command on multiple lines for readability.
py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed ^
    --name "%ML_EXE_NAME%" ^
    --distpath "%DIST_FOLDER%" ^
    --icon="%ML_ICON_PATH%" ^
    --add-data="%ML_TOOLS_PATH%;ml_tools" ^
    "assets\%ML_SCRIPT_NAME%"

:CheckCompileResult
IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for ML version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
)
ECHO ML version compiled successfully to the '%TARGET_EXE_DIR%' directory.
ECHO Finished compilation attempt.
GOTO EndScript

:ErrorOccurred
ECHO.
ECHO An error occurred during compilation.
ECHO The window will remain open. Press any key to close AFTER reviewing errors.
PAUSE
EXIT /B 1

:EndScript
ECHO.
ECHO Cleaning up any remaining build artifacts...
IF EXIST "*.spec" (
    DEL "*.spec"
)
IF EXIST "%BUILD_FOLDER%" (
    RMDIR /S /Q "%BUILD_FOLDER%"
)
ECHO.
ECHO Script finished. The window will remain open. Press any key to close.
PAUSE
ENDLOCAL
EXIT /B 0

