@echo OFF
ECHO Creating executables for Limbus Company Bot...

REM Ensure PyInstaller is installed: pip install pyinstaller

REM --- Configuration ---
SET NORMAL_SCRIPT_NAME=winrate.py
SET NORMAL_GUI_CONFIG_NAME=gui_config.py
SET NORMAL_EXE_NAME=LimbusBot

SET MULTITHREADED_SCRIPT_NAME=multithread_winrate.py
SET MULTITHREADED_GUI_CONFIG_NAME=multithread_gui_config.py
SET MULTITHREADED_EXE_NAME=LimbusBot_MultiThreaded

SET DIST_FOLDER=dist
SET ASSET_FILES=*.png
SET CONFIG_JSON=roi_thresholds.json

REM Create dist folder if it doesn't exist
IF NOT EXIST %DIST_FOLDER% (
    ECHO Creating %DIST_FOLDER% directory...
    MKDIR %DIST_FOLDER%
)

ECHO.
ECHO Compiling NORMAL version (%NORMAL_SCRIPT_NAME%)...
ECHO This will use %NORMAL_GUI_CONFIG_NAME%.
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name %NORMAL_EXE_NAME% ^
    --distpath .\%DIST_FOLDER% ^
    --add-data "%ASSET_FILES%;." ^
    --add-data "%CONFIG_JSON%;." ^
    %NORMAL_SCRIPT_NAME%

IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for NORMAL version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
) ELSE (
    ECHO NORMAL version compiled successfully to .\%DIST_FOLDER%\%NORMAL_EXE_NAME%.exe
    REM Delete the .spec file for the normal version
    IF EXIST "%NORMAL_EXE_NAME%.spec" (
        ECHO Deleting %NORMAL_EXE_NAME%.spec...
        DEL "%NORMAL_EXE_NAME%.spec"
    )
)

ECHO.
ECHO Compiling MULTITHREADED version (%MULTITHREADED_SCRIPT_NAME%)...
ECHO This will use %MULTITHREADED_GUI_CONFIG_NAME%.
pyinstaller --noconfirm --clean --onefile --windowed ^
    --name %MULTITHREADED_EXE_NAME% ^
    --distpath .\%DIST_FOLDER% ^
    --add-data "%ASSET_FILES%;." ^
    --add-data "%CONFIG_JSON%;." ^
    %MULTITHREADED_SCRIPT_NAME%

IF %ERRORLEVEL% NEQ 0 (
    ECHO --------------------------------------------------------------------
    ECHO ERROR: PyInstaller failed for MULTITHREADED version.
    ECHO Please check the output above for specific error messages.
    ECHO --------------------------------------------------------------------
    GOTO ErrorOccurred
) ELSE (
    ECHO MULTITHREADED version compiled successfully to .\%DIST_FOLDER%\%MULTITHREADED_EXE_NAME%.exe
    REM Delete the .spec file for the multithreaded version
    IF EXIST "%MULTITHREADED_EXE_NAME%.spec" (
        ECHO Deleting %MULTITHREADED_EXE_NAME%.spec...
        DEL "%MULTITHREADED_EXE_NAME%.spec"
    )
)

ECHO.
ECHO Compilation process finished successfully.
ECHO Executables are in the '%DIST_FOLDER%' directory.
GOTO EndScript

:ErrorOccurred
ECHO.
ECHO An error occurred during compilation.
ECHO The window will remain open. Press any key to close.
PAUSE
EXIT /B 1

:EndScript
ECHO.
ECHO Cleaning up any remaining .spec files...
IF EXIST "*.spec" (
    DEL "*.spec"
)
ECHO.
ECHO Press any key to close this window.
PAUSE
EXIT /B 0
