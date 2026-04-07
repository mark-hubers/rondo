# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Structured logging with request_id correlation — RONDO-148.

Rondo-REQ-104 (extension): observability for cross-component dispatch tracing.

Finding #215: No way to trace a single dispatch through mcp_dispatch ->
providers -> auth -> adapter -> audit. Production debugging impossible.

This module provides:
    bind_request_id(rid) — context manager that sets thread-local request_id
    get_request_id() — read current thread's request_id (or empty)
    new_request_id() — generate a fresh request_id (UUID4)
    StructuredLogger — wraps stdlib logger with structured JSON output
    log_event(level, msg, **fields) — emit JSON record with request_id

Records emit as JSON lines for downstream parsing (jq, structured log
aggregators). Falls back to plain text format when stdlib logger is in
text mode.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# -- Thread-local storage for request_id propagation
_local = threading.local()


def new_request_id() -> str:
    """Generate a fresh request_id (UUID4 hex, 32 chars)."""
    return uuid.uuid4().hex


def get_request_id() -> str:
    """Return current thread's bound request_id, or empty if none."""
    return getattr(_local, "request_id", "")


@contextmanager
def bind_request_id(request_id: str | None = None) -> Iterator[str]:
    """Context manager: bind request_id to current thread for log correlation.

    Usage:
        with bind_request_id() as rid:
            log_event("INFO", "dispatch start", model="sonnet")
            # -- All log_event calls in this block include rid

    If request_id=None, generates a fresh one.
    """
    rid = request_id or new_request_id()
    previous = getattr(_local, "request_id", "")
    _local.request_id = rid
    try:
        yield rid
    finally:
        _local.request_id = previous


def log_event(level: str, message: str, **fields: Any) -> None:
    """Emit a structured log record with request_id + custom fields.

    Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.

    The record is logged via stdlib logger at the given level. Format is
    JSON when extra fields are present, plain text otherwise.
    """
    rid = get_request_id()
    record = {
        "ts": time.time(),
        "level": level,
        "msg": message,
        "request_id": rid,
        **fields,
    }

    log_method = getattr(logger, level.lower(), logger.info)
    try:
        log_method(json.dumps(record, default=str))
    except (TypeError, ValueError):
        # -- Fallback if a field can't be serialized
        log_method("%s | request_id=%s | %s", message, rid, str(fields)[:300])


class StructuredLogger:
    """Convenience wrapper that mimics logging.Logger but emits structured records.

    Use this when you want a per-component logger that auto-injects
    request_id and a fixed component name on every call.
    """

    def __init__(self, component: str) -> None:
        self.component = component

    def info(self, message: str, **fields: Any) -> None:
        """Emit INFO record."""
        log_event("INFO", message, component=self.component, **fields)

    def warning(self, message: str, **fields: Any) -> None:
        """Emit WARNING record."""
        log_event("WARNING", message, component=self.component, **fields)

    def error(self, message: str, **fields: Any) -> None:
        """Emit ERROR record."""
        log_event("ERROR", message, component=self.component, **fields)

    def debug(self, message: str, **fields: Any) -> None:
        """Emit DEBUG record."""
        log_event("DEBUG", message, component=self.component, **fields)


# -- sig: mgh-6201.cd.bd955f.f1d0.f0d062
