@echo off
REM Dorsal from the command line, e.g.:  dorsal color FF8800   ^|   dorsal effect candle   ^|   dorsal --help
python "%~dp0src\dorsal_cli.py" %*
