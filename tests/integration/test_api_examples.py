# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""Living tests for Rondo API examples — every example runs, every run is a test.

Each example in rondo/examples/api/ has a main() function.
This test file imports and runs each one, verifying they don't crash.
If an example breaks, the build breaks.

VER-001: Product acceptance / integration test coverage.
"""

from __future__ import annotations

import importlib.util
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

# -- Find the examples directory
EXAMPLES_API_DIR = Path(__file__).parent.parent.parent / "examples" / "api"

# -- RONDO-262: examples import from example_dispatch.py in their own directory
if str(EXAMPLES_API_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLES_API_DIR))

# -- Discover all example files (exclude helper libraries like example_dispatch.py)
_EXAMPLE_FILES = sorted(f for f in EXAMPLES_API_DIR.glob("*.py") if f.stem != "example_dispatch")


def _load_example(filepath: Path):
    """Dynamically import an example module."""
    name = filepath.stem
    spec = importlib.util.spec_from_file_location(f"example_{name}", filepath)
    if spec is None or spec.loader is None:
        pytest.skip(f"Cannot load {filepath}")
    module = importlib.util.module_from_spec(spec)
    # -- Prevent example from polluting sys.modules
    old_modules = set(sys.modules.keys())
    try:
        spec.loader.exec_module(module)
    finally:
        # -- Clean up any modules the example added
        new_modules = set(sys.modules.keys()) - old_modules
        for mod in new_modules:
            if mod.startswith("example_"):
                del sys.modules[mod]
    return module


class TestAPIExamplesRun:
    """Every API example runs without errors."""

    @pytest.fixture(autouse=True)
    def _stub_outside_world(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RONDO-362: stub the two outside-world seams so the build is hermetic.

        Examples are LIVE-by-default for a human running them, but in the build
        they must not make real (paid, flaky, ~180s-timeout) dispatches. We stub
        the lowest-common seams so every high-level path (rondo_run_file,
        rondo_multi_review, rondo_benchmark, ...) still builds its OWN envelope
        shape from a fake response — this verifies example LOGIC/wiring (the real
        test intent: "they don't crash") without any network or subprocess.

        Before this, ~12 example tests each hit the 180s subprocess timeout and
        "passed" on the degraded result — so live coverage was already fake while
        costing ~10 min (and possibly real API spend on a keyed machine).
        """
        from rondo import dispatch as _dispatch

        def _fake_subprocess(
            cmd: list[str],
            env: dict[str, str],
            timeout_sec: int,
            cwd: str = "",
            watchdog_sec: int = 0,
            stdin_text: str = "",
        ) -> tuple[str, str, int, bool]:
            # -- (stdout, stderr, returncode, timed_out): benign JSON success.
            return ('{"status": "ok", "result": "hermetic-stub"}', "", 0, False)

        monkeypatch.setattr(_dispatch, "_run_subprocess", _fake_subprocess)

        # -- HTTP seam: raise a NON-transient (4xx) error so retry_http fails
        # -- FAST. A transient error (429/5xx/URLError) would trip our own
        # -- hardened backoff and reintroduce the slowness we're removing.
        def _fake_urlopen(*args: object, **kwargs: object) -> object:
            # -- 401 is NON-transient (4xx, not 429), so retry_http raises at once.
            # -- A 5xx/429/URLError would be retried with backoff — reintroducing slowness.
            raise urllib.error.HTTPError(
                url="https://hermetic-stub", code=401, msg="stub: no live HTTP in build", hdrs=None, fp=None
            )

        monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    @pytest.mark.parametrize(
        "example_file",
        _EXAMPLE_FILES,
        ids=[f.stem for f in _EXAMPLE_FILES],
    )
    def test_example_main_runs(self, example_file: Path) -> None:
        """Import and run example's main() — must not raise."""
        module = _load_example(example_file)
        if not hasattr(module, "main"):
            pytest.skip(f"{example_file.name} has no main()")
        # -- RONDO-262: examples use argparse which conflicts with pytest's sys.argv.
        # -- Temporarily set sys.argv to just the script name so argparse works.
        old_argv = sys.argv
        sys.argv = [str(example_file)]
        try:
            module.main()
        except SystemExit as exc:
            # -- Examples return 0 (success) or 1 (findings/warnings) — both are OK
            if exc.code not in (0, 1, None):
                raise
        finally:
            sys.argv = old_argv

    def test_at_least_7_api_examples(self) -> None:
        """We promised 7+ API examples."""
        assert len(_EXAMPLE_FILES) >= 7, f"Only {len(_EXAMPLE_FILES)} API examples (need 7+)"


class TestAPIExamplesQuality:
    """Examples are self-documenting — docstrings, comments, structure."""

    @pytest.mark.parametrize(
        "example_file",
        _EXAMPLE_FILES,
        ids=[f.stem for f in _EXAMPLE_FILES],
    )
    def test_has_module_docstring(self, example_file: Path) -> None:
        """Every example has a module-level docstring."""
        content = example_file.read_text(encoding="utf-8")
        assert content.startswith('"""') or content.startswith("# SPDX"), (
            f"{example_file.name} must start with a docstring or SPDX header"
        )

    @pytest.mark.parametrize(
        "example_file",
        _EXAMPLE_FILES,
        ids=[f.stem for f in _EXAMPLE_FILES],
    )
    def test_has_main_guard(self, example_file: Path) -> None:
        """Every example has if __name__ == '__main__' guard."""
        content = example_file.read_text(encoding="utf-8")
        assert "__name__" in content and "__main__" in content, f"{example_file.name} must have __main__ guard"


# -- sig: mgh-6201.cd.bd955f.4150.59066e
