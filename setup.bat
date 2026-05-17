@echo off
title Pepper Teleoperation - One-Time Setup
setlocal EnableDelayedExpansion

echo ============================================================
echo   Pepper Teleoperation - Dependency Setup
echo ============================================================
echo.
echo This script will:
echo   1. Create the pepper27_32 conda environment (Python 2.7 32-bit)
echo   2. Install GUI dependencies into it
echo   3. Install MediaPipe tracker dependencies for Python 3.10
echo.
echo Prerequisites that must already be installed:
echo   - Choregraphe Suite 2.5  (provides qi/naoqi Python bindings)
echo   - Miniconda or Anaconda  (for the Python 2.7 32-bit environment)
echo   - Python 3.10            (for the MediaPipe tracker)
echo.
pause

:: -- Step 1: Check conda is available ----------------------------------------
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found on PATH.
    echo Please install Miniconda from https://docs.conda.io/en/latest/miniconda.html
    echo Then re-run this script from an Anaconda Prompt, or add conda to your PATH.
    pause
    exit /b 1
)
echo [OK] conda found.

:: -- Step 2: Create or update pepper27_32 env --------------------------------
conda env list | findstr /C:"pepper27_32" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [1/4] Creating pepper27_32 environment (Python 2.7, 32-bit)...
    set CONDA_FORCE_32BIT=1
    conda create -n pepper27_32 python=2.7 -y
    if errorlevel 1 (
        echo [ERROR] Failed to create conda environment.
        echo Make sure Miniconda is installed and try running from an Anaconda Prompt.
        pause
        exit /b 1
    )
    echo [OK] Environment created.
) else (
    echo [OK] pepper27_32 environment already exists - skipping creation.
)

:: -- Step 3: Install GUI pip packages into pepper27_32 -----------------------
echo.
echo [2/4] Installing GUI dependencies into pepper27_32...

:: Find the conda Python executable
set "PEPPER_PY="
if exist "%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe"
if exist "%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe"
if exist "C:\Miniconda3\envs\pepper27_32\python.exe"              set "PEPPER_PY=C:\Miniconda3\envs\pepper27_32\python.exe"
if exist "C:\ProgramData\miniconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=C:\ProgramData\miniconda3\envs\pepper27_32\python.exe"

if not defined PEPPER_PY (
    echo [ERROR] Could not locate pepper27_32\python.exe.
    echo Common locations checked:
    echo   %%USERPROFILE%%\miniconda3\envs\pepper27_32\
    echo   C:\Miniconda3\envs\pepper27_32\
    echo   C:\ProgramData\miniconda3\envs\pepper27_32\
    echo.
    echo If your Miniconda is installed elsewhere, install manually:
    echo   set CONDA_FORCE_32BIT=1
    echo   conda activate pepper27_32
    echo   pip install -r requirements_gui.txt
    pause
    exit /b 1
)

echo Using: !PEPPER_PY!
"!PEPPER_PY!" -m pip install --upgrade pip
"!PEPPER_PY!" -m pip install -r requirements_gui.txt
if errorlevel 1 (
    echo [ERROR] Failed to install GUI dependencies.
    pause
    exit /b 1
)
echo [OK] GUI dependencies installed.

:: -- Step 4: Check Python 3.10 ------------------------------------------------
echo.
echo [3/4] Checking Python 3.10...
py -3.10 -c "import sys; print(sys.version)" >nul 2>&1
if errorlevel 1 (
    echo [WARNING] py -3.10 not found.
    echo Download Python 3.10 from https://www.python.org/downloads/
    echo After installing, re-run this script or install tracker deps manually:
    echo   py -3.10 -m pip install -r requirements_tracker.txt
    echo.
    echo Skipping tracker dependency install...
    goto :skip_tracker
)
echo [OK] Python 3.10 found.

echo.
echo [4/4] Installing MediaPipe tracker dependencies...
py -3.10 -m pip install -r requirements_tracker.txt
if errorlevel 1 (
    echo [ERROR] Failed to install tracker dependencies.
    pause
    exit /b 1
)
echo [OK] Tracker dependencies installed.

:skip_tracker

:: -- Step 5: Verify NAOqi bindings -------------------------------------------
echo.
echo Verifying NAOqi bindings...
set "CHORE_LIB=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\lib"
set "CHORE_BIN=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"

if not exist "%CHORE_LIB%\_qi.pyd" (
    echo.
    echo [WARNING] Choregraphe NAOqi bindings not found at:
    echo   !CHORE_LIB!
    echo.
    echo You must install Choregraphe Suite 2.5 to control Pepper.
    echo Download from: https://community.softbankrobotics.com/
    echo.
    echo The tracker and GUI will still launch, but connecting to Pepper will fail
    echo until Choregraphe is installed.
) else (
    echo [OK] Choregraphe NAOqi bindings found.
    set "PYTHONPATH=%CHORE_LIB%;%PYTHONPATH%"
    set "PATH=%CHORE_BIN%;%PATH%"
    "!PEPPER_PY!" -c "import qi, naoqi; print('qi OK')" >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] qi/naoqi import failed even though Choregraphe files exist.
        echo Make sure you are using the 32-bit Python environment - NAOqi only works
        echo with Python 2.7 32-bit.
    ) else (
        echo [OK] qi and naoqi import successfully.
    )
)

echo.
echo ============================================================
echo   Setup complete!
echo   Run  Start_Pepper_Azure.bat  to launch the system.
echo ============================================================
echo.
pause
