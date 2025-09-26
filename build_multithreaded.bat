@echo OFF
SETLOCAL EnableDelayedExpansion
ECHO Starting compile_bots.bat for LEGACY (template-matching) version...
ECHO.

REM --- Configuration ---
ECHO Setting configuration variables...
SET PYTHON_VERSION_SPECIFIER=-3.13
REM Adjusted paths for subfolders
SET LEGACY_SCRIPT_NAME=multithreaded_winrate.py
SET LEGACY_EXE_NAME=LimbusBot_Multithreaded
SET LEGACY_ICON_PATH=multi.ico

SET DIST_FOLDER=dist
SET BUILD_FOLDER=build
SET TARGET_EXE_DIR=%DIST_FOLDER%\%LEGACY_EXE_NAME%
SET ASSET_FILES=assets\images\*.png
SET CONFIG_JSON=saved_user_vars.json
SET TEMP_CONFIG_BACKUP_NAME=temp_config_backup.json
ECHO Configuration variables set.
ECHO.

REM --- Backup Existing Config from Dist ---
ECHO Backing up existing config file if found...
IF EXIST "%TEMP_CONFIG_BACKUP_NAME%" (
    ECHO Deleting old temp config file.
    DEL "%TEMP_CONFIG_BACKUP_NAME%"
)

SET "DIST_CONFIG_PATH=%TARGET_EXE_DIR%\%CONFIG_JSON%"

IF EXIST "%DIST_CONFIG_PATH%" (
    ECHO Found existing config in dist folder: %DIST_CONFIG_PATH%
    COPY "%DIST_CONFIG_PATH%" "%TEMP_CONFIG_BACKUP_NAME%" > NUL
    ECHO Backed up to %TEMP_CONFIG_BACKUP_NAME%
) ELSE (
    ECHO No existing config found in dist folder to back up.
)
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
ECHO Compiling LEGACY version...

SET "CONFIG_SOURCE_FILE="
IF EXIST "%TEMP_CONFIG_BACKUP_NAME%" ( SET "CONFIG_SOURCE_FILE=%TEMP_CONFIG_BACKUP_NAME%" )
IF EXIST "%CONFIG_JSON%" ( IF NOT DEFINED CONFIG_SOURCE_FILE ( SET "CONFIG_SOURCE_FILE=%CONFIG_JSON%" ) )

IF DEFINED CONFIG_SOURCE_FILE (
    ECHO Including config file: !CONFIG_SOURCE_FILE!
    py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed ^
        --name "%LEGACY_EXE_NAME%" ^
        --distpath "%DIST_FOLDER%" ^
        --icon="%LEGACY_ICON_PATH%" ^
        --add-data="!CONFIG_SOURCE_FILE!;." ^
        --add-data="!ASSET_FILES!;images" ^
        "assets\!LEGACY_SCRIPT_NAME!"
) ELSE (
    ECHO WARNING: Config file %CONFIG_JSON% not found. Compiling without it.
    py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed ^
        --name "%LEGACY_EXE_NAME%" ^
        --distpath "%DIST_FOLDER%" ^
        --icon="%LEGACY_ICON_PATH%" ^
        --add-data="!ASSET_FILES!;images" ^
        "assets\!LEGACY_SCRIPT_NAME!"
)

:CheckCompileResult
IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for LEGACY version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
)
ECHO LEGACY version compiled successfully.
ECHO Finished compilation attempt.
GOTO RestoreConfig

:RestoreConfig
ECHO.
ECHO Placing config file in new build directory...
SET "FINAL_CONFIG_PATH=!TARGET_EXE_DIR!\%CONFIG_JSON%"

IF DEFINED CONFIG_SOURCE_FILE (
    IF EXIST "!CONFIG_SOURCE_FILE!" (
        IF EXIST "!TARGET_EXE_DIR!\" (
            ECHO Waiting for file handles to be released...
            timeout /t 1 /nobreak >nul
            ECHO Copying '!CONFIG_SOURCE_FILE!' to '!FINAL_CONFIG_PATH!'
            COPY /Y "!CONFIG_SOURCE_FILE!" "!FINAL_CONFIG_PATH!"

            IF !ERRORLEVEL! NEQ 0 (
                ECHO ERROR: Failed to copy config file.
            ) ELSE (
                ECHO Config file placed successfully.
                IF /I "!CONFIG_SOURCE_FILE!"=="!TEMP_CONFIG_BACKUP_NAME!" (
                    ECHO Deleting temporary config backup.
                    DEL "!TEMP_CONFIG_BACKUP_NAME!"
                )
            )
        ) ELSE (
            ECHO WARNING: New build directory not found. Cannot place config.
        )
    ) ELSE (
        ECHO WARNING: Source config file disappeared. Cannot place config.
    )
) ELSE (
    ECHO No source config was included in the build.
)
GOTO EndScript

:ErrorOccurred
ECHO.
ECHO An error occurred during compilation.
IF EXIST "!TEMP_CONFIG_BACKUP_NAME!" (
    DEL "!TEMP_CONFIG_BACKUP_NAME!"
)
PAUSE
EXIT /B 1

:EndScript
ECHO.
ECHO Cleaning up build artifacts...
IF EXIST "*.spec" ( DEL "*.spec" )
IF EXIST "%BUILD_FOLDER%" ( RMDIR /S /Q "%BUILD_FOLDER%" )
IF EXIST "!TEMP_CONFIG_BACKUP_NAME!" ( DEL "!TEMP_CONFIG_BACKUP_NAME!" )
ECHO.
ECHO Script finished. Press any key to close.
PAUSE
ENDLOCAL
EXIT /B 0
