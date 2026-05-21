@echo off
setlocal
cd /d "%~dp0"
title R5 Ultra Flasher

python "src\flash_wizard.py"
if errorlevel 1 (
    echo.
    echo  flash_wizard.py exited with an error.
    pause
)
endlocal
