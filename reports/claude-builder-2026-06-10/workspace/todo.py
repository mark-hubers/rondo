"""Todo-list module storing items in a local JSON file."""

import atexit
import fcntl
import json
import os
import sys
import tempfile

_DATA_FILE = os.path.join(os.path.dirname(__file__), "todos.json")


class TodoError(Exception):
    """Raised when a todo operation cannot be completed."""


def _cleanup_lock_file() -> None:
    """Remove the lock sidecar file on process exit to prevent accumulation.

    The lock file (<data-file>.lock) is used by fcntl.flock to serialise
    concurrent access.  It is intentionally kept open while the process
    lives; this atexit handler removes it from disk so repeated runs do not
    leave stale lock files behind.  Errors are silently swallowed — the file
    may have already been removed or may not exist on the first ever run.
    """
    try:
        os.unlink(_DATA_FILE + ".lock")
    except OSError:
        pass


atexit.register(_cleanup_lock_file)


def _load_store() -> dict:
    """Load the full store from the JSON data file.

    Returns a dict: {'next_id': int, 'tasks': list[dict]}.
    Transparently migrates the legacy plain-list format.
    Raises TodoError on corrupt or structurally invalid JSON.

    Returns:
    -------
    dict
        A store object with keys:
        - 'next_id' (int): the ID to assign to the next new task.
        - 'tasks' (list[dict]): the current list of task objects, each with
          keys 'id' (int), 'text' (str), and 'done' (bool).

    Raises:
    ------
    TodoError
        If the data file contains invalid JSON or an unrecognised schema.
    """
    # No file yet means a brand-new, empty store.
    if not os.path.exists(_DATA_FILE):
        return {"next_id": 1, "tasks": []}
    try:
        with open(_DATA_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, ValueError) as exc:
        raise TodoError(f"todos.json is corrupt and cannot be read: {exc}") from exc

    # Migrate from legacy plain-list format.
    if isinstance(data, list):
        if not all(isinstance(t, dict) for t in data):
            raise TodoError("todos.json has invalid structure: list items must be task objects")
        # Derive next_id from the highest existing id so we never reuse one.
        next_id = max((t.get("id", 0) for t in data), default=0) + 1
        return {"next_id": next_id, "tasks": data}

    # Validate the expected modern schema: a dict with 'next_id' and 'tasks'.
    if not isinstance(data, dict) or "next_id" not in data or "tasks" not in data:
        raise TodoError("todos.json has invalid structure: expected {'next_id', 'tasks'} object")
    tasks = data["tasks"]
    if not isinstance(tasks, list):
        raise TodoError("todos.json has invalid structure: 'tasks' must be a list")
    if not all(isinstance(t, dict) for t in tasks):
        raise TodoError("todos.json has invalid structure: task entries must be objects")
    return data


def _save_store(store: dict) -> None:
    """Persist the store to the JSON data file (atomic write via temp file).

    Writes to a temporary file in the same directory as the data file, then
    uses os.replace() (an atomic rename on POSIX) to swap it into place.
    This ensures a reader never sees a partially-written file.  If the write
    fails for any reason the temporary file is removed and the exception is
    re-raised, leaving the original data file intact.

    Parameters
    ----------
    store : dict
        The full store object to serialise (must include 'next_id' and
        'tasks' keys as produced by _load_store).
    """
    # Place the temp file in the same directory so os.replace stays on one
    # filesystem — cross-device renames are not atomic.
    dir_ = os.path.dirname(_DATA_FILE) or "."
    fd, tmp_path = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(store, f, indent=2)
        # Atomic swap: existing readers see old file until this line completes.
        os.replace(tmp_path, _DATA_FILE)
    except Exception:
        # Clean up the orphaned temp file before propagating the error.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def add_task(text: str) -> dict:
    """Add a new task with the given text and return it.

    Acquires an exclusive file lock to prevent concurrent writes from
    producing duplicate IDs.  The new task's ID is taken from the store's
    monotonically-increasing 'next_id' counter, which is incremented and
    persisted after each addition.

    Parameters
    ----------
    text : str
        The human-readable description for the new task.  The API does not
        validate or strip this value — blank strings are accepted (only the
        CLI main() enforces a non-empty check).

    Returns:
    -------
    dict
        The newly created task object: {'id': int, 'text': str, 'done': False}.
    """
    with open(_DATA_FILE + ".lock", "a") as lock_f:
        # Exclusive lock: only one writer can hold this at a time.
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        store = _load_store()
        new_id = store["next_id"]
        task = {"id": new_id, "text": text, "done": False}
        store["tasks"].append(task)
        # Advance the counter so the next call gets a strictly larger ID.
        store["next_id"] = new_id + 1
        _save_store(store)
        return task


def list_tasks() -> list[dict]:
    """Return all tasks (snapshot under shared lock).

    Acquires a shared (read) lock so concurrent readers do not block each
    other, while still preventing a read from racing a concurrent write.

    Returns:
    -------
    list[dict]
        A list of task objects, each with keys 'id' (int), 'text' (str),
        and 'done' (bool).  Returns an empty list when no data file exists.
    """
    with open(_DATA_FILE + ".lock", "a") as lock_f:
        # Shared lock: multiple concurrent readers are allowed.
        fcntl.flock(lock_f, fcntl.LOCK_SH)
        return _load_store()["tasks"]


def mark_done(task_id: int) -> dict | None:
    """Mark a task as done by ID. Returns the task or None if not found.

    Acquires an exclusive file lock, scans the task list for a matching ID,
    sets 'done' to True on the first match, and persists the change.  The
    operation is idempotent: marking an already-done task is a no-op that
    still returns the task.

    Parameters
    ----------
    task_id : int
        The integer ID of the task to complete.

    Returns:
    -------
    dict or None
        The updated task dict (with 'done' set to True) if found, or None
        when no task with the given ID exists.
    """
    with open(_DATA_FILE + ".lock", "a") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        store = _load_store()
        for task in store["tasks"]:
            if task["id"] == task_id:
                task["done"] = True
                _save_store(store)
                return task
    # No matching task found — return None without writing.
    return None


def delete_task(task_id: int) -> dict | None:
    """Delete a task by ID. Returns the deleted task or None if not found.

    Acquires an exclusive file lock, finds the first task whose 'id' matches
    task_id, removes it from the list in-place with list.pop(), and persists
    the updated store.  The 'next_id' counter is not modified, so IDs are
    never reused after deletion.

    Parameters
    ----------
    task_id : int
        The integer ID of the task to remove.

    Returns:
    -------
    dict or None
        The removed task dict if found, or None when no task with the given
        ID exists.
    """
    with open(_DATA_FILE + ".lock", "a") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        store = _load_store()
        for i, task in enumerate(store["tasks"]):
            if task["id"] == task_id:
                # pop() by index is O(n) but keeps order; task list is small.
                removed = store["tasks"].pop(i)
                _save_store(store)
                return removed
    # No matching task found — return None without writing.
    return None


def main() -> None:
    """CLI entry point.

    Parses command-line arguments and dispatches to the appropriate API
    function.  Supported subcommands:

    add <text>
        Add a new task.  Exits 2 if text is blank or whitespace-only.
    list
        Print all tasks with status indicators (✓ done, ○ pending).
    done <id>
        Mark the task with the given integer ID as done.  Exits 2 if the ID
        is not an integer or no matching task exists.
    delete <id>
        Delete the task with the given integer ID.  Exits 2 if the ID is not
        an integer or no matching task exists.

    Exits 1 on any TodoError (e.g. corrupt data file).
    """
    import argparse

    parser = argparse.ArgumentParser(description="Simple todo list")
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_parser = subparsers.add_parser("add", help="Add a new task")
    add_parser.add_argument("text", help="Task text")

    subparsers.add_parser("list", help="List all tasks")

    done_parser = subparsers.add_parser("done", help="Mark a task as done")
    done_parser.add_argument("id", help="Task ID (integer)")

    delete_parser = subparsers.add_parser("delete", help="Delete a task")
    delete_parser.add_argument("id", help="Task ID (integer)")

    args = parser.parse_args()

    try:
        if args.command == "add":
            # Reject blank/whitespace-only text at the CLI layer; the API allows it.
            if not args.text.strip():
                sys.stderr.write("ERROR: task text cannot be empty.\n")
                sys.exit(2)
            task = add_task(args.text)
            sys.stdout.write(f"Added task #{task['id']}: {task['text']}\n")
        elif args.command == "list":
            tasks = list_tasks()
            if not tasks:
                sys.stdout.write("No tasks.\n")
            else:
                for task in tasks:
                    # ✓ = completed, ○ = still pending
                    status = "✓" if task["done"] else "○"
                    sys.stdout.write(f"[{status}] #{task['id']}: {task['text']}\n")
        elif args.command == "done":
            # Validate that the supplied id string is a real integer before calling the API.
            try:
                task_id = int(args.id)
            except (ValueError, TypeError):
                sys.stderr.write(f"ERROR: id must be an integer, got: {args.id!r}\n")
                sys.exit(2)
            task = mark_done(task_id)
            if task:
                sys.stdout.write(f"Marked #{task['id']} done: {task['text']}\n")
            else:
                sys.stderr.write(f"Task #{task_id} not found.\n")
                sys.exit(2)
        elif args.command == "delete":
            # Same integer validation as the 'done' branch.
            try:
                task_id = int(args.id)
            except (ValueError, TypeError):
                sys.stderr.write(f"ERROR: id must be an integer, got: {args.id!r}\n")
                sys.exit(2)
            task = delete_task(task_id)
            if task:
                sys.stdout.write(f"Deleted task #{task['id']}: {task['text']}\n")
            else:
                sys.stderr.write(f"Task #{task_id} not found.\n")
                sys.exit(2)
    except TodoError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
