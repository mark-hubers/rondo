# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""ProviderAdapter abstract base class — RONDO-209 dependency inversion.

Rondo-REQ-109 req 001. Extracted from providers.py to break the cyclic
import between adapters/* and providers.py:

    Before (cycle):
        adapters/anthropic_api.py → providers.py → adapters/health.py → adapters/factory.py → back to adapters/anthropic_api.py

    After (no cycle):
        adapters/anthropic_api.py → provider_base.py
        providers.py → provider_base.py + adapters/health.py + adapters/factory.py
        adapters/factory.py → adapters/anthropic_api.py → provider_base.py

provider_base.py is L0 — only imports from rondo.engine for TaskResult.
Both adapters/ and providers.py depend on it; no module depends on
both adapters and providers in a way that creates a back-edge.

VER-001: structural refactor — verified by RONDO-209 cyclic import elimination.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from rondo.engine import TaskResult


class ProviderAdapter(ABC):
    """Abstract provider adapter — REQ-109 req 001.

    Every provider implements: dispatch, health, models.
    All return TaskResult (req 004: model-agnostic output).

    Concrete implementations live in rondo/adapters/{provider}.py.
    The base class lives here (provider_base.py) instead of providers.py
    so adapter modules can import the ABC without triggering a cycle
    through providers.py → adapters.health → adapters.factory.
    """

    name: str = "base"

    @abstractmethod
    def dispatch(self, prompt: str, model: str, **kwargs: Any) -> TaskResult:
        """Send prompt to provider, return TaskResult."""

    @abstractmethod
    def health(self) -> bool:
        """Check if provider is reachable."""

    @abstractmethod
    def models(self) -> list[str]:
        """List available models from this provider."""


# -- sig: mgh-6201.cd.bd955f.d209.b20114
