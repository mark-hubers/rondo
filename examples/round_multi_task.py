"""Rondo example: 3 tasks with model hints, pre/post gates. Parallel-safe."""
from pathlib import Path

from rondo.engine import Gate, Round, Task


def build_round(target_dir: str = ".") -> Round:
    return Round(
        name="code-survey",
        pre_gates=[
            Gate(
                "Directory exists",
                check_fn=lambda: (Path(target_dir).is_dir(), f"{target_dir} exists"),
            ),
        ],
        tasks=[
            Task(
                name="Count Python files",
                description="Auto-count .py files",
                auto_fn=lambda: (True, f"{len(list(Path(target_dir).rglob('*.py')))} files"),
            ),
            Task(
                name="Find TODOs",
                description="Search for TODO comments in source",
                instruction=f"Search all .py files under {target_dir} for TODO comments. List each with file and line number.",
                context_files=[target_dir],
                done_when="List of TODOs with file:line, or 'No TODOs found'",
                model="haiku",
            ),
            Task(
                name="Architecture summary",
                description="Describe the module structure",
                instruction=f"Read the top-level .py files in {target_dir} and describe the architecture in 5 bullet points.",
                context_files=[target_dir],
                done_when="5-bullet architecture summary",
                model="sonnet",
            ),
        ],
        post_gates=[
            Gate(
                "All tasks complete",
                check_fn=lambda: (True, "Post-gate placeholder"),
                blocking=False,
            ),
        ],
    )
