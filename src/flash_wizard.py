"""The console firmware wizard, from source."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r5ultra.wizard import run  # noqa: E402

run()
