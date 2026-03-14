# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Allow running rondo as a module: python -m rondo."""

import sys

from rondo.cli import main

sys.exit(main())

# -- sig: ace-82f2ab15
