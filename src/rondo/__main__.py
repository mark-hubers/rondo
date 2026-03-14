"""Allow running rondo as a module: python -m rondo."""

import sys

from rondo.cli import main

sys.exit(main())
