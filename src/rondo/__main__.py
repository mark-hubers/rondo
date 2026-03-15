# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Allow running rondo as a module: python -m rondo."""

import sys

from rondo.cli import main

sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.5b63.82f2ab
