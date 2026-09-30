"""The command line from source: python src/dorsal_cli.py --help (installed it's dorsal-cli.exe)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dorsal.cli import main  # noqa: E402

sys.exit(main())
