import csv

import pytest

from csv_report_refined import category_totals, make_report, top_category


def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def test_make_report_happy_path_with_absolute_path_containing_spaces(tmp_path):
    report_dir = tmp_path / "reports with spaces"
    report_dir.mkdir()
    csv_path = report_dir / "spending data.csv"
    _write_csv(
        csv_path,
        [
            ["category", "date", "amount"],
            ["Food", "2024-01-01", "10.25"],
            ["Books", "2024-01-02", "7"],
            ["Food", "2024-01-03", "2.5"],
        ],
    )

    absolute_path = csv_path.resolve()
    assert absolute_path.is_absolute()
    assert make_report(str(absolute_path)) == "\n".join(
        [
            "Spending report",
            "===============",
            "Books: 7.0",
            "Food: 12.75",
            "Top category: Food",
        ]
    )


def test_make_report_missing_file_raises(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError):
        make_report(str(missing_path))


def test_make_report_malformed_row_raises(tmp_path):
    csv_path = tmp_path / "malformed.csv"
    csv_path.write_text(
        "category,date,amount\n"
        "Food,2024-01-01\n",
        encoding="utf-8",
    )

    with pytest.raises(IndexError):
        make_report(str(csv_path))


def test_make_report_invalid_date_format_raises_value_error(tmp_path):
    csv_path = tmp_path / "invalid-date.csv"
    _write_csv(
        csv_path,
        [
            ["category", "date", "amount"],
            ["Food", "01/02/2024", "10.25"],
        ],
    )

    with pytest.raises(ValueError):
        make_report(str(csv_path))


def test_category_totals_malformed_amount_raises_value_error():
    rows = [
        ["category", "date", "amount"],
        ["Food", "2024-01-01", "not-a-number"],
    ]

    with pytest.raises(ValueError):
        category_totals(rows)


@pytest.mark.parametrize("amount", ["-1", "0", "-0.01"])
def test_category_totals_non_positive_amounts_raise_value_error(amount):
    rows = [
        ["category", "date", "amount"],
        ["Food", "2024-01-01", amount],
    ]

    with pytest.raises(ValueError):
        category_totals(rows)


@pytest.mark.parametrize("bad_path", [None, 123])
def test_make_report_non_string_inputs_raise(bad_path):
    with pytest.raises((TypeError, OSError)):
        make_report(bad_path)


def test_make_report_empty_file_has_no_categories(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    assert make_report(str(csv_path)) == "\n".join(
        [
            "Spending report",
            "===============",
            "Top category: None",
        ]
    )


def test_make_report_header_only_csv_has_no_categories(tmp_path):
    csv_path = tmp_path / "headers-only.csv"
    _write_csv(csv_path, [["category", "date", "amount"]])

    assert make_report(str(csv_path)) == "\n".join(
        [
            "Spending report",
            "===============",
            "Top category: None",
        ]
    )


def test_category_totals_duplicate_categories_are_summed():
    rows = [
        ["category", "date", "amount"],
        ["Food", "2024-01-01", "10.25"],
        ["Books", "2024-01-02", "7"],
        ["Food", "2024-01-03", "2.5"],
    ]

    assert category_totals(rows) == {"Food": 12.75, "Books": 7.0}


def test_make_report_handles_quoted_special_characters_in_category_names(tmp_path):
    csv_path = tmp_path / "special-categories.csv"
    _write_csv(
        csv_path,
        [
            ["category", "date", "amount"],
            ["Food, dining", "2024-01-01", "3.5"],
            ["Cafe\nTea", "2024-01-02", "2"],
        ],
    )

    assert make_report(str(csv_path)) == "\n".join(
        [
            "Spending report",
            "===============",
            "Cafe\nTea: 2.0",
            "Food, dining: 3.5",
            "Top category: Food, dining",
        ]
    )


def test_top_category_tie_returns_first_inserted_category():
    totals = {}
    totals["Food"] = 10.0
    totals["Books"] = 10.0
    totals["Travel"] = 3.0

    assert top_category(totals) == "Food"


def test_top_category_all_zero_amounts_returns_first_inserted_category():
    totals = {}
    totals["Food"] = 0.0
    totals["Books"] = 0.0
    totals["Travel"] = 0.0

    assert top_category(totals) == "Food"
