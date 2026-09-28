"""
Compatibility shim. Version 1 lived in this single file; v2 moved the code
into the r5ultra package. Older "Run on Windows startup" entries point here,
so this keeps them working (and the app updates the entry on first launch).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r5ultra.webui import main  # noqa: E402   (falls back to the Tk window without WebView2)

main(sys.argv[1:])
