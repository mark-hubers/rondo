"""Tests for the todo-list module (add / list / done / delete + validation cases).

Uses tmp_path + monkeypatch so the real todos.json is never touched.
"""

import json
import os
import subprocess
import sys
import threading

import pytest

# Ensure workspace dir is on sys.path so `import todo` always resolves.
sys.path.insert(0, os.path.dirname(__file__))
import todo  # noqa: E402


@pytest.fixture()
def data_file(tmp_path, monkeypatch):
    """Redirect todo._DATA_FILE to a fresh temp path; real file untouched."""
    path = tmp_path / "todos.json"
    monkeypatch.setattr(todo, "_DATA_FILE", str(path))
    return path


# ── add_task ──────────────────────────────────────────────────────────────────


class TestAddTask:
    def test_returns_task_dict(self, data_file):
        task = todo.add_task("buy milk")
        assert task == {"id": 1, "text": "buy milk", "done": False}

    def test_persists_to_file(self, data_file):
        todo.add_task("first")
        on_disk = json.loads(data_file.read_text())
        tasks = on_disk["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["text"] == "first"

    def test_ids_increment(self, data_file):
        t1 = todo.add_task("alpha")
        t2 = todo.add_task("beta")
        assert t1["id"] == 1
        assert t2["id"] == 2

    def test_multiple_tasks_accumulate(self, data_file):
        for i in range(5):
            todo.add_task(f"task {i}")
        assert len(todo.list_tasks()) == 5

    def test_new_tasks_default_not_done(self, data_file):
        task = todo.add_task("something")
        assert task["done"] is False

    def test_concurrent_add_unique_ids(self, data_file):
        """Two concurrent add_task calls must produce distinct IDs with no data loss."""
        results = []
        errors = []

        def add_one(text):
            try:
                task = todo.add_task(text)
                results.append(task)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=add_one, args=("task-a",))
        t2 = threading.Thread(target=add_one, args=("task-b",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 2
        ids = {r["id"] for r in results}
        assert len(ids) == 2, f"ID collision: both tasks got same id from {ids}"
        on_disk = json.loads(data_file.read_text())
        assert len(on_disk["tasks"]) == 2, "Both tasks must be persisted"

    def test_id_unique_after_gap_in_sequence(self, data_file):
        """IDs must be unique even when the on-disk sequence has a gap."""
        todo.add_task("one")
        todo.add_task("two")
        todo.add_task("three")
        # Manually remove task 2 from the store: remaining task ids = [1, 3]
        store = json.loads(data_file.read_text())
        store["tasks"] = [t for t in store["tasks"] if t["id"] != 2]
        data_file.write_text(json.dumps(store))
        # next_id in store is 4, so new task gets id=4 regardless of the gap
        new_task = todo.add_task("four")
        all_ids = [t["id"] for t in todo.list_tasks()]
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs after gap: {all_ids}"
        assert new_task["id"] == 4, f"Expected id=4, got {new_task['id']}"

    def test_id_no_reuse_after_highest_id_deletion(self, data_file):
        """IDs must not be reused after the highest-ID task is deleted externally."""
        todo.add_task("one")  # id=1
        todo.add_task("two")  # id=2
        todo.add_task("three")  # id=3  (highest)
        # Delete the highest-ID task externally; next_id stays at 4 in the store
        store = json.loads(data_file.read_text())
        store["tasks"] = [t for t in store["tasks"] if t["id"] != 3]
        data_file.write_text(json.dumps(store))
        # With the old max(ids)+1 strategy the next task would reuse id=3.
        # With the next_id counter it must use id=4.
        new_task = todo.add_task("four")
        all_ids = [t["id"] for t in todo.list_tasks()]
        assert len(all_ids) == len(set(all_ids)), f"Duplicate IDs: {all_ids}"
        assert new_task["id"] == 4, f"Expected id=4 (no reuse), got {new_task['id']}"

    def test_atomic_write_preserves_data_on_crash(self, data_file, monkeypatch):
        """A crash mid-write must not corrupt or empty the data file."""
        todo.add_task("existing task")
        original = data_file.read_text()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(json, "dump", boom)
        with pytest.raises(OSError):
            todo.add_task("new task")

        assert data_file.exists(), "Data file must still exist"
        assert data_file.read_text() == original, "Original data must be intact after crash"

    def test_concurrent_add_multiprocess_unique_ids(self, data_file, tmp_path):
        """Two concurrent processes calling add_task must produce distinct IDs."""
        workspace = os.path.dirname(os.path.abspath(__file__))
        data_file_str = str(data_file)
        script_path = tmp_path / "mp_add.py"
        script_path.write_text(
            "import sys, os\n"
            f"sys.path.insert(0, {workspace!r})\n"
            "import todo\n"
            f"todo._DATA_FILE = {data_file_str!r}\n"
            "todo.add_task(sys.argv[1])\n"
        )
        p1 = subprocess.Popen([sys.executable, str(script_path), "proc-a"])
        p2 = subprocess.Popen([sys.executable, str(script_path), "proc-b"])
        assert p1.wait() == 0, f"Process 1 exited with code {p1.returncode}"
        assert p2.wait() == 0, f"Process 2 exited with code {p2.returncode}"
        tasks = todo.list_tasks()
        assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}: {tasks}"
        ids = {t["id"] for t in tasks}
        assert len(ids) == 2, f"ID collision between processes: ids={ids}"


# ── list_tasks ────────────────────────────────────────────────────────────────


class TestListTasks:
    def test_empty_when_no_file(self, data_file):
        assert not data_file.exists()
        assert todo.list_tasks() == []

    def test_empty_when_file_has_empty_list(self, data_file):
        data_file.write_text("[]")
        assert todo.list_tasks() == []

    def test_returns_all_tasks(self, data_file):
        todo.add_task("a")
        todo.add_task("b")
        tasks = todo.list_tasks()
        assert len(tasks) == 2
        assert tasks[0]["text"] == "a"
        assert tasks[1]["text"] == "b"

    def test_does_not_mutate_file(self, data_file):
        todo.add_task("x")
        before = data_file.read_text()
        todo.list_tasks()
        assert data_file.read_text() == before


# ── mark_done ─────────────────────────────────────────────────────────────────


class TestMarkDone:
    def test_returns_updated_task(self, data_file):
        todo.add_task("do laundry")
        task = todo.mark_done(1)
        assert task is not None
        assert task["id"] == 1
        assert task["done"] is True

    def test_persists_done_flag(self, data_file):
        todo.add_task("walk dog")
        todo.mark_done(1)
        on_disk = json.loads(data_file.read_text())
        assert on_disk["tasks"][0]["done"] is True

    def test_nonexistent_id_returns_none(self, data_file):
        todo.add_task("something")
        assert todo.mark_done(999) is None

    def test_zero_id_returns_none(self, data_file):
        todo.add_task("task")
        assert todo.mark_done(0) is None

    def test_only_target_task_marked(self, data_file):
        todo.add_task("first")
        todo.add_task("second")
        todo.mark_done(1)
        tasks = todo.list_tasks()
        assert tasks[0]["done"] is True
        assert tasks[1]["done"] is False

    def test_mark_done_idempotent(self, data_file):
        """Calling mark_done twice on the same task stays done without raising."""
        todo.add_task("task to complete")
        result1 = todo.mark_done(1)
        assert result1 is not None
        assert result1["done"] is True
        result2 = todo.mark_done(1)
        assert result2 is not None
        assert result2["done"] is True
        on_disk = json.loads(data_file.read_text())
        assert len(on_disk["tasks"]) == 1
        assert on_disk["tasks"][0]["done"] is True


# ── delete_task ───────────────────────────────────────────────────────────────


class TestDeleteTask:
    def test_delete_returns_removed_task(self, data_file):
        todo.add_task("to remove")
        task = todo.delete_task(1)
        assert task is not None
        assert task["id"] == 1
        assert task["text"] == "to remove"

    def test_delete_removes_from_list(self, data_file):
        todo.add_task("keep")
        todo.add_task("remove")
        todo.delete_task(2)
        tasks = todo.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == 1

    def test_delete_nonexistent_returns_none(self, data_file):
        todo.add_task("task")
        assert todo.delete_task(999) is None

    def test_delete_persists(self, data_file):
        todo.add_task("task")
        todo.delete_task(1)
        on_disk = json.loads(data_file.read_text())
        assert on_disk["tasks"] == []

    def test_delete_does_not_reset_next_id(self, data_file):
        """Deleting a task must not affect next_id — IDs must keep incrementing."""
        todo.add_task("first")  # id=1
        todo.add_task("second")  # id=2
        todo.delete_task(2)  # remove highest
        new_task = todo.add_task("third")
        assert new_task["id"] == 3, f"Expected id=3, got {new_task['id']}"

    def test_delete_cli_success(self, data_file, monkeypatch, capsys):
        """CLI delete subcommand removes the task and prints confirmation."""
        todo.add_task("test task")
        monkeypatch.setattr("sys.argv", ["todo", "delete", "1"])
        todo.main()
        out, _ = capsys.readouterr()
        assert "Deleted task #1" in out
        assert todo.list_tasks() == []

    def test_delete_nonexistent_cli_exits_2(self, data_file, monkeypatch):
        """CLI exits 2 when delete target does not exist."""
        monkeypatch.setattr("sys.argv", ["todo", "delete", "999"])
        with pytest.raises(SystemExit) as exc_info:
            todo.main()
        assert exc_info.value.code == 2


# ── validation / error cases ──────────────────────────────────────────────────


class TestValidationCases:
    def test_empty_text_api_allowed(self, data_file):
        """add_task() API does NOT validate text — only CLI main() does.
        Confirm empty string is stored without raising."""
        task = todo.add_task("")
        assert task["text"] == ""

    def test_empty_text_cli_exits_2(self, data_file, monkeypatch):
        """CLI rejects blank/whitespace text with exit code 2."""
        monkeypatch.setattr("sys.argv", ["todo", "add", "   "])
        with pytest.raises(SystemExit) as exc_info:
            todo.main()
        assert exc_info.value.code == 2

    def test_bad_id_cli_exits_2(self, data_file, monkeypatch):
        """CLI rejects non-integer done id with exit code 2."""
        monkeypatch.setattr("sys.argv", ["todo", "done", "notanumber"])
        with pytest.raises(SystemExit) as exc_info:
            todo.main()
        assert exc_info.value.code == 2

    def test_nonexistent_id_cli_exits_2(self, data_file, monkeypatch):
        """CLI exits 2 when a valid integer id has no matching task."""
        todo.add_task("some task")  # ensure file exists with a real task
        monkeypatch.setattr("sys.argv", ["todo", "done", "42"])
        with pytest.raises(SystemExit) as exc_info:
            todo.main()
        assert exc_info.value.code == 2

    def test_corrupt_json_list_raises(self, data_file):
        """_load_store() raises TodoError on JSONDecodeError."""
        data_file.write_text("{ not valid json !!!")
        with pytest.raises(todo.TodoError):
            todo.list_tasks()

    def test_corrupt_json_add_raises(self, data_file):
        """add_task() propagates TodoError from _load_store() on corrupt JSON."""
        data_file.write_text("[broken")
        with pytest.raises(todo.TodoError):
            todo.add_task("anything")

    def test_corrupt_json_mark_done_raises(self, data_file):
        """mark_done() propagates TodoError from _load_store() on corrupt JSON."""
        data_file.write_text("{bad json")
        with pytest.raises(todo.TodoError):
            todo.mark_done(1)

    def test_corrupt_json_cli_exits_1(self, data_file, monkeypatch):
        """CLI main() catches TodoError and exits 1."""
        data_file.write_text("{ not valid json !!!")
        monkeypatch.setattr("sys.argv", ["todo", "list"])
        with pytest.raises(SystemExit) as exc_info:
            todo.main()
        assert exc_info.value.code == 1

    def test_schema_wrong_root_type_raises(self, data_file):
        """_load_store() raises TodoError when JSON root is a dict missing next_id/tasks."""
        data_file.write_text('{"something": "else"}')
        with pytest.raises(todo.TodoError):
            todo.list_tasks()

    def test_schema_list_of_non_dicts_raises(self, data_file):
        """_load_store() raises TodoError when JSON is a list of non-dict items."""
        data_file.write_text("[1, 2, 3]")
        with pytest.raises(todo.TodoError):
            todo.list_tasks()


# ── edge cases ────────────────────────────────────────────────────────────────


class TestEdgeCases:
    """Unicode task text, very long text, done-on-already-done, zero-task list."""

    # ── unicode task text ─────────────────────────────────────────────────────

    def test_unicode_emoji_text(self, data_file):
        """Task text with emoji characters round-trips through JSON correctly."""
        text = "Buy milk \U0001f95b and eggs \U0001f95a"
        task = todo.add_task(text)
        assert task["text"] == text
        on_disk = json.loads(data_file.read_text())
        assert on_disk["tasks"][0]["text"] == text

    def test_unicode_cjk_text(self, data_file):
        """Task text with CJK characters is stored and retrieved correctly."""
        text = "買牛乳 および 鸡卵を買う"
        task = todo.add_task(text)
        assert task["text"] == text
        assert todo.list_tasks()[0]["text"] == text

    def test_unicode_accented_latin(self, data_file):
        """Accented Latin characters survive the JSON round-trip."""
        text = "Caf\xe9 au lait und Stra\xdfe \xfcberqueren"
        task = todo.add_task(text)
        assert task["text"] == text

    def test_unicode_rtl_text(self, data_file):
        """Right-to-left text (Arabic) is stored unchanged."""
        text = "اشترِ الحليب"
        task = todo.add_task(text)
        assert task["text"] == text

    def test_unicode_mixed_scripts(self, data_file):
        """Task with multiple scripts in one string round-trips intact."""
        text = "Buy \U0001f95b 牛乳 Milch hal\xe1l"
        task = todo.add_task(text)
        retrieved = todo.list_tasks()[0]
        assert retrieved["text"] == text

    def test_unicode_text_cli(self, data_file, monkeypatch, capsys):
        """CLI add + list handles unicode task text without error."""
        text = "Ångstr\xf6m units \U0001f52c"
        monkeypatch.setattr("sys.argv", ["todo", "add", text])
        todo.main()
        out, _ = capsys.readouterr()
        assert text in out

    # ── very long text ────────────────────────────────────────────────────────

    def test_very_long_text_stored(self, data_file):
        """A 10,000-character task text is accepted and persists without truncation."""
        text = "x" * 10_000
        task = todo.add_task(text)
        assert task["text"] == text
        assert len(task["text"]) == 10_000

    def test_very_long_text_round_trips(self, data_file):
        """Very long text survives a JSON file round-trip byte-for-byte."""
        text = "A" * 5_000 + "B" * 5_000
        todo.add_task(text)
        retrieved = todo.list_tasks()[0]["text"]
        assert retrieved == text

    def test_very_long_text_list_tasks(self, data_file):
        """list_tasks() returns the full long text, not a truncated version."""
        text = "z" * 50_000
        todo.add_task(text)
        tasks = todo.list_tasks()
        assert len(tasks) == 1
        assert len(tasks[0]["text"]) == 50_000

    # ── done on an already-done task ──────────────────────────────────────────

    def test_done_on_already_done_api_returns_task(self, data_file):
        """mark_done() on an already-done task returns the task (not None)."""
        todo.add_task("finish report")
        todo.mark_done(1)
        result = todo.mark_done(1)
        assert result is not None
        assert result["id"] == 1
        assert result["done"] is True

    def test_done_on_already_done_no_extra_entries(self, data_file):
        """Calling mark_done twice does not add extra task entries."""
        todo.add_task("read book")
        todo.mark_done(1)
        todo.mark_done(1)
        assert len(todo.list_tasks()) == 1

    def test_done_on_already_done_cli_succeeds(self, data_file, monkeypatch, capsys):
        """CLI 'done <id>' on an already-done task exits 0 and prints confirmation."""
        todo.add_task("submit form")
        monkeypatch.setattr("sys.argv", ["todo", "done", "1"])
        todo.main()
        capsys.readouterr()
        # Second 'done' call — must NOT raise SystemExit
        monkeypatch.setattr("sys.argv", ["todo", "done", "1"])
        todo.main()
        out, _ = capsys.readouterr()
        assert "#1" in out

    def test_done_on_already_done_file_state(self, data_file):
        """After double mark_done the file still has exactly one task with done=True."""
        todo.add_task("call dentist")
        todo.mark_done(1)
        todo.mark_done(1)
        on_disk = json.loads(data_file.read_text())
        assert len(on_disk["tasks"]) == 1
        assert on_disk["tasks"][0]["done"] is True

    # ── list with zero tasks ──────────────────────────────────────────────────

    def test_list_zero_tasks_after_all_deleted(self, data_file):
        """list_tasks() returns [] after every task is deleted."""
        todo.add_task("first")
        todo.add_task("second")
        todo.delete_task(1)
        todo.delete_task(2)
        assert todo.list_tasks() == []

    def test_list_zero_tasks_after_delete_file_state(self, data_file):
        """On-disk store has an empty task list after all tasks are deleted."""
        todo.add_task("temp")
        todo.delete_task(1)
        on_disk = json.loads(data_file.read_text())
        assert on_disk["tasks"] == []

    def test_list_zero_tasks_cli_after_delete(self, data_file, monkeypatch, capsys):
        """CLI 'list' on a store where all tasks were deleted prints 'No tasks.'"""
        todo.add_task("will be deleted")
        todo.delete_task(1)
        monkeypatch.setattr("sys.argv", ["todo", "list"])
        todo.main()
        out, _ = capsys.readouterr()
        assert "No tasks" in out

    def test_list_zero_tasks_cli_no_file(self, data_file, monkeypatch, capsys):
        """CLI 'list' with no data file at all prints 'No tasks.'"""
        assert not data_file.exists()
        monkeypatch.setattr("sys.argv", ["todo", "list"])
        todo.main()
        out, _ = capsys.readouterr()
        assert "No tasks" in out
