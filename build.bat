@echo OFF
ECHO Starting compile_bots.bat...
ECHO.

REM --- User Selection ---
:ChooseVersion
ECHO Which version do you want to build?
ECHO   1. NORMAL (winrate_original.py) [DEPRECATED]
ECHO   2. MULTITHREADED (multithreaded_winrate.py)
SET /P BUILD_CHOICE="Enter 1 or 2 and press ENTER: "
IF "%BUILD_CHOICE%"=="1" (
    SET BUILD_TARGET=NORMAL
) ELSE IF "%BUILD_CHOICE%"=="2" (
    SET BUILD_TARGET=MULTI
) ELSE (
    ECHO Invalid choice. Please enter 1 or 2.
    GOTO ChooseVersion
)
ECHO Selected: %BUILD_TARGET%
ECHO.

REM --- Configuration ---
ECHO Setting configuration variables...
SET PYTHON_VERSION_SPECIFIER=-3.13

REM Define script and exe names WITHOUT internal quotes
SET NORMAL_SCRIPT_NAME=winrate_original.py
SET NORMAL_EXE_NAME=LimbusBot_Normal
SET NORMAL_ICON_PATH=normal.ico

SET MULTITHREADED_SCRIPT_NAME=multithreaded_winrate.py
REM Using a simplified name is more robust for batch scripting.
SET MULTITHREADED_EXE_NAME=Limbus_Bot_Multithreaded
SET MULTITHREADED_ICON_PATH=multi.ico

SET DIST_FOLDER=dist
SET BUILD_FOLDER=build
SET ASSET_FILES=*.png
SET CONFIG_JSON=saved_user_vars.json
ECHO Configuration variables set.

REM --- Clean Up dist Folder ---
ECHO Cleaning up %DIST_FOLDER% folder...
IF EXIST "%DIST_FOLDER%" (
    ECHO Deleting contents of %DIST_FOLDER%...
    RMDIR /S /Q "%DIST_FOLDER%"
)
ECHO Creating fresh %DIST_FOLDER% directory...
MKDIR "%DIST_FOLDER%"
ECHO Cleanup complete.

REM --- Icon Check ---
ECHO Checking for icon files...
SET NORMAL_ICON_OPTION_CMD=
IF NOT EXIST "%NORMAL_ICON_PATH%" (
    ECHO WARNING: Icon file for NORMAL bot NOT FOUND at "%NORMAL_ICON_PATH%"
) ELSE (
    ECHO Found icon for NORMAL bot: %NORMAL_ICON_PATH%
    SET NORMAL_ICON_OPTION_CMD=--icon="%NORMAL_ICON_PATH%"
)

SET MULTITHREADED_ICON_OPTION_CMD=
IF NOT EXIST "%MULTITHREADED_ICON_PATH%" (
    ECHO WARNING: Icon file for MULTITHREADED bot NOT FOUND at "%MULTITHREADED_ICON_PATH%"
) ELSE (
    ECHO Found icon for MULTITHREADED bot: %MULTITHREADED_ICON_PATH%
    SET MULTITHREADED_ICON_OPTION_CMD=--icon="%MULTITHREADED_ICON_PATH%"
)
ECHO Icon check complete.

REM --- Environment Diagnostics ---
ECHO Verifying Python executable for %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import sys; print(f'Using Python Executable: {sys.executable}')"
ECHO Checking if PyInstaller can be imported by %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import PyInstaller; print(f'PyInstaller version: {PyInstaller.__version__} from {PyInstaller.__file__}')"
IF %ERRORLEVEL% NEQ 0 ( ECHO WARNING: PyInstaller module could not be imported directly. )
ECHO.

REM --- Main Compilation Logic ---
IF "%BUILD_TARGET%"=="NORMAL" (
    GOTO CompileNormal
) ELSE (
    GOTO CompileMulti
)

:CompileNormal
ECHO Compiling NORMAL version...
SET PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "%NORMAL_EXE_NAME%" --distpath .\%DIST_FOLDER%
SET SCRIPT_TO_COMPILE=%NORMAL_SCRIPT_NAME%
SET ICON_OPTION=%NORMAL_ICON_OPTION_CMD%
GOTO ExecuteCompilation

:CompileMulti
ECHO Compiling MULTITHREADED version...
SET PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "%MULTITHREADED_EXE_NAME%" --distpath .\%DIST_FOLDER%
SET SCRIPT_TO_COMPILE=%MULTITHREADED_SCRIPT_NAME%
SET ICON_OPTION=%MULTITHREADED_ICON_OPTION_CMD%
GOTO ExecuteCompilation

:ExecuteCompilation
SET PYINSTALLER_CMD_DATA=
IF EXIST "%CONFIG_JSON%" (
    ECHO Including config file: %CONFIG_JSON%
    SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%CONFIG_JSON%;."
) ELSE (
    ECHO WARNING: Config file %CONFIG_JSON% not found. Compiling without it.
)
SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%ASSET_FILES%;."

ECHO ---
ECHO EXECUTING: %PYINSTALLER_CMD_BASE% %ICON_OPTION% %PYINSTALLER_CMD_DATA% %SCRIPT_TO_COMPILE%
ECHO ---
%PYINSTALLER_CMD_BASE% %ICON_OPTION% %PYINSTALLER_CMD_DATA% %SCRIPT_TO_COMPILE%

IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for %BUILD_TARGET% version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
) ELSE (
    ECHO %BUILD_TARGET% version compiled successfully.
    IF EXIST "%BUILD_TARGET_EXE_NAME%.spec" (
        ECHO Deleting .spec file...
        DEL "%BUILD_TARGET_EXE_NAME%.spec"
    )
)
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
EXIT /B 0
