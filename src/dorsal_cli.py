"""Dorsal's command line from the source tree. Usage: python src/dorsal_cli.py --help
(or dorsal.bat --help). The installed app ships this as dorsal-cli.exe."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from r5ultra.cli import main  # noqa: E402

sys.exit(main())
