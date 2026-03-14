"""Rondo example: auto task gate + interactive task."""

from pathlib import Path

from rondo.engine import Gate, Round, Task

TARGET = "README.md"


def build_round() -> Round:
    return Round(
        name="file-check",
        pre_gates=[
            Gate(
                "Target file exists",
                check_fn=lambda: (Path(TARGET).exists(), f"{TARGET} {'found' if Path(TARGET).exists() else 'missing'}"),
            ),
        ],
        tasks=[
            Task(
                name="Count lines",
                description=f"Auto-count lines in {TARGET}",
                auto_fn=lambda: (True, f"{sum(1 for _ in open(TARGET))} lines"),
            ),
            Task(
                name="Summarize file",
                description=f"Ask Claude to summarize {TARGET}",
                instruction=f"Read {TARGET} and write a 2-sentence summary.",
                context_files=[TARGET],
                done_when="2-sentence summary of the file's purpose",
                model="haiku",
            ),
        ],
    )
