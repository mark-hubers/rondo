"""Rondo round definitions — reusable round blueprints.

Each module defines a round builder function that returns a Round object.
Rounds are declarative — they describe WHAT to check, not HOW to check it.

Modules:
    spec_health    — Overnight spec health check (staleness, sections, cross-refs)
    design_check   — 15-item design checklist (from OB Round 2)
"""
