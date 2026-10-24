from __future__ import annotations

from pathlib import Path

from app.data.data_validator import inspect_csv


def test_inspect_csv_lists_columns_and_sample_rows(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    path.write_text("a,b\n1,2\n3,4\n", encoding="utf-8")

    report = inspect_csv(path)

    assert report["columns"] == ["a", "b"]
    assert report["num_columns"] == 2
    assert report["sample_rows"] == [{"a": 1, "b": 2}, {"a": 3, "b": 4}]


def test_inspect_csv_reports_missing_file(tmp_path: Path) -> None:
    report = inspect_csv(tmp_path / "missing.csv")

    assert "error" in report
    assert report["file"] == "missing.csv"
