# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Regression: an unlisted worker-exception type crashes the whole parallel round.

VER-001 verification matrix — holistic-review finding #8 (cursor-review lens),
quality-checklist item 6.

THE BUG in src/rondo/parallel.py (pinned here, NOT fixed here):

    _collect_future() catches only (OSError, ValueError, RuntimeError), while
    _dispatch_worker re-raises EVERYTHING after refunding its budget reservation.
    So a dispatch_task_routed that raises KeyError or TypeError — the malformed
    routing/config (programmer-error) class — propagates out of future.result(),
    kills run_parallel entirely, and every OTHER task's result is lost.

That violates Rondo-REQ-101 req 8 ("Single task failure doesn't crash others")
and Rondo-STD-110 C7 ("exception in thread → error result, not crash").

THE CONTRACT these tests pin: ANY Exception raised by one task's dispatch becomes
that task's error TaskResult (status error, message preserved); the OTHER tasks
still complete and the round returns normally. KeyboardInterrupt / SystemExit are
deliberately NOT covered here — BaseException stays fatal by design, so we never
assert that those get converted.

All three tests drive the REAL run_parallel end-to-end and assert OBSERVABLE
outcomes (it returns, task statuses, error message, result count) — never an
internal method name — so a fix that reshapes _collect_future still satisfies
them. No budget is set in config, so the budget gate stays out of play.
"""

from unittest.mock import patch

import pytest

from rondo.config import RondoConfig
from rondo.engine import DispatchUsage, Round, Task, TaskResult
from rondo.parallel import run_parallel

# -- 4 tasks / 4 workers: the named victim (t2) raises; the rest return cheap.
_WORKERS = 4
_VICTIM = "t2"


def _make_tasks(n: int) -> list[Task]:
    """Build n minimal valid interactive tasks named t1..tn."""
    return [Task(name=f"t{i + 1}", instruction=f"do {i + 1}", done_when=f"done {i + 1}") for i in range(n)]


def _done_result(task: Task) -> tuple[TaskResult, DispatchUsage]:
    """Build the cheap (cost 0) done (TaskResult, DispatchUsage) a healthy seam returns."""
    return (
        TaskResult(
            task_name=task.name,
            status="done",
            raw_output='{"status":"done"}',
            model="sonnet",
            auth_mode="max",
            timestamp="2026-06-08T00:00:00Z",
            cost_usd=0.0,
        ),
        DispatchUsage(task_name=task.name, model="sonnet", cost_usd=0.0),
    )


def _raising_dispatch_factory(exc: BaseException):
    """Build a dispatch seam where the victim task raises `exc`; the rest return done."""

    def _dispatch(task: Task, config: RondoConfig, **kwargs) -> tuple[TaskResult, DispatchUsage]:
        if task.name == _VICTIM:
            raise exc
        return _done_result(task)

    return _dispatch


@pytest.mark.parametrize(
    "exc",
    [KeyError("boom"), TypeError("boom")],
    ids=["KeyError", "TypeError"],
)
def test_unlisted_worker_exception_becomes_error_result(exc: BaseException) -> None:
    """An unlisted exception type from one task must not crash the parallel round.

    The victim (t2) raises an exception type NOT in _collect_future's catch tuple
    (KeyError / TypeError — the malformed-routing class). On current code that
    propagates out of future.result() and run_parallel raises, losing every other
    task's result. The contract: run_parallel returns, t2 becomes an error result
    with its message preserved, and the other three tasks still complete — pinning
    finding #8 (Rondo-REQ-101 req 8, Rondo-STD-110 C7).
    """
    round_def = Round(name="isolation", tasks=_make_tasks(_WORKERS))
    config = RondoConfig(workers=_WORKERS, throttle_sec=0.0)

    with patch("rondo.parallel.dispatch_task_routed", side_effect=_raising_dispatch_factory(exc)):
        result = run_parallel(round_def, config)

    assert len(result.task_results) == _WORKERS, (
        f"all {_WORKERS} tasks must have a result entry; got {len(result.task_results)} "
        f"({type(exc).__name__} propagated and lost the round — finding #8)"
    )
    done = [tr for tr in result.task_results if tr.status == "done"]
    assert len(done) == _WORKERS - 1, (
        f"the {_WORKERS - 1} healthy tasks must still complete; got {len(done)} done "
        f"after {type(exc).__name__} from {_VICTIM} (finding #8)"
    )
    victim = next(tr for tr in result.task_results if tr.task_name == _VICTIM)
    assert victim.status == "error", (
        f"{_VICTIM} must become an error result, not crash the round; status={victim.status!r} "
        f"({type(exc).__name__} — finding #8)"
    )
    assert victim.error_message, f"{_VICTIM}'s error result must carry a non-empty message ({type(exc).__name__})"


def test_listed_runtimeerror_still_becomes_error_result() -> None:
    """Rail: a RuntimeError (an ALREADY-listed type) keeps its error-result behavior.

    This guards the existing path against regression — a fix that widens the catch
    must not break the type that already worked. The victim raises RuntimeError;
    run_parallel returns, t2 is an error result with a message, and the other three
    tasks still complete.
    """
    round_def = Round(name="isolation-rail", tasks=_make_tasks(_WORKERS))
    config = RondoConfig(workers=_WORKERS, throttle_sec=0.0)

    with patch(
        "rondo.parallel.dispatch_task_routed",
        side_effect=_raising_dispatch_factory(RuntimeError("boom")),
    ):
        result = run_parallel(round_def, config)

    assert len(result.task_results) == _WORKERS, "all tasks must have a result entry (RuntimeError rail)"
    done = [tr for tr in result.task_results if tr.status == "done"]
    assert len(done) == _WORKERS - 1, f"the {_WORKERS - 1} healthy tasks must still complete (RuntimeError rail)"
    victim = next(tr for tr in result.task_results if tr.task_name == _VICTIM)
    assert victim.status == "error", f"{_VICTIM} must be an error result (RuntimeError rail); status={victim.status!r}"
    assert victim.error_message, f"{_VICTIM}'s error result must carry a non-empty message (RuntimeError rail)"


# -- sig: mgh-6201.cd.bd955f.a875.ec8735
