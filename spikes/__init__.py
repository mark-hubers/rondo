# SPDX-FileCopyrightText: 2026 Mark G. Hubers / HubersTech
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Rondo — Python-orchestrated AI work.

The conductor. Python runs structured rounds of tasks.
Claude reads the instructions and does the work.
State persists through JSON and DB — survives compaction.

Package structure:
    rondo.engine     — Core: Gate, Task, Round, run/resume/save/load
    rondo.dispatch   — Mode 2/3: CLI + API task dispatch
    rondo.monitor    — Dashboard, tmux, escalation queue
    rondo.demo       — Working demos

Used by:
    ob/rounds.py     — OB round definitions (survey, design, fit-check)
    ob/demo_round.py — OB-specific demos

"Python is the conductor. Claude is the orchestra. The conversation is the wire."
"""
