# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=budget value="Parallel round under a hard budget cap — spend can never exceed it"

"""Rondo API example: a parallel round that CANNOT overspend its budget.

What this demonstrates
----------------------
``run_parallel`` with ``max_budget_usd`` set — the RONDO-373 budget gate:

* every worker must RESERVE budget atomically before it dispatches
  (no check-then-act window — W workers can't all slip past the cap);
* a cold-start PROBE runs first so the round learns real cost before
  fanning out (waiters hold; they never admit blind on a timeout);
* $0-cost dispatches (Claude max-auth) are real samples — a free round
  fans out fully instead of serializing;
* tasks refused for budget come back as ``ERR_BUDGET_EXCEEDED`` —
  refused BEFORE dispatch, never silently charged.

Uses **live** dispatch (subprocess Claude). On a max-auth setup the tasks
cost $0, so all of them run and the cap is trivially honored — the printout
shows whatever actually happened, including refusals on paid setups.

Run::

    cd rondo && uv run python examples/api/budget_guarded_parallel.py
"""

from __future__ import annotations

import sys

from example_dispatch import banner

from rondo.config import RondoConfig
from rondo.engine import Round, Task
from rondo.runner import run_round

# -- A cap small enough that PAID dispatches would have to be refused past it;
# -- on the free max-auth path every task fits ($0 each) and all run.
BUDGET_CAP_USD = 0.25


def main() -> int:
    """Run 4 tiny tasks in parallel under a hard budget cap; print the truth."""
    tasks = [
        Task(
            name=f"haiku-{i}",
            instruction=f"Reply with exactly one short line: 'budget demo task {i} ok'.",
            done_when="The single line is returned.",
        )
        for i in range(1, 5)
    ]
    round_def = Round(name="budget-guarded-demo", tasks=tasks)
    config = RondoConfig(workers=4, throttle_sec=0.0, max_budget_usd=BUDGET_CAP_USD)

    print(banner(f"Parallel round, 4 workers, hard cap ${BUDGET_CAP_USD:.2f} (RONDO-373 gate)"))
    result = run_round(round_def, config)

    spent = sum(tr.cost_usd or 0.0 for tr in result.task_results if tr.status == "done")
    refused = [tr for tr in result.task_results if tr.error_code == "ERR_BUDGET_EXCEEDED"]
    for tr in result.task_results:
        cost = f"${tr.cost_usd:.4f}" if tr.cost_usd else "$0"
        note = tr.error_code or ""
        print(f"   {tr.task_name:<10} {tr.status:<8} {cost:<9} {note}")
    print(f"   round status={result.status}  spent=${spent:.4f}  refused-for-budget={len(refused)}")

    if spent > BUDGET_CAP_USD:
        print(banner(f"-ERROR- spent ${spent:.4f} EXCEEDS the ${BUDGET_CAP_USD:.2f} cap — gate broken"))
        return 1
    print(banner(f"-PASS- spend ${spent:.4f} <= cap ${BUDGET_CAP_USD:.2f} — the gate held"))
    return 0


if __name__ == "__main__":
    sys.exit(main())


# -- sig: mgh-6201.cd.bd955f.68e4.9f469c
