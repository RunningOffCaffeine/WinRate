@echo OFF
SETLOCAL EnableDelayedExpansion
ECHO Starting compile_bots.bat...
ECHO.

REM --- User Selection ---
:ChooseVersion
ECHO Which version do you want to build?
ECHO   1. NORMAL (winrate_original.py) [DEPRECATED]
ECHO   2. MULTITHREADED (multithreaded_winrate.py)
SET /P BUILD_CHOICE="Enter 1 or 2 and press ENTER (default MULTI): "
IF "%BUILD_CHOICE%"=="1" (
    SET BUILD_TARGET=NORMAL
) ELSE IF "%BUILD_CHOICE%"=="2" (
    SET BUILD_TARGET=MULTI
) ELSE (
    SET BUILD_TARGET=MULTI
)
ECHO Selected: %BUILD_TARGET%
ECHO.

REM --- Configuration ---
ECHO Setting configuration variables...
SET PYTHON_VERSION_SPECIFIER=-3.13

REM Adjusted paths for subfolders
SET NORMAL_SCRIPT_NAME=assets\winrate_original.py
SET NORMAL_EXE_NAME=LimbusBot
SET NORMAL_ICON_PATH=normal.ico

SET MULTITHreadED_SCRIPT_NAME=assets\multithreaded_winrate.py
SET MULTITHreadED_EXE_NAME=LimbusBot_Multithreaded
SET MULTITHreadED_ICON_PATH=multi.ico

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

REM Determine which version's config to look for
IF "%BUILD_TARGET%"=="NORMAL" (
    SET "EXE_NAME_TO_CHECK=%NORMAL_EXE_NAME%"
) ELSE (
    SET "EXE_NAME_TO_CHECK=%MULTITHreadED_EXE_NAME%"
)
REM We check for the config next to the old .exe, as that is the target location
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
ECHO Checking for icon files...
SET "NORMAL_ICON_OPTION_CMD="
IF EXIST "%NORMAL_ICON_PATH%" (
    ECHO Found icon for NORMAL bot: %NORMAL_ICON_PATH%
    SET "NORMAL_ICON_OPTION_CMD=--icon="%NORMAL_ICON_PATH%""
) ELSE (
    ECHO WARNING: Icon file for NORMAL bot NOT FOUND at "%NORMAL_ICON_PATH%"
)

SET "MULTITHREADED_ICON_OPTION_CMD="
IF EXIST "%MULTITHREADED_ICON_PATH%" (
    ECHO Found icon for MULTITHREADED bot: %MULTITHREADED_ICON_PATH%
    SET "MULTITHREADED_ICON_OPTION_CMD=--icon="%MULTITHREADED_ICON_PATH%""
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
IF "%BUILD_TARGET%"=="NORMAL" (
    GOTO CompileNormal
) ELSE (
    GOTO CompileMulti
)

:CompileNormal
ECHO Compiling NORMAL version...
SET "PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "%NORMAL_EXE_NAME%" --distpath .\%DIST_FOLDER%"
SET "SCRIPT_TO_COMPILE=%NORMAL_SCRIPT_NAME%"
SET "ICON_OPTION=!NORMAL_ICON_OPTION_CMD!"
GOTO ExecuteCompilation

:CompileMulti
ECHO Compiling MULTITHREADED version...
SET "PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "%MULTITHreadED_EXE_NAME%" --distpath .\%DIST_FOLDER%"
SET "SCRIPT_TO_COMPILE=%MULTITHreadED_SCRIPT_NAME%"
SET "ICON_OPTION=!MULTITHreadED_ICON_OPTION_CMD!"
GOTO ExecuteCompilation

:ExecuteCompilation
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
REM This --add-data argument places the file in the root of the build folder, next to the .exe
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
IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for !BUILD_TARGET! version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
)
ECHO !BUILD_TARGET! version compiled successfully.
ECHO Finished compilation attempt.
GOTO RestoreConfig

:RestoreConfig
ECHO.
ECHO Placing config file in new build directory...
REM Determine which version's folder to restore to
IF "!BUILD_TARGET!"=="NORMAL" (
    SET "EXE_NAME_TO_CHECK=!NORMAL_EXE_NAME!"
) ELSE (
    SET "EXE_NAME_TO_CHECK=!MULTITHreadED_EXE_NAME!"
)
REM Construct the path to the directory where the .exe is located.
SET "FINAL_EXE_DIR=!DIST_FOLDER!\!EXE_NAME_TO_CHECK!\"
REM Construct the full final path for the config file.
SET "FINAL_CONFIG_PATH=!FINAL_EXE_DIR!!CONFIG_JSON!"

IF DEFINED CONFIG_SOURCE_FILE (
    IF EXIST "!CONFIG_SOURCE_FILE!" (
        IF EXIST "!FINAL_EXE_DIR!" (
            REM Wait for 1 second to ensure PyInstaller has released file handles.
            ECHO Waiting for file handles to be released...
            timeout /t 1 /nobreak >nul

            REM Copy the source config file to the same directory as the executable, overwriting the one from the build.
            ECHO Copying '!CONFIG_SOURCE_FILE!' to '!FINAL_CONFIG_PATH!'
            COPY /Y "!CONFIG_SOURCE_FILE!" "!FINAL_CONFIG_PATH!"

            REM Check if copy was successful before proceeding.
            IF !ERRORLEVEL! NEQ 0 (
                ECHO ERROR: Failed to copy config file. Access may be denied or path issue.
            ) ELSE (
                ECHO Config file placed successfully next to the .exe.
                REM If the original source was the temp file, delete it from the root directory.
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