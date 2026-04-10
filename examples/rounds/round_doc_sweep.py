"""Rondo example: parallel documentation sweep across multiple files.

Pattern: multiple independent tasks that can run in parallel (workers > 1).
Shows: parallel-safe tasks, per-task model hints, context_files per task.
Auto-filters to files that actually exist — safe to run in any project.
"""

from pathlib import Path

from rondo.engine import Round, Task


def build_round(files: list[str] | None = None) -> Round:
    if files is None:
        # -- Common docs — filtered to what actually exists
        candidates = ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE"]
        files = [f for f in candidates if Path(f).exists()]
        if not files:
            files = ["README.md"]  # -- fallback: Claude will note it's missing

    tasks = []
    for filepath in files:
        tasks.append(
            Task(
                name=f"Document {filepath}",
                description=f"Review and improve {filepath}",
                instruction=(
                    f"Read {filepath} and improve it:\n"
                    "1. Fix any broken links or outdated references\n"
                    "2. Add missing sections if obvious gaps exist\n"
                    "3. Ensure consistent formatting (headers, lists, code blocks)\n"
                    "4. Keep the same voice and style"
                ),
                context_files=[filepath],
                done_when=f"{filepath} reviewed and improved with tracked changes",
                model="haiku",
            ),
        )

    return Round(
        name="doc-sweep",
        tasks=tasks,
    )
