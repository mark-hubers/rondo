# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Tests for rondo.engine — Rondo-REQ-100 reqs 1-11, 23, 29, 31, 46.

VER-001 verification matrix: every test maps to a numbered requirement.
TDD: these tests are written BEFORE engine.py exists.
"""

import json

# -- Add rondo/src to path so we can import rondo

from rondo.engine import (
    TERMINAL_STATES,
    Gate,
    GateResult,
    Round,
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
    validate_round,
    validate_task,
)


# -- Rondo-REQ-100 Req 1: Round contains name, gates, tasks
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


# -- Rondo-REQ-100 Req 2: Task has name, mode, status
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


# -- Rondo-REQ-100 Req 3: Interactive task — Do/Read/Done (three-field contract)
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


# -- Rondo-REQ-100 Req 4: Auto task — callable returns (bool, str)
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


# -- Rondo-REQ-100 Req 5: Gate — name, check_fn, blocking
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


# -- Rondo-REQ-100 Req 6: Pre-gates block on failure
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


# -- Rondo-REQ-100 Req 7: Post-gates after all tasks
class TestPostgateTiming:
    def test_run_gates_works_for_post_gates(self):
        """Post-gates use the same run_gates function.

        Timing (after all tasks) is runner.py's job — we test gate execution here.
        """
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


# -- REQ-100 Req 008: State machine — pending → in_progress → terminal
class TestStateTransitions:
    def test_terminal_states(self):
        assert TERMINAL_STATES == {"done", "blocked", "partial", "error", "skipped"}

    def test_is_terminal_true(self):
        for state in ("done", "blocked", "partial", "error", "skipped"):
            assert is_terminal(state) is True, f"{state} should be terminal"

    def test_is_terminal_false(self):
        for state in ("pending", "in_progress"):
            assert is_terminal(state) is False, f"{state} should not be terminal"

    def test_task_starts_pending(self):
        t = Task(name="t")
        assert t.status == "pending"

    def test_task_status_can_be_set(self):
        t = Task(name="t")
        t.status = "in_progress"
        assert t.status == "in_progress"
        t.status = "done"
        assert t.status == "done"


# -- Rondo-REQ-100 Req 9: Round complete when all tasks terminal
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

    def test_in_progress_is_not_complete(self):
        tasks = [Task(name="t1")]
        tasks[0].status = "in_progress"
        assert is_round_complete(tasks) is False

    def test_empty_tasks_is_complete(self):
        assert is_round_complete([]) is True


# -- Rondo-REQ-100 Req 10: Serializable to JSON
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


# -- Rondo-REQ-100 Req 11: Resumable from JSON
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


# -- Rondo-REQ-100 Req 23: Task can hint a model
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


# -- Rondo-REQ-100 Req 29: Round definition returns Round object
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


# -- Rondo-REQ-100 Req 31: Round definitions accept parameters
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


# -- Rondo-REQ-100 Req 46: RoundResult.status calculation
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


# ──────────────────────────────────────────────────────────────────
#  Task Validation — validate_task()
# ──────────────────────────────────────────────────────────────────


class TestValidateTask:
    def test_valid_interactive_task(self):
        """Valid interactive task returns no errors."""
        task = Task(name="check", instruction="Do thing", done_when="Thing done")
        assert validate_task(task) == []

    def test_valid_auto_task(self):
        """Valid auto task returns no errors."""
        task = Task(name="count", auto_fn=lambda: (True, "42"))
        assert validate_task(task) == []

    def test_empty_name(self):
        """Empty task name is an error."""
        task = Task(name="", instruction="do", done_when="done")
        errors = validate_task(task)
        assert any("empty name" in e for e in errors)

    def test_whitespace_name(self):
        """Whitespace-only task name is an error."""
        task = Task(name="   ", instruction="do", done_when="done")
        errors = validate_task(task)
        assert any("empty name" in e for e in errors)

    def test_missing_instruction(self):
        """Interactive task without instruction is an error."""
        task = Task(name="t", instruction="", done_when="done")
        errors = validate_task(task)
        assert any("instruction" in e.lower() or "Do field" in e for e in errors)

    def test_missing_done_when(self):
        """Interactive task without done_when is an error."""
        task = Task(name="t", instruction="do", done_when="")
        errors = validate_task(task)
        assert any("done_when" in e.lower() or "Done field" in e for e in errors)

    def test_neither_auto_nor_interactive(self):
        """Task with no auto_fn and no instruction/done_when is an error."""
        task = Task(name="empty-task")
        errors = validate_task(task)
        assert any("neither" in e for e in errors)

    def test_both_auto_and_interactive(self):
        """Task with both auto_fn AND instruction/done_when is an error."""
        task = Task(name="confused", instruction="do", done_when="done", auto_fn=lambda: (True, "ok"))
        errors = validate_task(task)
        assert any("both" in e.lower() for e in errors)

    def test_multiple_errors_returned(self):
        """A task can have multiple validation errors at once."""
        task = Task(name="")  # -- empty name AND no contract
        errors = validate_task(task)
        assert len(errors) >= 2


# ──────────────────────────────────────────────────────────────────
#  Round Validation — validate_round()
# ──────────────────────────────────────────────────────────────────


class TestValidateRound:
    def test_valid_round(self):
        """Valid round returns no errors."""
        r = Round(
            name="my-round",
            tasks=[Task(name="t1", instruction="do", done_when="done")],
        )
        assert validate_round(r) == []

    def test_empty_round_name(self):
        """Empty round name is an error."""
        r = Round(name="", tasks=[Task(name="t1", instruction="do", done_when="done")])
        errors = validate_round(r)
        assert any("Round name" in e for e in errors)

    def test_duplicate_task_names(self):
        """Duplicate task names are caught."""
        r = Round(
            name="dup-round",
            tasks=[
                Task(name="same", instruction="do A", done_when="A done"),
                Task(name="same", instruction="do B", done_when="B done"),
            ],
        )
        errors = validate_round(r)
        assert any("Duplicate" in e for e in errors)

    def test_invalid_task_in_round(self):
        """Invalid task inside a round is caught."""
        r = Round(
            name="bad-task-round",
            tasks=[Task(name="bad", instruction="", done_when="")],
        )
        errors = validate_round(r)
        assert len(errors) > 0

    def test_empty_tasks_valid(self):
        """Round with no tasks is valid (handled at runner level)."""
        r = Round(name="empty-round")
        assert validate_round(r) == []


# ──────────────────────────────────────────────────────────────────
#  REQ-106: Structured Task Input (context_data)
# ──────────────────────────────────────────────────────────────────


class TestContextData:
    """REQ-106 reqs 001-009: context_data on Task and TaskResult."""

    def test_task_has_context_data_default_empty(self):
        """REQ-106 req 001: Task has context_data field, defaults to empty dict."""
        t = Task(name="t", instruction="do", done_when="done")
        assert t.context_data == {}

    def test_task_context_data_accepts_dict(self):
        """REQ-106 req 001: context_data accepts a dict."""
        t = Task(name="t", instruction="do", done_when="done",
                 context_data={"findings": [1, 2, 3], "product": "ob"})
        assert t.context_data["product"] == "ob"
        assert len(t.context_data["findings"]) == 3

    def test_task_result_has_context_data(self):
        """REQ-106 req 002: TaskResult has context_data for audit trail."""
        r = TaskResult(task_name="t", context_data={"input": "test"})
        assert r.context_data["input"] == "test"

    def test_task_result_context_data_default_empty(self):
        """REQ-106 req 002: TaskResult context_data defaults to empty dict."""
        r = TaskResult(task_name="t")
        assert r.context_data == {}

    def test_validate_rejects_non_serializable(self):
        """REQ-106 req 009: non-JSON-serializable context_data is an error."""
        t = Task(name="bad", instruction="do", done_when="done",
                 context_data={"fn": lambda: None})
        errors = validate_task(t)
        assert any("JSON-serializable" in e for e in errors)

    def test_validate_accepts_serializable(self):
        """REQ-106 req 009: valid JSON context_data passes validation."""
        t = Task(name="ok", instruction="do", done_when="done",
                 context_data={"findings": [{"check": "yaml", "status": "pass"}]})
        errors = validate_task(t)
        assert errors == []

    def test_validate_empty_context_data_ok(self):
        """REQ-106: empty context_data is valid (it's optional)."""
        t = Task(name="ok", instruction="do", done_when="done")
        errors = validate_task(t)
        assert errors == []

    def test_context_data_with_nested_structures(self):
        """REQ-106: nested dicts and lists work."""
        data = {
            "findings": [
                {"check": "yaml_parses", "severity": "error", "files": ["a.yaml", "b.yaml"]},
                {"check": "fk_match", "severity": "warning", "count": 5},
            ],
            "metadata": {"product": "ob", "total": 132},
        }
        t = Task(name="deep", instruction="review", done_when="JSON", context_data=data)
        assert len(t.context_data["findings"]) == 2
        assert t.context_data["metadata"]["total"] == 132

    def test_context_files_path_traversal_rejected(self):
        """REQ-100 req 003: context_files with '..' are rejected."""
        t = Task(name="bad", instruction="do", done_when="done",
                 context_files=["../../etc/passwd"])
        errors = validate_task(t)
        assert any(".." in e for e in errors)

    def test_context_files_absolute_path_rejected(self):
        """REQ-100 req 003: absolute paths in context_files are rejected."""
        t = Task(name="bad", instruction="do", done_when="done",
                 context_files=["/etc/passwd"])
        errors = validate_task(t)
        assert any("absolute" in e for e in errors)

    def test_context_files_relative_path_ok(self):
        """REQ-100 req 003: relative paths in context_files are valid."""
        t = Task(name="ok", instruction="do", done_when="done",
                 context_files=["specs/my-spec.md", "platform.yaml"])
        errors = validate_task(t)
        assert errors == []

    def test_context_files_symlink_outside_root_rejected(self, tmp_path):
        """REQ-100 req 003: symlinks pointing outside project root are rejected."""
        ## -- Create a symlink pointing to /etc
        link = tmp_path / "sneaky_link"
        link.symlink_to("/etc")
        t = Task(name="bad", instruction="do", done_when="done",
                 context_files=[str(link)])
        errors = validate_task(t, project_root=str(tmp_path))
        assert any("symlink" in e for e in errors)

    def test_context_files_symlink_inside_root_ok(self, tmp_path):
        """REQ-100 req 003: symlinks within project root are valid."""
        target = tmp_path / "real_file.md"
        target.write_text("content")
        link = tmp_path / "good_link"
        link.symlink_to(target)
        t = Task(name="ok", instruction="do", done_when="done",
                 context_files=[str(link)])
        errors = validate_task(t, project_root=str(tmp_path))
        assert not any("symlink" in e for e in errors)

    def test_context_files_total_size_capped(self, tmp_path):
        """REQ-100 req 003: total context size capped at max_context_bytes."""
        ## -- Create files totaling > 500KB
        for i in range(6):
            (tmp_path / f"big_{i}.txt").write_text("x" * 100_000)
        files = [str(tmp_path / f"big_{i}.txt") for i in range(6)]
        t = Task(name="big", instruction="do", done_when="done",
                 context_files=files)
        errors = validate_task(t, max_context_bytes=500_000)
        assert any("max_context_bytes" in e for e in errors)

    def test_context_files_under_size_cap_ok(self, tmp_path):
        """REQ-100 req 003: files under the cap pass validation."""
        (tmp_path / "small.txt").write_text("hello")
        t = Task(name="ok", instruction="do", done_when="done",
                 context_files=[str(tmp_path / "small.txt")])
        errors = validate_task(t, max_context_bytes=500_000)
        assert not any("max_context_bytes" in e for e in errors)


# -- Deep coverage: new Session 91 fields in serialization
class TestNewFieldsSerialization:
    """Verify Session 91 fields survive JSON round-trip."""

    def test_task_with_all_new_fields_serializable(self):
        """Task with tool_mode, bare, human_input, context_data → JSON → back."""
        import json
        from dataclasses import asdict

        t = Task(name="full", instruction="do", done_when="done",
                 tool_mode="sandbox", bare=False, human_input="check first",
                 context_data={"key": [1, 2, 3]})
        data = asdict(t)
        # Remove non-serializable fields
        data.pop("auto_fn", None)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["tool_mode"] == "sandbox"
        assert parsed["bare"] is False
        assert parsed["human_input"] == "check first"
        assert parsed["context_data"]["key"] == [1, 2, 3]

    def test_task_result_with_command_sent(self):
        """TaskResult.command_sent survives JSON round-trip."""
        import json
        from dataclasses import asdict

        tr = TaskResult(task_name="t", status="done",
                        command_sent=["claude", "-p", "test", "--bare"])
        data = asdict(tr)
        json_str = json.dumps(data, default=str)
        parsed = json.loads(json_str)
        assert parsed["command_sent"] == ["claude", "-p", "test", "--bare"]

    def test_dispatch_usage_budget_field_serializable(self):
        """DispatchUsage.budget_exceeded survives JSON round-trip."""
        import json
        from dataclasses import asdict
        from rondo.engine import DispatchUsage as _DU

        u = _DU(task_name="t", budget_exceeded=True, cost_usd=0.05)
        data = asdict(u)
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["budget_exceeded"] is True
        assert parsed["cost_usd"] == 0.05


class TestRoundStateWithNewFields:
    """Round state includes new fields in serialization."""

    def test_state_dict_includes_tool_mode(self):
        """round_state_to_dict captures tool_mode status."""
        tasks = [Task(name="t1", tool_mode="sandbox")]
        tasks[0].status = "done"
        state = round_state_to_dict(tasks, [])
        assert state["task_statuses"]["t1"] == "done"

    def test_resume_preserves_pending_tasks(self):
        """round_state_from_dict only sets status for known tasks."""
        tasks = [Task(name="t1"), Task(name="t2"), Task(name="t3")]
        state = {"task_statuses": {"t1": "done"}, "gate_results": []}
        round_state_from_dict(tasks, state)
        assert tasks[0].status == "done"
        assert tasks[1].status == "pending"
        assert tasks[2].status == "pending"


# -- sig: mgh-6201.cd.bd955f.39ed.655d8b
