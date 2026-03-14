"""Tests for rondo.engine — REQ-001 reqs 1-11, 23, 29, 31, 46.

VER-001 verification matrix: every test maps to a numbered requirement.
TDD: these tests are written BEFORE engine.py exists.
"""
import json
import sys
from pathlib import Path

import pytest

# -- Add rondo/src to path so we can import rondo
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rondo.engine import (
    Gate,
    GateResult,
    Round,
    RoundResult,
    Task,
    TaskResult,
    calculate_round_status,
    is_round_complete,
    is_terminal,
    round_state_from_dict,
    round_state_to_dict,
    run_gate,
    run_gates,
    should_proceed,
    TERMINAL_STATES,
)


# -- REQ-001 Req 1: Round contains name, gates, tasks
class TestRoundStructure:

    def test_round_has_name(self):
        r = Round(name="test-round")
        assert r.name == "test-round"

    def test_round_has_tasks(self):
        t = Task(name="t1")
        r = Round(name="r", tasks=[t])
        assert len(r.tasks) == 1
        assert r.tasks[0].name == "t1"

    def test_round_has_pre_gates(self):
        g = Gate(name="g1", check_fn=lambda: (True, "ok"))
        r = Round(name="r", pre_gates=[g])
        assert len(r.pre_gates) == 1

    def test_round_has_post_gates(self):
        g = Gate(name="g1", check_fn=lambda: (True, "ok"))
        r = Round(name="r", post_gates=[g])
        assert len(r.post_gates) == 1

    def test_round_defaults_empty(self):
        r = Round(name="r")
        assert r.tasks == []
        assert r.pre_gates == []
        assert r.post_gates == []


# -- REQ-001 Req 2: Task has name, mode, status
class TestTaskFields:

    def test_task_has_name(self):
        t = Task(name="my-task")
        assert t.name == "my-task"

    def test_task_has_mode_default_interactive(self):
        t = Task(name="t")
        assert t.mode == "interactive"

    def test_task_has_status_default_pending(self):
        t = Task(name="t")
        assert t.status == "pending"

    def test_task_has_description(self):
        t = Task(name="t", description="A test task")
        assert t.description == "A test task"

    def test_task_description_defaults_empty(self):
        t = Task(name="t")
        assert t.description == ""


# -- REQ-001 Req 3: Interactive task — Do/Read/Done (three-field contract)
class TestThreeFieldContract:

    def test_instruction_field(self):
        t = Task(name="t", instruction="Do this thing")
        assert t.instruction == "Do this thing"

    def test_context_files_field(self):
        t = Task(name="t", context_files=["a.py", "b.py"])
        assert t.context_files == ["a.py", "b.py"]

    def test_done_when_field(self):
        t = Task(name="t", done_when="Output contains X")
        assert t.done_when == "Output contains X"

    def test_all_three_fields(self):
        t = Task(
            name="full",
            instruction="Read the file and summarize",
            context_files=["README.md"],
            done_when="2-sentence summary",
        )
        assert t.instruction
        assert t.context_files
        assert t.done_when


# -- REQ-001 Req 4: Auto task — callable returns (bool, str)
class TestAutoTaskRun:

    def test_auto_fn_callable(self):
        t = Task(name="t", auto_fn=lambda: (True, "done"))
        assert t.auto_fn is not None
        passed, detail = t.auto_fn()
        assert passed is True
        assert detail == "done"

    def test_is_auto_property(self):
        auto = Task(name="a", auto_fn=lambda: (True, "ok"))
        interactive = Task(name="i")
        assert auto.is_auto is True
        assert interactive.is_auto is False

    def test_auto_fn_defaults_none(self):
        t = Task(name="t")
        assert t.auto_fn is None


# -- REQ-001 Req 5: Gate — name, check_fn, blocking
class TestGateCheck:

    def test_gate_has_name(self):
        g = Gate(name="check", check_fn=lambda: (True, "ok"))
        assert g.name == "check"

    def test_gate_check_fn_returns_tuple(self):
        g = Gate(name="g", check_fn=lambda: (True, "all good"))
        passed, detail = g.check_fn()
        assert passed is True
        assert detail == "all good"

    def test_gate_blocking_default_true(self):
        g = Gate(name="g", check_fn=lambda: (True, "ok"))
        assert g.blocking is True

    def test_gate_non_blocking(self):
        g = Gate(name="g", check_fn=lambda: (True, "ok"), blocking=False)
        assert g.blocking is False

    def test_run_gate_passing(self):
        g = Gate(name="g", check_fn=lambda: (True, "passed"))
        result = run_gate(g)
        assert isinstance(result, GateResult)
        assert result.gate_name == "g"
        assert result.passed is True
        assert result.detail == "passed"

    def test_run_gate_failing(self):
        g = Gate(name="g", check_fn=lambda: (False, "missing file"))
        result = run_gate(g)
        assert result.passed is False
        assert result.detail == "missing file"


# -- REQ-001 Req 6: Pre-gates block on failure
class TestBlockingPregate:

    def test_blocking_gate_fails_should_not_proceed(self):
        gates = [
            Gate(name="blocker", check_fn=lambda: (False, "nope"), blocking=True),
        ]
        results = run_gates(gates)
        assert should_proceed(results) is False

    def test_all_gates_pass_should_proceed(self):
        gates = [
            Gate(name="g1", check_fn=lambda: (True, "ok")),
            Gate(name="g2", check_fn=lambda: (True, "ok")),
        ]
        results = run_gates(gates)
        assert should_proceed(results) is True

    def test_non_blocking_gate_fails_should_still_proceed(self):
        gates = [
            Gate(name="warn", check_fn=lambda: (False, "warning"), blocking=False),
        ]
        results = run_gates(gates)
        # -- Non-blocking failure is a warning, not a blocker
        assert should_proceed(results) is True

    def test_mixed_gates_blocking_fails(self):
        gates = [
            Gate(name="ok", check_fn=lambda: (True, "fine")),
            Gate(name="block", check_fn=lambda: (False, "nope"), blocking=True),
            Gate(name="warn", check_fn=lambda: (False, "eh"), blocking=False),
        ]
        results = run_gates(gates)
        assert should_proceed(results) is False


# -- REQ-001 Req 7: Post-gates after all tasks
class TestPostgateTiming:

    def test_run_gates_works_for_post_gates(self):
        """Post-gates use the same run_gates function.
        Timing (after all tasks) is runner.py's job — we test gate execution here."""
        gates = [
            Gate(name="quality", check_fn=lambda: (True, "looks good"), blocking=False),
        ]
        results = run_gates(gates)
        assert len(results) == 1
        assert results[0].passed is True

    def test_multiple_post_gates(self):
        gates = [
            Gate(name="g1", check_fn=lambda: (True, "ok")),
            Gate(name="g2", check_fn=lambda: (False, "needs work"), blocking=False),
        ]
        results = run_gates(gates)
        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False


# -- REQ-001 Req 8: State machine — pending → running → terminal
class TestStateTransitions:

    def test_terminal_states(self):
        assert TERMINAL_STATES == {"done", "blocked", "partial", "error", "skipped"}

    def test_is_terminal_true(self):
        for state in ("done", "blocked", "partial", "error", "skipped"):
            assert is_terminal(state) is True, f"{state} should be terminal"

    def test_is_terminal_false(self):
        for state in ("pending", "running"):
            assert is_terminal(state) is False, f"{state} should not be terminal"

    def test_task_starts_pending(self):
        t = Task(name="t")
        assert t.status == "pending"

    def test_task_status_can_be_set(self):
        t = Task(name="t")
        t.status = "running"
        assert t.status == "running"
        t.status = "done"
        assert t.status == "done"


# -- REQ-001 Req 9: Round complete when all tasks terminal
class TestRoundCompletion:

    def test_all_done_is_complete(self):
        tasks = [Task(name="t1"), Task(name="t2")]
        tasks[0].status = "done"
        tasks[1].status = "done"
        assert is_round_complete(tasks) is True

    def test_mixed_terminal_is_complete(self):
        tasks = [Task(name="t1"), Task(name="t2"), Task(name="t3")]
        tasks[0].status = "done"
        tasks[1].status = "error"
        tasks[2].status = "skipped"
        assert is_round_complete(tasks) is True

    def test_pending_is_not_complete(self):
        tasks = [Task(name="t1"), Task(name="t2")]
        tasks[0].status = "done"
        tasks[1].status = "pending"
        assert is_round_complete(tasks) is False

    def test_running_is_not_complete(self):
        tasks = [Task(name="t1")]
        tasks[0].status = "running"
        assert is_round_complete(tasks) is False

    def test_empty_tasks_is_complete(self):
        assert is_round_complete([]) is True


# -- REQ-001 Req 10: Serializable to JSON
class TestSerializeRound:

    def test_serialize_round_state(self):
        tasks = [Task(name="t1"), Task(name="t2")]
        tasks[0].status = "done"
        tasks[1].status = "error"
        gate_results = [GateResult(gate_name="g1", passed=True, detail="ok")]

        state = round_state_to_dict(tasks, gate_results)

        assert state["task_statuses"]["t1"] == "done"
        assert state["task_statuses"]["t2"] == "error"
        assert len(state["gate_results"]) == 1
        assert state["gate_results"][0]["gate_name"] == "g1"

    def test_serialize_to_json_string(self):
        tasks = [Task(name="t1")]
        tasks[0].status = "done"
        gate_results = []

        state = round_state_to_dict(tasks, gate_results)
        json_str = json.dumps(state)
        parsed = json.loads(json_str)

        assert parsed["task_statuses"]["t1"] == "done"


# -- REQ-001 Req 11: Resumable from JSON
class TestResumeRound:

    def test_resume_sets_task_statuses(self):
        tasks = [Task(name="t1"), Task(name="t2"), Task(name="t3")]
        state = {
            "task_statuses": {"t1": "done", "t2": "error"},
            "gate_results": [],
        }

        round_state_from_dict(tasks, state)

        assert tasks[0].status == "done"
        assert tasks[1].status == "error"
        assert tasks[2].status == "pending"  # -- not in state, stays pending

    def test_resume_skips_completed_tasks(self):
        """After resume, only pending tasks need to run."""
        tasks = [Task(name="t1"), Task(name="t2")]
        state = {"task_statuses": {"t1": "done"}, "gate_results": []}

        round_state_from_dict(tasks, state)

        pending = [t for t in tasks if t.status == "pending"]
        assert len(pending) == 1
        assert pending[0].name == "t2"


# -- REQ-001 Req 23: Task can hint a model
class TestTaskModelHint:

    def test_model_default_none(self):
        t = Task(name="t")
        assert t.model is None

    def test_model_can_be_set(self):
        t = Task(name="t", model="opus")
        assert t.model == "opus"

    def test_model_haiku(self):
        t = Task(name="t", model="haiku")
        assert t.model == "haiku"


# -- REQ-001 Req 29: Round definition returns Round object
class TestRoundBuilder:

    def test_function_returns_round(self):
        def build_round():
            return Round(
                name="test",
                tasks=[Task(name="t1", instruction="do stuff", done_when="done")],
            )

        r = build_round()
        assert isinstance(r, Round)
        assert r.name == "test"
        assert len(r.tasks) == 1


# -- REQ-001 Req 31: Round definitions accept parameters
class TestParameterizedRound:

    def test_parameterized_round(self):
        def build_round(target: str = "src/"):
            return Round(
                name=f"check-{target}",
                tasks=[
                    Task(
                        name="scan",
                        instruction=f"Scan {target}",
                        context_files=[target],
                        done_when="File list",
                    ),
                ],
            )

        r1 = build_round("src/")
        r2 = build_round("tests/")
        assert r1.name == "check-src/"
        assert r2.name == "check-tests/"
        assert r1.tasks[0].context_files == ["src/"]
        assert r2.tasks[0].context_files == ["tests/"]


# -- REQ-001 Req 46: RoundResult.status calculation
class TestRoundResultStatusCalculation:

    def test_all_done(self):
        results = [
            TaskResult(task_name="t1", status="done"),
            TaskResult(task_name="t2", status="done"),
        ]
        assert calculate_round_status(results) == "done"

    def test_all_skipped(self):
        results = [
            TaskResult(task_name="t1", status="skipped"),
            TaskResult(task_name="t2", status="skipped"),
        ]
        assert calculate_round_status(results) == "skipped"

    def test_all_error(self):
        results = [
            TaskResult(task_name="t1", status="error"),
            TaskResult(task_name="t2", status="error"),
        ]
        assert calculate_round_status(results) == "error"

    def test_all_blocked(self):
        results = [
            TaskResult(task_name="t1", status="blocked"),
            TaskResult(task_name="t2", status="blocked"),
        ]
        assert calculate_round_status(results) == "error"

    def test_mix_done_and_error(self):
        results = [
            TaskResult(task_name="t1", status="done"),
            TaskResult(task_name="t2", status="error"),
        ]
        assert calculate_round_status(results) == "partial"

    def test_mix_done_and_blocked(self):
        results = [
            TaskResult(task_name="t1", status="done"),
            TaskResult(task_name="t2", status="blocked"),
        ]
        assert calculate_round_status(results) == "partial"

    def test_mix_done_and_partial(self):
        results = [
            TaskResult(task_name="t1", status="done"),
            TaskResult(task_name="t2", status="partial"),
        ]
        assert calculate_round_status(results) == "partial"

    def test_empty_results_skipped(self):
        """No tasks dispatched (gate blocked) → skipped."""
        assert calculate_round_status([]) == "skipped"

    def test_mix_error_and_blocked_no_done(self):
        results = [
            TaskResult(task_name="t1", status="error"),
            TaskResult(task_name="t2", status="blocked"),
        ]
        assert calculate_round_status(results) == "error"
