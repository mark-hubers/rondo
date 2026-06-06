# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Build-cut flags — RONDO-332 (SOP-105 P1-6).

ONE constant decides the distribution cut. Release packaging for a public
build flips PUBLIC_BUILD to True; the development tree ships False, so the
author's workflow never changes.

What a public build excludes:
    - auth=max (the Claude-subscription subprocess pattern): refused at
      config validation AND at dispatch env-prep (defense in depth), with
      the api-key alternative named in the message.

Import direction:
    _build.py → stdlib only (leaf — importable from anywhere)
"""

from __future__ import annotations

# -- Flipped to True ONLY by public release packaging. Never at runtime.
PUBLIC_BUILD = False


def is_public_build() -> bool:
    """True when this distribution is a public cut — P1-6 gate source."""
    return PUBLIC_BUILD


# -- sig: mgh-6201.cd.bd955f.03bc.c9b47c
