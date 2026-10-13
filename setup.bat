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
echo Tip: run this from an "Anaconda Prompt" if conda is not on PATH.
echo.
pause

:: -- Step 1: Check conda is available ----------------------------------------
where conda >nul 2>&1
if errorlevel 1 (
    echo [ERROR] conda not found on PATH.
    echo Open "Anaconda Prompt", cd to this folder, then run setup.bat again.
    goto :end_fail
)
echo [OK] conda found.

:: IMPORTANT: always "call conda ..." — conda is a .bat; without call, this
:: script exits immediately and the window just closes.

:: -- Step 2: Create pepper27_32 if needed ------------------------------------
echo.
echo [1/4] Checking for pepper27_32 environment...
call conda env list | findstr /C:"pepper27_32" >nul 2>&1
if errorlevel 1 (
    echo Creating pepper27_32 (Python 2.7, 32-bit^)...
    set CONDA_FORCE_32BIT=1
    call conda create -n pepper27_32 python=2.7 -y
    if errorlevel 1 (
        echo [ERROR] Failed to create conda environment.
        goto :end_fail
    )
    echo [OK] Environment created.
) else (
    echo [OK] pepper27_32 already exists.
)

:: -- Step 3: Locate pepper27_32 python.exe -----------------------------------
echo.
echo [2/4] Locating pepper27_32 python.exe...
set "PEPPER_PY="
set "CONDA_BASE="

:: Write conda base to a temp file (more reliable than for /f with conda.bat)
set "BASE_FILE=%TEMP%\pepper_conda_base.txt"
call conda info --base > "%BASE_FILE%" 2>nul
if exist "%BASE_FILE%" (
    set /p CONDA_BASE=<"%BASE_FILE%"
    del "%BASE_FILE%" >nul 2>&1
)

if defined CONDA_BASE (
    echo conda base: !CONDA_BASE!
    if exist "!CONDA_BASE!\envs\pepper27_32\python.exe" (
        set "PEPPER_PY=!CONDA_BASE!\envs\pepper27_32\python.exe"
    )
)

if not defined PEPPER_PY if exist "%USERPROFILE%\anaconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=%USERPROFILE%\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "%USERPROFILE%\Anaconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=%USERPROFILE%\Anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY=%USERPROFILE%\miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY=%USERPROFILE%\Miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "%LOCALAPPDATA%\anaconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=%LOCALAPPDATA%\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "%LOCALAPPDATA%\miniconda3\envs\pepper27_32\python.exe" set "PEPPER_PY=%LOCALAPPDATA%\miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "C:\Anaconda3\envs\pepper27_32\python.exe"               set "PEPPER_PY=C:\Anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "C:\Miniconda3\envs\pepper27_32\python.exe"              set "PEPPER_PY=C:\Miniconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "C:\ProgramData\anaconda3\envs\pepper27_32\python.exe"   set "PEPPER_PY=C:\ProgramData\anaconda3\envs\pepper27_32\python.exe"
if not defined PEPPER_PY if exist "C:\ProgramData\miniconda3\envs\pepper27_32\python.exe"  set "PEPPER_PY=C:\ProgramData\miniconda3\envs\pepper27_32\python.exe"

if not defined PEPPER_PY (
    echo [ERROR] Could not locate pepper27_32\python.exe
    echo conda base was: !CONDA_BASE!
    echo.
    echo Manual fix in Anaconda Prompt:
    echo   call conda activate pepper27_32
    echo   python -c "import sys; print(sys.executable)"
    echo   python -m pip install -r requirements_gui.txt
    goto :end_fail
)

echo Using: !PEPPER_PY!

:: Prefer conda run (avoids path/quoting issues); fall back to direct python.exe
echo Installing GUI dependencies...
call conda run -n pepper27_32 python -m pip install --upgrade pip
if errorlevel 1 (
    echo conda run failed, trying direct interpreter...
    "!PEPPER_PY!" -m pip install --upgrade pip
)
call conda run -n pepper27_32 python -m pip install -r "%~dp0requirements_gui.txt"
if errorlevel 1 (
    echo conda run pip failed, trying direct interpreter...
    "!PEPPER_PY!" -m pip install -r "%~dp0requirements_gui.txt"
)
if errorlevel 1 (
    echo [ERROR] Failed to install GUI dependencies.
    goto :end_fail
)
echo [OK] GUI dependencies installed.

:: -- Step 4: Python 3.10 tracker deps ----------------------------------------
echo.
echo [3/4] Checking Python 3.10...
set "TRACKER_OK="
py -3.10 -V >nul 2>&1
if not errorlevel 1 set "TRACKER_OK=1"

if not defined TRACKER_OK (
    echo [WARNING] py -3.10 not found.
    echo Install Python 3.10, then run:
    echo   py -3.10 -m pip install -r requirements_tracker.txt
    echo Skipping tracker dependency install...
    goto :skip_tracker
)
echo [OK] Python 3.10 found.

echo.
echo [4/4] Installing MediaPipe tracker dependencies...
py -3.10 -m pip install -r "%~dp0requirements_tracker.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install tracker dependencies.
    goto :end_fail
)
echo [OK] Tracker dependencies installed.

:skip_tracker

:: -- Step 5: Verify NAOqi bindings -------------------------------------------
echo.
echo Verifying NAOqi / Choregraphe bindings...
set "CHORE_LIB=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\lib"
set "CHORE_BIN=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"

if not exist "%CHORE_LIB%\_qi.pyd" (
    echo [WARNING] Choregraphe NAOqi bindings not found at:
    echo   !CHORE_LIB!
    echo Install Choregraphe Suite 2.5 before controlling Pepper.
) else (
    echo [OK] Choregraphe files found.
    set "PYTHONPATH=%CHORE_LIB%;%PYTHONPATH%"
    set "PATH=%CHORE_BIN%;%PATH%"
    call conda run -n pepper27_32 python -c "import qi, naoqi; print('qi OK')"
    if errorlevel 1 (
        echo [WARNING] qi/naoqi import failed.
        echo NAOqi needs Python 2.7 32-bit. Check that pepper27_32 is 32-bit.
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
exit /b 0

:end_fail
echo.
echo Setup did not finish successfully. Window will stay open.
pause
exit /b 1
