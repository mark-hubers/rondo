# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
# rondo-meta: mode=subprocess provider=anthropic category=flagship value="REQ-115 verified execution — rondo checks the work itself, the anti-lying layer"

"""Rondo REQ-115: verified execution — rondo checks the work ITSELF.

What this demonstrates
----------------------
The anti-lying layer. A pipeline step DECLARES what the world must look like
afterwards (`verify:` block — files that must exist, a command that must exit
clean), and the ENGINE checks those claims in its own process. A model's
`passed: true` cannot override rondo's own observation.

This example needs NO live AI: it injects two fake dispatches — an HONEST one
that does the work, and a LIAR that claims success but does nothing — and
shows rondo catching the liar every time. (The same `verify:` block on a real
Claude step would gate it identically.)

Run::

    cd rondo && uv run python examples/api/verified_step.py
"""

from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

from rondo.pipeline import load_pipeline, run_pipeline


def main() -> int:
    """Run the honest vs liar demonstration and report rondo's verdicts."""
    ws = Path(tempfile.mkdtemp(prefix="rondo-verified-"))
    target = ws / "report.txt"
    yaml_path = ws / "pipe.yaml"
    yaml_path.write_text(
        textwrap.dedent(f"""\
        name: verified-demo
        budget_usd: 1.0
        steps:
          - name: build
            prompt: "create {target} with the analysis"
            on_fail: continue
            verify:
              files: ["{target}"]
        """)
    )
    spec = load_pipeline(yaml_path)

    # -- HONEST: the dispatch actually creates the declared file
    def honest(prompt: str, model: str) -> dict:  # noqa: ARG001
        target.write_text("the work was really done\n")
        return {"status": "done", "raw_output": '{"passed": true}', "cost_usd": 0.0}

    # -- LIAR: claims success loudly, creates nothing
    def liar(prompt: str, model: str) -> dict:  # noqa: ARG001
        return {"status": "done", "raw_output": '{"passed": true, "result": "all done!"}', "cost_usd": 0.0}

    print("== HONEST dispatch (file really created) ==")
    env = run_pipeline(spec, dispatch=honest)
    rec = env["steps"][0]
    print(f"  step status: {rec['status']}   rondo-verified: {rec['verification']['ok']}")
    print(f"  evidence: {rec['verification']['checked_files']}")

    target.unlink(missing_ok=True)  # -- reset for the liar
    print("\n== LIAR dispatch (claims passed=true, does nothing) ==")
    env = run_pipeline(spec, dispatch=liar)
    rec = env["steps"][0]
    print(f"  step status: {rec['status']}   rondo-verified: {rec['verification']['ok']}")
    print(f"  rondo's verdict: {rec['error']}")

    ok = env["steps"][0]["status"] == "error" and not env["steps"][0]["verification"]["ok"]
    print("\n-PASS- the liar's passed=true did not survive rondo's own check" if ok else "-ERROR- liar not caught")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
