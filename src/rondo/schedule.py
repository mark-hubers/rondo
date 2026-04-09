# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Rondo schedule — generate launchd plists for recurring dispatches.

REQ-101: automated scheduling. Creates macOS launchd plists
that run `rondo run` on a cron-like schedule.

Import direction:
    schedule.py → no rondo imports (standalone utility)
"""

from __future__ import annotations

from pathlib import Path

_PLIST_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.rondo.{name}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>StartCalendarInterval</key>
    <dict>
{interval_xml}
    </dict>
    <key>StandardOutPath</key>
    <string>{log_path}</string>
    <key>StandardErrorPath</key>
    <string>{log_path}</string>
    <key>WorkingDirectory</key>
    <string>{work_dir}</string>
</dict>
</plist>"""

_INTERVALS = {
    "hourly": "        <key>Minute</key>\n        <integer>0</integer>",
    "daily": "        <key>Hour</key>\n        <integer>3</integer>\n        <key>Minute</key>\n        <integer>0</integer>",
    "weekly": "        <key>Weekday</key>\n        <integer>1</integer>\n        <key>Hour</key>\n        <integer>3</integer>\n        <key>Minute</key>\n        <integer>0</integer>",
    "monthly": "        <key>Day</key>\n        <integer>1</integer>\n        <key>Hour</key>\n        <integer>3</integer>\n        <key>Minute</key>\n        <integer>0</integer>",
}


def generate_plist(
    *,
    name: str,
    command: str,
    args: list[str],
    interval: str = "weekly",
    output_dir: str = "",
    work_dir: str = "",
) -> str:
    """Generate a macOS launchd plist for scheduled Rondo dispatch.

    Returns the plist XML as a string. Optionally writes to output_dir.
    """
    # -- RONDO-216 C6 (Cursor finding): escape XML special chars in interpolated values.
    # -- Unescaped strings in plist XML can cause malformed plists or injection.
    from html import escape as _xml_escape  # pylint: disable=import-outside-toplevel

    all_args = [command] + args
    args_xml = "\n".join(f"        <string>{_xml_escape(a)}</string>" for a in all_args)
    interval_xml = _INTERVALS.get(interval, _INTERVALS["weekly"])
    log_dir = Path.home() / ".rondo" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    log_path = str(log_dir / f"{name}.log")
    work_dir = work_dir or str(Path.home())

    plist = _PLIST_TEMPLATE.format(
        name=_xml_escape(name),
        args_xml=args_xml,
        interval_xml=interval_xml,
        log_path=_xml_escape(log_path),
        work_dir=_xml_escape(work_dir),
    )

    if output_dir:
        out_path = Path(output_dir) / f"com.rondo.{name}.plist"
        out_path.write_text(plist, encoding="utf-8")

    return plist


# -- sig: mgh-6201.cd.bd955f.a101.d30101
