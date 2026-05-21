@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title R5 Ultra Controller — Installer

echo.
echo   R5 Ultra Controller — Installer
echo.

REM ── Step 1: Python ──────────────────────────────────────────────
echo   Checking for Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo   Python is not installed, or not on your PATH.
    echo.
    echo   Install Python 3.10 or newer from:
    echo     https://www.python.org/downloads/
    echo.
    echo   During install, tick the box "Add Python to PATH",
    echo   then re-run this installer.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Found Python !PYVER!
echo.

REM ── Step 2: pip ─────────────────────────────────────────────────
echo   Checking pip...
python -m pip --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo   pip is missing. Trying to bootstrap it...
    python -m ensurepip --upgrade
    if errorlevel 1 (
        echo.
        echo   Could not bootstrap pip automatically. Try:
        echo     python -m ensurepip --upgrade
        echo.
        pause
        exit /b 1
    )
)
echo   OK
echo.

REM ── Step 3: dependencies ───────────────────────────────────────
echo   Installing dependencies from requirements.txt...
echo   (this may take a minute on the first run)
echo.
python -m pip install --upgrade --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
    echo.
    echo   pip install failed. Read the messages above to see why.
    echo   The most common cause is no internet connection.
    echo.
    pause
    exit /b 1
)
echo.

REM ── Step 4: smoke test ─────────────────────────────────────────
echo   Verifying everything imports cleanly...
python -c "import hid, intelhex, pystray, PIL, tkinter" 2>nul
if errorlevel 1 (
    echo.
    echo   One of the modules failed to import. Run:
    echo     python -c "import hid, intelhex, pystray, PIL, tkinter"
    echo   to see which one.
    echo.
    pause
    exit /b 1
)
echo   OK
echo.

REM ── Done ───────────────────────────────────────────────────────
echo   Install complete.
echo.
echo   Next steps:
echo.
echo     run.bat      launch the controller GUI
echo     flash.bat    flash the patched firmware (do this first)
echo.
echo   You only need to run this installer once.
echo.
pause
endlocal
