@echo OFF
ECHO Starting compile_bots.bat...
ECHO This window should remain open due to PAUSE statements for debugging.
ECHO If it closes before the first 'Press any key to continue', there might be an issue with how the .bat file is launched or a very early syntax error.

REM --- User Selection ---
:ChooseVersion
ECHO.
ECHO Which version do you want to build?
ECHO   1. NORMAL (winrate.py)
ECHO   2. MULTITHREADED (multithreaded_winrate.py)
SET /P BUILD_CHOICE=Enter 1 or 2 and press ENTER: 
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

REM Ensure PyInstaller is installed for Python 3.13: py -3.13 -m pip install pyinstaller

REM --- Configuration ---
ECHO Setting configuration variables...
SET PYTHON_VERSION_SPECIFIER=-3.13

REM Define icon paths - REPLACE THESE with actual paths or ensure files are in the same directory
SET NORMAL_ICON_PATH=normal.ico
SET MULTITHREADED_ICON_PATH=multi.ico

SET DIST_FOLDER=dist
SET BUILD_FOLDER=build
SET ASSET_FILES=*.png
SET CONFIG_JSON=saved_user_vars.json
ECHO Configuration variables set.

REM --- Clean Up dist Folder (Delete everything except .json) ---
ECHO Cleaning up %DIST_FOLDER% folder (except .json files)...
IF EXIST "%DIST_FOLDER%" (
    PUSHD "%DIST_FOLDER%"
    FOR %%F IN (*.*) DO (
        IF /I NOT "%%~xF"==".json" DEL "%%F"
    )
    POPD
) ELSE (
    ECHO %DIST_FOLDER% folder does not exist, skipping cleanup.
)
ECHO dist folder cleanup complete.

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

ECHO NORMAL_ICON_OPTION_CMD is: [%NORMAL_ICON_OPTION_CMD%]
ECHO MULTITHREADED_ICON_OPTION_CMD is: [%MULTITHREADED_ICON_OPTION_CMD%]

REM Create dist folder (it was just deleted, so recreate)
IF NOT EXIST %DIST_FOLDER% (
    ECHO Creating %DIST_FOLDER% directory...
    MKDIR %DIST_FOLDER%
)

ECHO.
ECHO --- Environment Diagnostics (Brief) ---
ECHO Verifying Python executable for %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import sys; print(f'Using Python Executable: {sys.executable}')"
ECHO Checking if PyInstaller can be imported by %PYTHON_VERSION_SPECIFIER%:
py %PYTHON_VERSION_SPECIFIER% -c "import PyInstaller; print(f'PyInstaller version: {PyInstaller.__version__} from {PyInstaller.__file__}')"
IF %ERRORLEVEL% NEQ 0 (
    ECHO WARNING: PyInstaller module could not be imported directly by 'py %PYTHON_VERSION_SPECIFIER% -c "import PyInstaller"'.
    ECHO This might indicate an issue with the Python environment used by the batch script.
)
ECHO --- End Environment Diagnostics ---
ECHO.

IF "%BUILD_TARGET%"=="NORMAL" (
    ECHO Compiling NORMAL version (winrate.py)...
    SET PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "Limbus Bot" --distpath .\%DIST_FOLDER%
    SET PYINSTALLER_CMD_DATA=
    IF EXIST "%CONFIG_JSON%" (
        ECHO Including config file: %CONFIG_JSON%
        SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%CONFIG_JSON%;."
    ) ELSE (
        ECHO WARNING: Config file %CONFIG_JSON% not found. Compiling without it.
    )
    SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%ASSET_FILES%;."
    SET PYINSTALLER_CMD_ICON=
    IF DEFINED NORMAL_ICON_OPTION_CMD (
        ECHO Including icon: %NORMAL_ICON_OPTION_CMD%
        SET PYINSTALLER_CMD_ICON=%NORMAL_ICON_OPTION_CMD%
    ) ELSE (
        ECHO Compiling NORMAL version without specific icon.
    )
    ECHO ---
    ECHO EXECUTING: %PYINSTALLER_CMD_BASE% %PYINSTALLER_CMD_ICON% %PYINSTALLER_CMD_DATA% "winrate.py"
    ECHO ---
    %PYINSTALLER_CMD_BASE% %PYINSTALLER_CMD_ICON% %PYINSTALLER_CMD_DATA% "winrate.py"
    IF %ERRORLEVEL% NEQ 0 (
        ECHO --------------------------------------------------------------------
        ECHO ERROR: PyInstaller failed for NORMAL version.
        ECHO Please check the output above for specific error messages.
        ECHO Ensure Python %PYTHON_VERSION_SPECIFIER% is correctly configured and PyInstaller is installed for it.
        ECHO You can try: py %PYTHON_VERSION_SPECIFIER% -m pip install pyinstaller --force-reinstall
        ECHO --------------------------------------------------------------------
        GOTO ErrorOccurred
    ) ELSE (
        ECHO NORMAL version compiled successfully to .\%DIST_FOLDER%\Limbus Bot.exe
        IF EXIST "Limbus Bot.spec" (
            ECHO Deleting Limbus Bot.spec...
            DEL "Limbus Bot.spec"
        )
    )
    ECHO Finished NORMAL version compilation attempt.
) ELSE (
    ECHO Compiling MULTITHREADED version (multithreaded_winrate.py)...
    SET PYINSTALLER_CMD_BASE=py %PYTHON_VERSION_SPECIFIER% -m PyInstaller --noconfirm --clean --windowed --name "Limbus Bot (Multithreaded)" --distpath .\%DIST_FOLDER%
    SET PYINSTALLER_CMD_DATA=
    IF EXIST "%CONFIG_JSON%" (
        ECHO Including config file: %CONFIG_JSON%
        SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%CONFIG_JSON%;."
    ) ELSE (
        ECHO WARNING: Config file %CONFIG_JSON% not found. Compiling without it for MULTITHREADED version.
    )
    SET PYINSTALLER_CMD_DATA=%PYINSTALLER_CMD_DATA% --add-data "%ASSET_FILES%;."
    SET PYINSTALLER_CMD_ICON=
    IF DEFINED MULTITHREADED_ICON_OPTION_CMD (
        ECHO Including icon: %MULTITHREADED_ICON_OPTION_CMD%
        SET PYINSTALLER_CMD_ICON=%MULTITHREADED_ICON_OPTION_CMD%
    ) ELSE (
        ECHO Compiling MULTITHREADED version without specific icon.
    )
    ECHO ---
    ECHO EXECUTING: %PYINSTALLER_CMD_BASE% %PYINSTALLER_CMD_ICON% %PYINSTALLER_CMD_DATA% "multithreaded_winrate.py"
    ECHO ---
    %PYINSTALLER_CMD_BASE% %PYINSTALLER_CMD_ICON% %PYINSTALLER_CMD_DATA% "multithreaded_winrate.py"
    IF %ERRORLEVEL% NEQ 0 (
        ECHO --------------------------------------------------------------------
        ECHO ERROR: PyInstaller failed for MULTITHREADED version.
        ECHO Please check the output above for specific error messages.
        ECHO Ensure Python %PYTHON_VERSION_SPECIFIER% is correctly configured and PyInstaller is installed for it.
        ECHO You can try: py %PYTHON_VERSION_SPECIFIER% -m pip install pyinstaller --force-reinstall
        ECHO --------------------------------------------------------------------
        GOTO ErrorOccurred
    ) ELSE (
        ECHO MULTITHREADED version compiled successfully to .\%DIST_FOLDER%\Limbus Bot (Multithreaded).exe
        IF EXIST "Limbus Bot (Multithreaded).spec" (
            ECHO Deleting "Limbus Bot (Multithreaded).spec"...
            DEL "Limbus Bot (Multithreaded).spec"
        )
    )
    ECHO Finished MULTITHREADED version compilation attempt.
)

ECHO.
ECHO Compilation process finished successfully (or reached this point after an error was handled by GOTO).
GOTO EndScript

:ErrorOccurred
ECHO.
ECHO An error occurred during compilation.
ECHO The window will remain open (due to PAUSE). Press any key to close AFTER reviewing errors.
PAUSE
EXIT /B 1

:EndScript
ECHO.
ECHO Cleaning up any remaining .spec files...
IF EXIST "*.spec" (
    DEL "*.spec"
)
ECHO.
ECHO Script finished. The window will remain open (due to PAUSE) for you to review the output.
ECHO Press any key to close this window.
PAUSE
EXIT /K
