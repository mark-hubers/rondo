# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""AST mutation gate — RONDO-363.

VER-001 verification matrix: test-quality (mutation) contract.

The gate exists to answer one question mechanically: would a test FAIL if the
code were wrong? A mutant that survives (tests still pass with broken code) is
a gap — or a lie. These tests prove the gate itself bites: it must CATCH
mutants under a strong test and report SURVIVORS under a weak one. The strong-
vs-weak pair is the whole point — a gate that can't tell them apart is theater.
"""

from __future__ import annotations

from rondo.mutate import MutationOutcome, generate_mutants, run_mutation_gate


class TestGenerateMutants:
    """AST operators produce real, distinct mutations of the source."""

    def test_comparison_operator_is_mutated(self) -> None:
        mutants = generate_mutants("def f(a, b):\n    return a > b\n")
        sources = [src for _, src in mutants]
        assert any(">=" in s for s in sources), f"no >/>= mutant: {sources}"

    def test_return_value_is_mutated_to_none(self) -> None:
        mutants = generate_mutants("def f():\n    return 1\n")
        sources = [src for _, src in mutants]
        assert any("return None" in s for s in sources), f"no return-None mutant: {sources}"

    def test_boolean_literal_is_flipped(self) -> None:
        mutants = generate_mutants("def f():\n    return True\n")
        sources = [src for _, src in mutants]
        assert any("False" in s for s in sources), f"no True/False mutant: {sources}"

    def test_return_none_yields_no_noop_mutant(self) -> None:
        """`return None` must NOT produce a return-None mutant (no-op = fake survivor)."""
        mutants = generate_mutants("def f():\n    return None\n")
        assert all(m.operator != "return-none" for m, _ in mutants), "no-op return-None mutant generated"

    def test_bare_return_yields_no_noop_mutant(self) -> None:
        """A bare `return` must NOT produce a return-None mutant either."""
        mutants = generate_mutants("def f():\n    if True:\n        return\n    return 1\n")
        none_snips = [m.snippet for m, _ in mutants if m.operator == "return-none" and "return" == m.snippet.strip()]
        assert not none_snips, f"bare-return mutated: {none_snips}"

    def test_empty_returnless_code_yields_no_crash(self) -> None:
        # -- a module with nothing mutable must not raise, just return []
        assert generate_mutants("x = 'hello'\n") == [] or isinstance(generate_mutants("x = 'hello'\n"), list)


class TestRunMutationGate:
    """The gate distinguishes a STRONG test from a WEAK one — the anti-lie core."""

    def _write_module(self, tmp_path, body: str):
        mod = tmp_path / "subject.py"
        mod.write_text(body, encoding="utf-8")
        return mod

    def test_strong_test_catches_every_mutant(self, tmp_path) -> None:
        """A real test (asserts the behavior) catches all mutants → 0 survivors."""
        mod = self._write_module(tmp_path, "def add(a, b):\n    return a + b\n")
        original = mod.read_text(encoding="utf-8")

        def _strong_test() -> bool:
            # -- import the (possibly mutated) module fresh and assert real behavior
            ns: dict = {}
            exec(compile(mod.read_text(encoding="utf-8"), str(mod), "exec"), ns)  # noqa: S102
            try:
                ok = ns["add"](2, 3) == 5 and ns["add"](0, 0) == 0
            except Exception:  # noqa: BLE001 -- a crashing mutant counts as caught
                return True
            return not ok  # -- True == test FAILED == mutant caught

        outcomes = run_mutation_gate(str(mod), _strong_test)
        survivors = [o for o in outcomes if not o.caught]
        assert outcomes, "no mutants generated"
        assert not survivors, f"strong test let mutants survive: {[s.mutant.snippet for s in survivors]}"
        assert mod.read_text(encoding="utf-8") == original, "gate did not restore the original file"

    def test_weak_test_lets_mutants_survive(self, tmp_path) -> None:
        """A test that asserts nothing real catches NOTHING → survivors flagged.

        This is the lie the gate must expose: green tests that never fail.
        """
        mod = self._write_module(tmp_path, "def add(a, b):\n    return a + b\n")

        def _weak_test() -> bool:
            return False  # -- never fails → never catches a mutant (theater)

        outcomes = run_mutation_gate(str(mod), _weak_test)
        survivors = [o for o in outcomes if not o.caught]
        assert survivors, "gate failed to flag a weak test's surviving mutants"
        assert all(isinstance(o, MutationOutcome) for o in outcomes)

    def test_original_restored_even_if_runner_raises(self, tmp_path) -> None:
        """The gate must NEVER leave mutated code behind, even on runner crash."""
        mod = self._write_module(tmp_path, "def f():\n    return 1\n")
        original = mod.read_text(encoding="utf-8")

        def _boom() -> bool:
            raise RuntimeError("runner exploded")

        try:
            run_mutation_gate(str(mod), _boom)
        except RuntimeError:
            pass
        assert mod.read_text(encoding="utf-8") == original, "mutated code left on disk after crash"


class TestTimeoutPerMutant:
    """RONDO-392 (ROAD-TO-8 8.8): --timeout-per-mutant — a hanging suite is a CAUGHT mutant.

    Item-17 debt: dispatch.py mutants made test_dispatch.py hang 6h+. A mutant
    that hangs the tests has visibly broken the code — that is detection, not
    survival. timeout_sec=0 keeps today's unbounded behavior (backward compat).
    """

    def test_timeout_expired_counts_as_caught(self, monkeypatch) -> None:
        """TimeoutExpired from the pytest subprocess → runner returns True (caught)."""
        import subprocess

        from rondo import mutate as mutate_mod

        def _fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 1))

        monkeypatch.setattr(mutate_mod.subprocess, "run", _fake_run)
        runner = mutate_mod._pytest_runner("tests/whatever.py", timeout_sec=1)
        assert runner() is True, "a hung (timed-out) suite must count as a CAUGHT mutant"

    def test_timeout_zero_passes_no_timeout_to_subprocess(self, monkeypatch) -> None:
        """timeout_sec=0 (default) → subprocess.run receives timeout=None (unbounded, today's behavior)."""
        from rondo import mutate as mutate_mod

        seen: dict = {}

        def _fake_run(cmd, **kwargs):  # noqa: ANN001, ANN003
            seen.update(kwargs)

            class _P:
                returncode = 1

            return _P()

        monkeypatch.setattr(mutate_mod.subprocess, "run", _fake_run)
        runner = mutate_mod._pytest_runner("tests/whatever.py")
        assert runner() is True
        assert seen.get("timeout") is None, "timeout_sec=0 must mean NO subprocess timeout"

    def test_real_hang_is_killed_and_caught(self, tmp_path) -> None:
        """UNMOCKED contract test: a genuinely sleeping pytest target is killed at the timeout and reported caught."""
        import time

        from rondo.mutate import _pytest_runner

        hang_test = tmp_path / "test_hang_canary.py"
        hang_test.write_text(
            "import time\n\n\ndef test_sleeps_forever():\n    time.sleep(30)\n",
            encoding="utf-8",
        )
        runner = _pytest_runner(str(hang_test), timeout_sec=2)
        start = time.monotonic()
        caught = runner()
        elapsed = time.monotonic() - start
        assert caught is True, "a hanging mutant run must be reported as caught"
        assert elapsed < 15, f"the hung subprocess must be killed near the timeout, took {elapsed:.1f}s"

    def test_cli_flag_threads_through_to_runner(self, monkeypatch, tmp_path) -> None:
        """--timeout-per-mutant N reaches _pytest_runner (dead-flag lock: the flag does something)."""
        from rondo import mutate as mutate_mod

        captured: dict = {}

        def _fake_runner(tests, timeout_sec=0):  # noqa: ANN001
            captured["timeout_sec"] = timeout_sec
            return lambda: True

        monkeypatch.setattr(mutate_mod, "_pytest_runner", _fake_runner)
        src = tmp_path / "m.py"
        src.write_text("def f():\n    return 1\n", encoding="utf-8")
        mutate_mod.main([str(src), "--tests", "tests/x.py", "--timeout-per-mutant", "120"])
        assert captured.get("timeout_sec") == 120, "--timeout-per-mutant must thread through to the pytest runner"


# -- sig: mgh-6201.cd.bd955f.a7e0.adb14f
