@echo off
title NAO Dance Study - Operator Panel
setlocal EnableDelayedExpansion

:: Opens the browser control panel on the "NAO Study" tab (no body tracker needed).
:: Optional args are passed through, e.g.:  Start_NAO_Study.bat --ip 192.168.1.70 --connect
:: Old Tk study window:                      set "STUDY_SCRIPT=nao_study_gui.py" below
set "STUDY_SCRIPT=web_app.py"

set "CHORE_LIB=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\lib"
set "CHORE_BIN=C:\Program Files (x86)\Softbank Robotics\Choregraphe Suite 2.5\bin"

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
for %%B in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "C:\Anaconda3" "C:\Miniconda3" "C:\ProgramData\anaconda3" "C:\ProgramData\miniconda3") do (
    if not defined PEPPER_PY_EXE if exist "%%~B\envs\pepper27_32\python.exe" set "PEPPER_PY_EXE=%%~B\envs\pepper27_32\python.exe"
)

if not defined PEPPER_PY_EXE (
    echo [ERROR] Could not find the pepper27_32 Python environment. Run setup.bat first.
    pause
    exit /b 1
)

if exist "%CHORE_LIB%\_qi.pyd" (
    set "PYTHONPATH=%CHORE_LIB%;%PYTHONPATH%"
    set "PATH=%CHORE_BIN%;%PATH%"
) else (
    echo [WARNING] Choregraphe NAOqi bindings not found - only Simulation mode will work.
)

cd /d "%~dp0pepper_teleoperation"
if /I "%STUDY_SCRIPT%"=="web_app.py" (
    "!PEPPER_PY_EXE!" -u web_app.py --tab study --no-tracker --no-voice %*
) else (
    "!PEPPER_PY_EXE!" nao_study_gui.py %*
)
if errorlevel 1 pause
