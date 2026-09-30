"""Starts Dorsal. .pyw so no console window pops up."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dorsal.webui import main  # noqa: E402

main(sys.argv[1:])
