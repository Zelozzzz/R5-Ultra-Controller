@echo off
setlocal
cd /d "%~dp0"

REM Install dependencies quietly if missing
python -m pip install --quiet --disable-pip-version-check -r requirements.txt >nul 2>&1

REM Launch the GUI without a console window when possible
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw "src\controller.py"
) else (
    start "" python "src\controller.py"
)
endlocal
