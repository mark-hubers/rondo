# rondo-meta: mode=subprocess provider=anthropic category=basic value="Absolute minimal one-task Python round"

"""Rondo example: simplest possible round — one task, no gates."""

from rondo.engine import Round, Task


def build_round() -> Round:
    return Round(
        name="hello",
        tasks=[
            Task(
                name="Say hello",
                description="Verify Rondo can dispatch a task to Claude",
                instruction="Say 'Hello from Rondo!' and confirm you received this prompt.",
                done_when="Response contains 'Hello from Rondo' or equivalent greeting",
            ),
        ],
    )
