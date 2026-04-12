# rondo-meta: mode=subprocess provider=anthropic category=review value="Forward/reverse/sideways review strategy on a demo file"

"""Rondo review: use Rondo to review its own demo_pipeline.py.

Eating our own dog food — multi-directional review of the demo code
using the same tool the demo demonstrates.
"""

from pathlib import Path

from rondo.engine import Gate, Round, Task

DEMO_FILE = "examples/demo_pipeline.py"
EXAMPLES_DIR = "examples/"
TESTS_DIR = "tests/"


def _demo_exists() -> tuple[bool, str]:
    """Gate: verify demo file exists."""
    if Path(DEMO_FILE).exists():
        lines = len(Path(DEMO_FILE).read_text().splitlines())
        return (True, f"{DEMO_FILE} exists ({lines} lines)")
    return (False, f"{DEMO_FILE} not found")


def build_round() -> Round:
    return Round(
        name="review-demo-pipeline",
        pre_gates=[
            Gate("Demo file exists", check_fn=_demo_exists, blocking=True),
        ],
        tasks=[
            # -- FORWARD: Does the code do what it claims?
            Task(
                name="forward-review",
                description="Forward review: does the demo work correctly?",
                instruction=(
                    f"Read {DEMO_FILE} and review it FORWARD (top to bottom):\n\n"
                    "1. Does each step's gate correctly check the previous step's output?\n"
                    "2. Does the JSON path in each gate match what save_result() would write?\n"
                    "3. Are the instructions clear enough for Claude to produce useful output?\n"
                    "4. Does build_round() return Step 1 and build_phases() return all 4?\n"
                    "5. Are there any bugs, crashes, or unhandled edge cases?\n\n"
                    "Output: table of finding, severity (CRITICAL/WARNING/NIT), location, suggested fix"
                ),
                context_files=[DEMO_FILE],
                done_when="Table of findings with severity and suggested fixes",
                model="sonnet",
            ),
            # -- REVERSE: Walk bottom-up, check assumptions
            Task(
                name="reverse-review",
                description="Reverse review: walk bottom-up checking assumptions",
                instruction=(
                    f"Read {DEMO_FILE} and review it REVERSE (bottom to top):\n\n"
                    "Start at Step 4 (verify) and work backwards:\n"
                    "1. Step 4 assumes fixes were applied — what if Step 3 failed?\n"
                    "2. Step 3 assumes review produced priorities — what if Step 2 was empty?\n"
                    "3. Step 2 assumes scan found issues — what if Step 1 found nothing?\n"
                    "4. Step 1 assumes src/ exists — what if it doesn't?\n\n"
                    "For each assumption: is it guarded by a gate? Is the gate correct?\n"
                    "Output: table of assumption, guarded (yes/no), fix needed"
                ),
                context_files=[DEMO_FILE],
                done_when="Table of assumptions with guard status and fixes",
                model="sonnet",
            ),
            # -- SIDEWAYS: Compare against other examples
            Task(
                name="sideways-review",
                description="Sideways review: compare patterns against other examples",
                instruction=(
                    f"Read {DEMO_FILE} and compare it against the other examples in {EXAMPLES_DIR}:\n\n"
                    "Check these conventions:\n"
                    "1. Does it follow the same import pattern? (from rondo.engine import ...)\n"
                    "2. Does it have the same docstring style? (module + function docstrings)\n"
                    "3. Does it use the same gate return pattern? ((bool, str) tuples)\n"
                    "4. Are function names consistent with other examples? (_prefixed for private)\n"
                    "5. Is there a corresponding test in tests/test_examples.py?\n"
                    "6. Does it handle edge cases the same way other examples do?\n\n"
                    "Output: table of convention, matches (yes/no), detail"
                ),
                context_files=[DEMO_FILE, EXAMPLES_DIR, TESTS_DIR],
                done_when="Convention comparison table showing matches and mismatches",
                model="sonnet",
            ),
        ],
    )
