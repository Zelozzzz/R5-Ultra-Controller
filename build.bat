@echo off
REM Builds Dorsal.exe into dist\Dorsal (needs: pip install pyinstaller)
cd /d "%~dp0"
python packaging\build.py
