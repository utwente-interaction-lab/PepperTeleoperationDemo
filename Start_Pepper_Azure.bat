@echo off
title Pepper Teleoperation - Tracker Select
setlocal EnableDelayedExpansion

set "CHORE_LIB=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\lib"
set "CHORE_BIN=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"
set "TRACKER_PY_CMD=py -3.10"
set "TRACKER_BACKEND=mediapipe"
set "TRACKER_SCRIPT=mediapipe_body_tracker.py"
:: GUI_SCRIPT: web_app.py = browser control panel (default), pepper_gui.py = old Tk window
set "GUI_SCRIPT=web_app.py"

:: Find pepper27_32 python (always "call conda" — conda is a .bat file)
set "PEPPER_PY_EXE="
set "CONDA_BASE="
set "BASE_FILE=%TEMP%\pepper_conda_base.txt"
where conda >nul 2>&1
if not errorlevel 1 (
    call conda info --base > "%BASE_FILE%" 2>nul
    if exist "%BASE_FILE%" (
        set /p CONDA_BASE=<"%BASE_FILE%"
        del "%BASE_FILE%" >nul 2>&1
    )
)
if defined CONDA_BASE if exist "!CONDA_BASE!\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=!CONDA_BASE!\envs\pepper27_32\python.exe"

if not defined PEPPER_PY_EXE if exist "%USERPROFILE%\anaconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "%USERPROFILE%\Anaconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\Anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "%LOCALAPPDATA%\anaconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%LOCALAPPDATA%\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "%LOCALAPPDATA%\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%LOCALAPPDATA%\miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "C:\Anaconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=C:\Anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "C:\Miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=C:\Miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "C:\ProgramData\anaconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=C:\ProgramData\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY_EXE if exist "C:\ProgramData\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=C:\ProgramData\miniconda3\envs\pepper27_32\python.exe"

if not exist "%CHORE_LIB%\_qi.pyd" (
    echo [ERROR] Could not find qi Python bindings at:
    echo         !CHORE_LIB!
    echo Please verify Choregraphe Suite 2.5 is installed.
    pause
    exit /b 1
)

if not exist "%CHORE_BIN%\qi.dll" (
    echo [ERROR] Could not find qi runtime DLL at:
    echo         !CHORE_BIN!
    echo Please verify Choregraphe Suite 2.5 is installed.
    pause
    exit /b 1
)

set "PYTHONPATH=%CHORE_LIB%;%PYTHONPATH%"
set "PATH=%CHORE_BIN%;%PATH%"
set "LOG_DIR=%~dp0logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

py -3.10 -V >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Could not run tracker Python with: py -3.10
    echo Install Python 3.10 and make sure the py launcher is available.
    pause
    exit /b 1
)

if /I "%TRACKER_BACKEND%"=="mediapipe" (
    set "TRACKER_SCRIPT=mediapipe_body_tracker.py"
    py -3.10 -c "import cv2, mediapipe, zmq" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Missing MediaPipe tracker deps on Python 3.10.
        echo Install with:
        echo   py -3.10 -m pip install mediapipe opencv-python pyzmq numpy
        pause
        exit /b 1
    )
) else (
    set "TRACKER_SCRIPT=azure_body_tracker.py"
    py -3.10 -c "import cv2, pykinect_azure, zmq" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Missing Azure tracker deps on Python 3.10.
        echo Install with:
        echo   py -3.10 -m pip install pykinect_azure opencv-python pyzmq numpy
        pause
        exit /b 1
    )
)

if not defined PEPPER_PY_EXE (
    echo [ERROR] Could not find pepper27_32 Python environment.
    echo conda base was: !CONDA_BASE!
    echo.
    echo Run setup.bat from an Anaconda Prompt first.
    pause
    exit /b 1
)
set "PEPPER_PY_CMD=!PEPPER_PY_EXE!"

"!PEPPER_PY_CMD!" -c "import qi, naoqi" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pepper runtime cannot import qi/naoqi.
    echo Interpreter: !PEPPER_PY_CMD!
    echo Choregraphe lib must be on PYTHONPATH and env must be Python 2.7 32-bit.
    pause
    exit /b 1
)

"!PEPPER_PY_CMD!" -c "import numpy, scipy, matplotlib, zmq" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pepper Python is missing required packages.
    echo Using interpreter: !PEPPER_PY_CMD!
    echo Install with:
    echo   "!PEPPER_PY_CMD!" -m pip install numpy scipy matplotlib pyzmq pillow
    pause
    exit /b 1
)

echo ============================================================
echo   Pepper Teleoperation System - Configurable Tracker
echo ============================================================
echo.
echo Logs will be written to:
echo   %LOG_DIR%\azure_tracker.log
echo   %LOG_DIR%\pepper_gui.log
echo Pepper Python: "!PEPPER_PY_CMD!"
echo.
echo [1/2] Starting tracker backend: %TRACKER_BACKEND%
echo       (Close this window to shut down the tracker)

:: Clean up stale MediaPipe tracker processes that may still hold ZMQ ports.
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":1234 .*LISTENING"') do (
    for /f "tokens=1" %%I in ('tasklist /FI "PID eq %%P" ^| findstr /I "python.exe"') do (
        echo [INFO] Releasing stale tracker PID %%P on port 1234
        taskkill /PID %%P /F >nul 2>&1
    )
)
for /f "tokens=5" %%P in ('netstat -ano ^| findstr ":1236 .*LISTENING"') do (
    for /f "tokens=1" %%I in ('tasklist /FI "PID eq %%P" ^| findstr /I "python.exe"') do (
        echo [INFO] Releasing stale tracker PID %%P on port 1236
        taskkill /PID %%P /F >nul 2>&1
    )
)

start "Body Tracker" cmd /k "cd /d %~dp0openpose_wrap && py -3.10 %TRACKER_SCRIPT% 1>>""%LOG_DIR%\azure_tracker.log"" 2>>&1"

timeout /t 3 /nobreak >nul

echo [2/2] Starting Pepper Control Panel...
echo       (Close this window to shut down the GUI)

start "Pepper GUI" cmd /k "cd /d %~dp0pepper_teleoperation && ""!PEPPER_PY_CMD!"" -u %GUI_SCRIPT% 1>>""%LOG_DIR%\pepper_gui.log"" 2>>&1"
if /I "%GUI_SCRIPT%"=="web_app.py" echo The control panel opens in your browser: http://127.0.0.1:8000

echo.
echo Both processes started. Close the individual windows to stop them.
echo If either process fails, open the logs above and share the error text.
pause
