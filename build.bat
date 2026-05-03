@echo OFF
SETLOCAL EnableDelayedExpansion
ECHO Starting compile_bots.bat...
ECHO.

REM --- Configuration ---
ECHO Setting configuration variables...
SET "PYTHON_VERSION_SPECIFIER=-3.13"

ECHO Using Python 3.13 or newer...
py %PYTHON_VERSION_SPECIFIER% --version

ECHO Checking for PyInstaller...
py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --version >nul 2>&1

IF !ERRORLEVEL! NEQ 0 (
    ECHO PyInstaller not found. Installing...
    py %PYTHON_VERSION_SPECIFIER% -m pip install --upgrade pip
    py %PYTHON_VERSION_SPECIFIER% -m pip install pyinstaller

    IF !ERRORLEVEL! NEQ 0 (
        ECHO Failed to install PyInstaller. Aborting.
        EXIT /B 1
    )
) ELSE (
    ECHO PyInstaller is already installed.
)

REM Adjusted paths for subfolders
SET MULTITHREADED_SCRIPT_NAME=assets\multithreaded_winrate.py
SET MULTITHREADED_EXE_NAME=LimbusBot_Multithreaded
SET MULTITHREADED_ICON_PATH=multi.ico

SET DIST_FOLDER=dist
SET BUILD_FOLDER=build
SET ASSET_FILES=assets\images\*.png
SET CONFIG_JSON=saved_user_vars.json
SET TEMP_CONFIG_BACKUP_NAME=temp_config_backup.json
ECHO Configuration variables set.
ECHO.

REM --- Backup Existing Config from Dist ---
ECHO Backing up existing config file if found...
REM Clean up any old temp file first
IF EXIST "%TEMP_CONFIG_BACKUP_NAME%" (
    ECHO Deleting old temp config file.
    DEL "%TEMP_CONFIG_BACKUP_NAME%"
)

SET "EXE_NAME_TO_CHECK=%MULTITHREADED_EXE_NAME%"
SET "DIST_CONFIG_PATH=%DIST_FOLDER%\%EXE_NAME_TO_CHECK%\%CONFIG_JSON%"

IF EXIST "%DIST_CONFIG_PATH%" (
    ECHO Found existing config in dist folder: %DIST_CONFIG_PATH%
    COPY "%DIST_CONFIG_PATH%" "%TEMP_CONFIG_BACKUP_NAME%" > NUL
    ECHO Backed up to %TEMP_CONFIG_BACKUP_NAME%
) ELSE (
    ECHO No existing config found in dist folder to back up.
)
ECHO.

REM --- Clean Up dist Folder ---
ECHO Cleaning up %DIST_FOLDER% folder...
IF EXIST "%DIST_FOLDER%" (
    PUSHD "%DIST_FOLDER%"
    FOR /D %%F IN (*) DO (
        ECHO Deleting directory %%F
        RMDIR /S /Q "%%F"
    )
    FOR %%F IN (*) DO (
        ECHO Deleting file %%F
        DEL /F /Q "%%F"
    )
    POPD
) ELSE (
    ECHO %DIST_FOLDER% does not exist. Creating it...
    MKDIR "%DIST_FOLDER%"
)
ECHO Cleanup complete.
ECHO.

REM --- Icon Check ---
ECHO Checking for icon file...
SET "MULTITHREADED_ICON_OPTION_CMD="
IF EXIST "%MULTITHREADED_ICON_PATH%" (
    ECHO Found icon for MULTITHREADED bot: %MULTITHREADED_ICON_PATH%
    SET "MULTITHREADED_ICON_OPTION_CMD=--icon=""%MULTITHREADED_ICON_PATH%"""
) ELSE (
    ECHO WARNING: Icon file for MULTITHREADED bot NOT FOUND at "%MULTITHREADED_ICON_PATH%"
)
ECHO Icon check complete.
ECHO.

REM --- Environment Diagnostics ---
ECHO Verifying Python executable for %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import sys; print(f'Using Python Executable: {sys.executable}')"
ECHO Checking if PyInstaller can be imported by %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import PyInstaller; print(f'PyInstaller version: {PyInstaller.__version__} from {PyInstaller.__file__}')"
IF %ERRORLEVEL% NEQ 0 ( ECHO WARNING: PyInstaller module could not be imported directly. )
ECHO.

REM --- Main Compilation Logic ---
ECHO Compiling MULTITHREADED version...
SET "PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "%MULTITHREADED_EXE_NAME%" --distpath .\%DIST_FOLDER%"
SET "SCRIPT_TO_COMPILE=%MULTITHREADED_SCRIPT_NAME%"
SET "ICON_OPTION=!MULTITHREADED_ICON_OPTION_CMD!"

SET "CONFIG_SOURCE_FILE="
IF EXIST "%TEMP_CONFIG_BACKUP_NAME%" (
    SET "CONFIG_SOURCE_FILE=%TEMP_CONFIG_BACKUP_NAME%"
    GOTO DoCompileWithConfig
)
IF EXIST "%CONFIG_JSON%" (
    SET "CONFIG_SOURCE_FILE=%CONFIG_JSON%"
    GOTO DoCompileWithConfig
)
ECHO WARNING: Config file %CONFIG_JSON% not found. Compiling without it.
GOTO DoCompileWithoutConfig

:DoCompileWithConfig
ECHO Including config file: !CONFIG_SOURCE_FILE!
SET "CONFIG_ARG=--add-data="!CONFIG_SOURCE_FILE!;!CONFIG_JSON!""
SET "ASSETS_ARG=--add-data="!ASSET_FILES!;images""
ECHO ---
ECHO EXECUTING: !PYINSTALLER_CMD_BASE! !ICON_OPTION! !CONFIG_ARG! !ASSETS_ARG! "!SCRIPT_TO_COMPILE!"
ECHO ---
!PYINSTALLER_CMD_BASE! !ICON_OPTION! !CONFIG_ARG! !ASSETS_ARG! "!SCRIPT_TO_COMPILE!"
GOTO CheckCompileResult

:DoCompileWithoutConfig
SET "ASSETS_ARG=--add-data="!ASSET_FILES!;images""
ECHO ---
ECHO EXECUTING: !PYINSTALLER_CMD_BASE! !ICON_OPTION! !ASSETS_ARG! "!SCRIPT_TO_COMPILE!"
ECHO ---
!PYINSTALLER_CMD_BASE! !ICON_OPTION! !ASSETS_ARG! "!SCRIPT_TO_COMPILE!"
GOTO CheckCompileResult

:CheckCompileResult
IF !ERRORLEVEL! NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for MULTITHREADED version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
)
ECHO MULTITHREADED version compiled successfully.
ECHO Finished compilation attempt.
GOTO RestoreConfig

:RestoreConfig
ECHO.
ECHO Placing config file in new build directory...
SET "EXE_NAME_TO_CHECK=!MULTITHREADED_EXE_NAME!"
SET "FINAL_EXE_DIR=!DIST_FOLDER!\!EXE_NAME_TO_CHECK!\"
SET "FINAL_CONFIG_PATH=!FINAL_EXE_DIR!!CONFIG_JSON!"

IF DEFINED CONFIG_SOURCE_FILE (
    IF EXIST "!CONFIG_SOURCE_FILE!" (
        IF EXIST "!FINAL_EXE_DIR!" (
            ECHO Waiting for file handles to be released...
            timeout /t 1 /nobreak >nul

            ECHO Copying '!CONFIG_SOURCE_FILE!' to '!FINAL_CONFIG_PATH!'
            COPY /Y "!CONFIG_SOURCE_FILE!" "!FINAL_CONFIG_PATH!"

            IF !ERRORLEVEL! NEQ 0 (
                ECHO ERROR: Failed to copy config file. Access may be denied or path issue.
            ) ELSE (
                ECHO Config file placed successfully next to the .exe.
                IF /I "!CONFIG_SOURCE_FILE!"=="!TEMP_CONFIG_BACKUP_NAME!" (
                    ECHO Deleting temporary config backup.
                    DEL "!TEMP_CONFIG_BACKUP_NAME!"
                )
            )
        ) ELSE (
            ECHO WARNING: New build directory '!FINAL_EXE_DIR!' not found. Cannot place config.
        )
    ) ELSE (
        ECHO WARNING: The source config file '!CONFIG_SOURCE_FILE!' disappeared. Cannot place config.
    )
) ELSE (
    ECHO No source config was included in the build.
)
GOTO EndScript

:ErrorOccurred
ECHO.
ECHO An error occurred during compilation.
IF EXIST "!TEMP_CONFIG_BACKUP_NAME!" (
    ECHO Deleting temporary config backup file.
    DEL "!TEMP_CONFIG_BACKUP_NAME!"
)
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
IF EXIST "!TEMP_CONFIG_BACKUP_NAME!" (
    ECHO Deleting leftover temporary config file.
    DEL "!TEMP_CONFIG_BACKUP_NAME!"
)
ECHO.
ECHO Script finished. The window will remain open. Press any key to close.
PAUSE
ENDLOCAL
EXIT /B 0
