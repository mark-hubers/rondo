#!/bin/bash
# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=cli provider=all category=operations value="The night watchman: one schedulable command that sweeps drift + retryq + reliability and ALERTS instead of waiting to be asked."
#
# Example 07 is the morning check YOU run. This is the check that runs when
# you DON'T — `rondo nightly` composes drift + retry sweep + 7d reliability
# into one sweep with an exit-code contract (0 = green, 1 = alerts) and
# fires a macOS notification on any alert. Schedule it once; a silent
# overnight fleet failure becomes a banner by morning.
#
# Everything here is FREE (catalog fetches + local data, zero dispatches).

set -euo pipefail

echo "=== CLI Example 08: Nightly Watchdog (the night watchman) ==="

echo "[1/3] One-shot sweep — drift + retryq + reliability, alerts inline"
echo "      (--no-notify keeps this demo from popping a notification)"
rondo nightly --no-notify || true
echo "      Exit code 0 = fleet green, 1 = at least one alert (scriptable)."
echo "      First real run flagged: 7d success 94% — one point under the 95%"
echo "      target. The watchdog reports the truth, not comfort."
echo

echo "[2/3] JSON mode — same sweep, machine-readable for your own automation"
rondo nightly --no-notify --json | head -15 || true
echo

echo "[3/3] Schedule it — daily 03:00 launchd job (prints plist; --install to arm)"
rondo schedule --cmd nightly --interval daily --name nightly-watchdog | head -12
echo "      Arm it:   rondo schedule --cmd nightly --interval daily --name nightly-watchdog --install"
echo "      Then:     launchctl load ~/Library/LaunchAgents/com.rondo.nightly-watchdog.plist"
echo "      Logs:     ~/.rondo/logs/nightly-watchdog.log"
echo

echo "-PASS- nightly watchdog example completed"
