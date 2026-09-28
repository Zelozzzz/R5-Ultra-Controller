@echo off
setlocal
cd /d "%~dp0"
title Dorsal - R5 Ultra Firmware Wizard
python "src\flash_wizard.py"
endlocal
