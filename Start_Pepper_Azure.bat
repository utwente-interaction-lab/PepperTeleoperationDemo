@echo off
title Pepper Teleoperation - Tracker Select
setlocal EnableDelayedExpansion

set "CHORE_LIB=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\lib"
set "CHORE_BIN=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"
set "TRACKER_PY_CMD=py -3.10"
set "TRACKER_BACKEND=mediapipe"
set "TRACKER_SCRIPT=mediapipe_body_tracker.py"
set "PEPPER_PY_EXE="
if exist "%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe"
if exist "%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe"
if exist "C:\Miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=C:\Miniconda3\envs\pepper27_32\python.exe"

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

%TRACKER_PY_CMD% -c "import sys; print(sys.version)" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Could not run tracker Python with: !TRACKER_PY_CMD!
    echo Install Python 3.10 and/or update TRACKER_PY in this .bat file.
    pause
    exit /b 1
)

if /I "%TRACKER_BACKEND%"=="mediapipe" (
    set "TRACKER_SCRIPT=mediapipe_body_tracker.py"
    %TRACKER_PY_CMD% -c "import cv2, mediapipe, zmq; print('ok')" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Missing MediaPipe tracker deps on Python 3.10.
        echo Install with:
        echo   py -3.10 -m pip install mediapipe opencv-python pyzmq numpy
        pause
        exit /b 1
    )
) else (
    set "TRACKER_SCRIPT=azure_body_tracker.py"
    %TRACKER_PY_CMD% -c "import cv2, pykinect_azure, zmq; print('ok')" >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Missing Azure tracker deps on Python 3.10.
        echo Install with:
        echo   py -3.10 -m pip install pykinect_azure opencv-python pyzmq numpy
        pause
        exit /b 1
    )
)

if defined PEPPER_PY_EXE (
    set "PEPPER_PY_CMD=%PEPPER_PY_EXE%"
) else (
    echo [ERROR] Could not find pepper27_32 Python environment.
    echo Expected one of:
    echo   %USERPROFILE%\miniconda3\envs\pepper27_32\python.exe
    echo   %USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe
    echo   C:\Miniconda3\envs\pepper27_32\python.exe
    echo.
    echo Create it with:
    echo   set CONDA_FORCE_32BIT=1
    echo   conda create -n pepper27_32 python=2.7 numpy scipy matplotlib pyzmq pillow -y
    pause
    exit /b 1
)

"%PEPPER_PY_CMD%" -c "import qi, naoqi; print('ok')" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pepper runtime is missing Python 2.7 32-bit support.
    echo This project needs SoftBank NAOqi with Python 2.7 32-bit.
    echo.
    echo Install Miniconda2 32-bit or Python 2.7 32-bit, then run:
    echo   "!PEPPER_PY_CMD!" -c "import qi, naoqi; print('ok')"
    echo.
    echo If the command above fails, the NAOqi libs are not on that Python.
    pause
    exit /b 1
)

"%PEPPER_PY_CMD%" -c "import numpy, scipy, matplotlib, zmq; print('ok')" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Pepper Python is missing required packages.
    echo Using interpreter: !PEPPER_PY_CMD!
    echo Please install in that exact interpreter:
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
echo Pepper Python: "%PEPPER_PY_CMD%"
echo.
echo [1/2] Starting tracker backend: %TRACKER_BACKEND%
echo       (Close this window to shut down the tracker)

:: Clean up stale MediaPipe tracker processes that may still hold ZMQ ports.
:: This avoids "Address in use (tcp://*:1234)" and black/no-camera startup.
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

:: Change to openpose_wrap folder and launch the tracker in a new window
start "Body Tracker" cmd /k "cd /d %~dp0openpose_wrap && %TRACKER_PY_CMD% %TRACKER_SCRIPT% 1>>""%LOG_DIR%\azure_tracker.log"" 2>>&1"

:: Give the tracker 3 seconds to bind the ZMQ socket before the GUI starts
timeout /t 3 /nobreak >nul

echo [2/2] Starting Pepper Control Panel...
echo       (Close this window to shut down the GUI)

:: Launch the GUI in a new window
start "Pepper GUI" cmd /k "cd /d %~dp0pepper_teleoperation && ""!PEPPER_PY_CMD!"" pepper_gui.py 1>>""%LOG_DIR%\pepper_gui.log"" 2>>&1"

echo.
echo Both processes started. Close the individual windows to stop them.
echo If either process fails, open the logs above and share the error text.
pause
