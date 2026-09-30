"""python -m dorsal opens the app, python -m dorsal <command> runs the command line."""

import sys

if len(sys.argv) > 1 and sys.argv[1] not in ("--tray",):
    from .cli import main
else:
    from .webui import main

sys.exit(main())
