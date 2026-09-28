"""`python -m r5ultra` opens the GUI; `python -m r5ultra <command>` runs the CLI."""

import sys

if len(sys.argv) > 1 and sys.argv[1] not in ("--tray", "--classic"):
    from .cli import main
else:
    from .webui import main

sys.exit(main())
