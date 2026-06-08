# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
"""AST mutation gate — RONDO-363: prove tests bite.

Rondo-VER-100 verification: mutation-adequacy gate — a test only counts if it
FAILS when the code it guards is wrong. This is the mechanical backstop for the
verification map.

For each small, behavior-changing mutation of a source file, the test suite
MUST fail (catch it). A surviving mutant — tests still green with broken code —
is a coverage/assertion gap, i.e. a test that would pass when the code is
wrong. This trusts no one: it is mechanical, not opinion. It is the backstop
behind separation-of-duties (a different agent writing the tests reduces
collusion; this proves the tests actually fail when they should).

Pure stdlib (ast), leaf module — no rondo imports, so any module can be the
subject without import cycles. Operators are deliberately small and semantic:
    a > b      -> a >= b        (comparison boundary)
    a and b    -> a or b        (boolean logic)
    True       -> False         (boolean literal)
    n          -> n + 1         (integer literal off-by-one)
    a + b      -> a - b         (arithmetic)
    return x   -> return None   (dropped result)
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

# -- Comparison + arithmetic flip tables, built from reversible pairs so each
# -- op maps to its boundary/inverse both ways (a > b <-> a >= b, etc.).
_CMP_PAIRS: list[tuple[type[ast.cmpop], type[ast.cmpop]]] = [
    (ast.Gt, ast.GtE),
    (ast.Lt, ast.LtE),
    (ast.Eq, ast.NotEq),
]
_CMP_FLIP: dict[type[ast.cmpop], type[ast.cmpop]] = {a: b for a, b in _CMP_PAIRS} | {b: a for a, b in _CMP_PAIRS}
_BIN_FLIP: dict[type[ast.operator], type[ast.operator]] = {ast.Add: ast.Sub, ast.Sub: ast.Add}


@dataclass
class Mutant:
    """One applied mutation: where it landed and what it did."""

    line: int
    operator: str
    snippet: str


@dataclass
class MutationOutcome:
    """A mutant plus whether the test suite CAUGHT it (failed)."""

    mutant: Mutant
    caught: bool


class _Mutator(ast.NodeTransformer):
    """Apply exactly ONE mutation — the `target`-th mutable site encountered.

    Walks deterministically (depth-first). With target=-1 it mutates nothing,
    which is how callers count the total number of mutable sites (self.seen).
    """

    def __init__(self, target: int) -> None:
        self.target = target
        self.seen = 0
        self.applied: Mutant | None = None

    def _site(self, node: ast.AST, operator: str, snippet: str) -> bool:
        """Register a mutable site; return True iff THIS one is the target."""
        idx = self.seen
        self.seen += 1
        if idx == self.target:
            self.applied = Mutant(line=getattr(node, "lineno", 0), operator=operator, snippet=snippet)
            return True
        return False

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """Flip the first comparison op at its boundary (> <-> >=, == <-> !=)."""
        self.generic_visit(node)
        if node.ops and type(node.ops[0]) in _CMP_FLIP and self._site(node, "compare", ast.unparse(node)):
            node.ops[0] = _CMP_FLIP[type(node.ops[0])]()
        return node

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        """Swap boolean logic: and <-> or."""
        self.generic_visit(node)
        if self._site(node, "boolop", ast.unparse(node)):
            node.op = ast.Or() if isinstance(node.op, ast.And) else ast.And()
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        """Swap arithmetic: + <-> -."""
        self.generic_visit(node)
        if type(node.op) in _BIN_FLIP and self._site(node, "arith", ast.unparse(node)):
            node.op = _BIN_FLIP[type(node.op)]()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        """Flip a bool literal, or bump an int literal by one (off-by-one)."""
        self.generic_visit(node)
        if isinstance(node.value, bool):
            if self._site(node, "bool-literal", repr(node.value)):
                return ast.Constant(value=not node.value)
        elif isinstance(node.value, int) and self._site(node, "int-literal", repr(node.value)):
            return ast.Constant(value=node.value + 1)
        return node

    def visit_Return(self, node: ast.Return) -> ast.AST:
        """Drop a returned value: `return x` -> `return None`."""
        self.generic_visit(node)
        if node.value is not None and self._site(node, "return-none", ast.unparse(node)):
            node.value = ast.Constant(value=None)
        return node


def _count_sites(source: str) -> int:
    """Count mutable sites without changing the tree (target=-1 = no-op)."""
    counter = _Mutator(target=-1)
    counter.visit(ast.parse(source))
    return counter.seen


def generate_mutants(source: str) -> list[tuple[Mutant, str]]:
    """Return [(Mutant, mutated_source)] — one entry per mutable site.

    Re-parses the source for each mutant so every mutation is independent and
    the walk order stays identical to the counting pass.
    """
    total = _count_sites(source)
    out: list[tuple[Mutant, str]] = []
    for idx in range(total):
        mutator = _Mutator(target=idx)
        tree = mutator.visit(ast.parse(source))
        ast.fix_missing_locations(tree)
        if mutator.applied is not None:
            out.append((mutator.applied, ast.unparse(tree)))
    return out


def run_mutation_gate(file_path: str, run_tests: Callable[[], bool]) -> list[MutationOutcome]:
    """Mutate `file_path` one site at a time; record which mutants tests CATCH.

    `run_tests()` returns True when the suite FAILS (mutant caught). The
    original file is ALWAYS restored — even if run_tests raises — so a crash
    never leaves mutated code on disk.
    """
    path = Path(file_path)
    original = path.read_text(encoding="utf-8")
    outcomes: list[MutationOutcome] = []
    try:
        for mutant, mutated in generate_mutants(original):
            path.write_text(mutated, encoding="utf-8")
            outcomes.append(MutationOutcome(mutant=mutant, caught=bool(run_tests())))
    finally:
        path.write_text(original, encoding="utf-8")
    return outcomes


def _pytest_runner(tests: str) -> Callable[[], bool]:
    """Build a run_tests() that runs pytest on `tests` in a fresh subprocess.

    Subprocess (not in-process) so each mutated source is imported fresh —
    no module caching masking the mutation. Returns True when pytest FAILS.
    """
    import subprocess  # nosec B404 -- project policy: subprocess is core (pyproject skips B404)  # pylint: disable=import-outside-toplevel

    def _run() -> bool:
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests.split()]
        # -- nosec B603: no shell, fixed argv, pytest target is a developer-supplied
        # -- path/expr run locally — same accepted pattern as dispatch.py.
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)  # nosec B603
        return proc.returncode != 0

    return _run


def _report(source: str, outcomes: list[MutationOutcome]) -> int:
    """Print survivors + a score line. Return process exit code (1 if any survived)."""
    survivors = [o for o in outcomes if not o.caught]
    for out in survivors:
        m = out.mutant
        sys.stdout.write(f"-SURVIVED- {source}:{m.line} [{m.operator}] {m.snippet}\n")
    total = len(outcomes)
    caught = total - len(survivors)
    if total == 0:
        sys.stdout.write(f"-WARNING- no mutable sites found in {source}\n")
        return 0
    status = "-PASS-" if not survivors else "-FAIL-"
    sys.stdout.write(f"{status} {caught}/{total} mutants caught ({len(survivors)} survived) in {source}\n")
    return 1 if survivors else 0


def main(argv: list[str] | None = None) -> int:
    """CLI: mutate a source file and fail if any mutant survives the tests."""
    import argparse  # pylint: disable=import-outside-toplevel

    parser = argparse.ArgumentParser(description="Mutation gate: prove tests fail when code is wrong.")
    parser.add_argument("source", help="source .py file to mutate")
    parser.add_argument("--tests", required=True, help="pytest target(s) to run per mutant (path or -k expr)")
    args = parser.parse_args(argv)
    outcomes = run_mutation_gate(args.source, _pytest_runner(args.tests))
    return _report(args.source, outcomes)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


# -- sig: mgh-6201.cd.bd955f.4fc8.2bd888
