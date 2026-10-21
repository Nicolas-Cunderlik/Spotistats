"""Script entry point for PyInstaller (app.spec) - same as `python -m spotistats`."""

import sys

from spotistats.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
