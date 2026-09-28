@echo off
setlocal
cd /d "%~dp0"

REM First run on a new PC? Install dependencies only if they're missing.
python -c "import hid, intelhex, pystray, PIL, customtkinter, tkinter" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies, one moment...
    python -m pip install --quiet --disable-pip-version-check -r requirements.txt
    if errorlevel 1 (
        echo Setup failed. Run install.bat to see the problem.
        pause
        exit /b 1
    )
)

REM pythonw runs the app without a console window.
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "src\launch.pyw" %*
) else (
    start "" python "src\launch.pyw" %*
)
endlocal
