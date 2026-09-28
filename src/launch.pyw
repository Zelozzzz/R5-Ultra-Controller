"""Double-click launcher (.pyw runs without a console window).
run.bat and the Windows startup entry both start the app through this file."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r5ultra.webui import main  # noqa: E402   (falls back to the Tk window without WebView2)

main(sys.argv[1:])
