"""PyInstaller entry script: the package's modules use relative imports, so they can't be
the script itself."""

import sys

from datafuzzy.ot.ui.app import main

sys.exit(main())
