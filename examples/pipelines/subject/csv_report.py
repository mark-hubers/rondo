# SPDX-FileCopyrightText: 2026 Mark Hubers
# SPDX-License-Identifier: MIT
#
# INTENTIONALLY BARE — this is the code-refine pipeline's SUBJECT, the
# "before" state: no docstrings, no type hints, no error handling, bare
# print. The pipeline (examples/pipelines/code-refine.yaml) improves it
# step by step; quality tooling complaints about THIS file are the point.
# ruff: noqa
import sys


def load_rows(path):
    rows = []
    for line in open(path):
        parts = line.strip().split(",")
        rows.append(parts)
    return rows


def category_totals(rows):
    totals = {}
    for row in rows[1:]:
        category = row[0]
        amount = float(row[2])
        if category in totals:
            totals[category] = totals[category] + amount
        else:
            totals[category] = amount
    return totals


def top_category(totals):
    best = None
    for name in totals:
        if best is None or totals[name] > totals[best]:
            best = name
    return best


def make_report(path):
    rows = load_rows(path)
    totals = category_totals(rows)
    lines = ["Spending report", "==============="]
    for name in sorted(totals):
        lines.append(name + ": " + str(round(totals[name], 2)))
    lines.append("Top category: " + str(top_category(totals)))
    return "\n".join(lines)


if __name__ == "__main__":
    print(make_report(sys.argv[1]))
