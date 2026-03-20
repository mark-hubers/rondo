"""Rondo round definitions — reusable round blueprints.

Each module defines a round builder function that returns a Round object.
Rounds are declarative — they describe WHAT to check, not HOW to check it.

Modules:
    spec_health        — Overnight spec health check (staleness, sections, cross-refs)
    design_check       — 15-item design checklist (from OB Round 2)
    digest_refresh     — Refresh stale spec digests
    build_check        — Full build pipeline (ruff, bandit, mypy, pytest)
    convention_check   — Codebase convention enforcement
    cross_field_audit  — Cross-field relationship validation (OB-STD-009 Req 24, OB-SOP-006 Req 27-32)
    sprint_close       — Sprint close readiness assessment
    knowledge_mine     — Extract decisions/patterns from journal
    pr_review          — AI code review from git diff
    test_gaps          — Test coverage gap analysis
"""
