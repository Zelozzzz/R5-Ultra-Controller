"""Runs the firmware wizard from the source tree (flash.bat uses this).
The wizard itself lives in r5ultra/wizard.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r5ultra.wizard import run  # noqa: E402

run()
