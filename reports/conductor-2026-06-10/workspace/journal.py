"""Simple append-only journal backed by a JSON Lines file."""

import json
import os

JOURNAL_FILE = os.path.join(os.path.dirname(__file__), "journal.jsonl")


def add_entry(text: str) -> None:
    """Append a text entry to the journal file.

    Serialises ``text`` as a JSON object ``{"text": ...}`` and appends it
    as a single line to ``JOURNAL_FILE``.  Creates the file if it does not
    already exist.

    Args:
        text: The string content to store in the new journal entry.

    Returns:
        None
    """
    with open(JOURNAL_FILE, "a") as f:
        f.write(json.dumps({"text": text}) + "\n")


def list_entries() -> list:
    """Read and return all journal entries in insertion order.

    Parses every non-empty line of ``JOURNAL_FILE`` as a JSON object and
    returns them as a list.  Returns an empty list if the file does not
    exist yet.

    Returns:
        A list of dicts, each with at least a ``"text"`` key, in the order
        they were written.
    """
    if not os.path.exists(JOURNAL_FILE):
        return []
    entries = []
    with open(JOURNAL_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def search_entries(term: str) -> list:
    """Return journal entries whose text contains *term* (case-insensitive).

    Delegates to :func:`list_entries` for loading, then filters by substring
    match after lowercasing both sides.  An empty *term* matches every entry.

    Args:
        term: The substring to search for within each entry's ``"text"`` value.

    Returns:
        A list of matching entry dicts, preserving original insertion order.
        Returns an empty list if no entries match or the journal is empty.
    """
    term_lower = term.lower()
    return [e for e in list_entries() if term_lower in e.get("text", "").lower()]
