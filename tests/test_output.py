"""
Unit tests for powerbi_mcp/output.py — CSV save and page-read helpers.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from powerbi_mcp.output import read_csv_page, save_rows_to_csv


# ---------------------------------------------------------------------------
# save_rows_to_csv
# ---------------------------------------------------------------------------


class TestSaveRowsToCsv:
    def test_creates_directory_if_missing(self, tmp_path: Path):
        output_dir = str(tmp_path / "subdir" / "nested")
        rows = [{"a": 1, "b": 2}]
        path = save_rows_to_csv(rows, output_dir)
        assert Path(path).exists()

    def test_returns_absolute_path(self, tmp_path: Path):
        rows = [{"x": "hello"}]
        path = save_rows_to_csv(rows, str(tmp_path))
        assert Path(path).is_absolute()

    def test_filename_contains_dax_result_prefix(self, tmp_path: Path):
        rows = [{"x": 1}]
        path = save_rows_to_csv(rows, str(tmp_path))
        assert Path(path).name.startswith("dax_result_")

    def test_csv_contains_correct_header_and_rows(self, tmp_path: Path):
        rows = [{"Year": 2024, "Sales": 1000}, {"Year": 2025, "Sales": 2000}]
        path = save_rows_to_csv(rows, str(tmp_path))
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            written = list(reader)
        assert [r["Year"] for r in written] == ["2024", "2025"]
        assert [r["Sales"] for r in written] == ["1000", "2000"]

    def test_raises_on_empty_rows(self, tmp_path: Path):
        with pytest.raises(ValueError, match="non-empty"):
            save_rows_to_csv([], str(tmp_path))

    def test_custom_name_appears_in_filename(self, tmp_path: Path):
        rows = [{"x": 1}]
        path = save_rows_to_csv(rows, str(tmp_path), name="sales by region 2024")
        assert "sales_by_region_2024" in Path(path).name

    def test_custom_name_truncated_to_40_chars(self, tmp_path: Path):
        rows = [{"x": 1}]
        long_name = "a" * 60
        path = save_rows_to_csv(rows, str(tmp_path), name=long_name)
        # slug part should be at most 40 chars
        stem = Path(path).stem  # e.g. dax_result_aaa...a_20260305_143022
        # strip leading "dax_result_" and trailing "_YYYYMMDD_HHMMSS"
        inner = stem[len("dax_result_"):]
        slug_part = "_".join(inner.split("_")[:-2])  # remove last two timestamp segments
        assert len(slug_part) <= 40

    def test_no_name_falls_back_to_timestamp_only(self, tmp_path: Path):
        rows = [{"x": 1}]
        path = save_rows_to_csv(rows, str(tmp_path))
        # name should be dax_result_YYYYMMDD_HHMMSS — no extra segment between
        parts = Path(path).stem.split("_")
        assert parts[0] == "dax"
        assert parts[1] == "result"
        # third segment is date, fourth is time — no extra word segments
        assert len(parts) == 4

    def test_special_characters_sanitized(self, tmp_path: Path):
        rows = [{"x": 1}]
        path = save_rows_to_csv(rows, str(tmp_path), name="Q1/2024 -- Revenue & Costs!")
        filename = Path(path).name
        assert "/" not in filename
        assert "&" not in filename
        assert "!" not in filename
        assert "q1" in filename.lower()


# ---------------------------------------------------------------------------
# read_csv_page
# ---------------------------------------------------------------------------


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


class TestReadCsvPage:
    def _sample_rows(self, n: int = 10) -> list[dict]:
        return [{"id": i, "value": f"v{i}"} for i in range(n)]

    def test_returns_first_page(self, tmp_path: Path):
        rows = self._sample_rows(10)
        f = tmp_path / "test.csv"
        _write_csv(f, rows)
        result = read_csv_page(str(f), offset=0, limit=5)
        assert len(result["rows"]) == 5
        assert result["rows"][0]["id"] == "0"
        assert result["totalRows"] == 10
        assert result["hasMore"] is True
        assert result["offset"] == 0
        assert result["limit"] == 5

    def test_returns_last_page(self, tmp_path: Path):
        rows = self._sample_rows(10)
        f = tmp_path / "test.csv"
        _write_csv(f, rows)
        result = read_csv_page(str(f), offset=8, limit=5)
        assert len(result["rows"]) == 2
        assert result["hasMore"] is False

    def test_offset_beyond_end_returns_empty(self, tmp_path: Path):
        rows = self._sample_rows(5)
        f = tmp_path / "test.csv"
        _write_csv(f, rows)
        result = read_csv_page(str(f), offset=10, limit=5)
        assert result["rows"] == []
        assert result["hasMore"] is False
        assert result["totalRows"] == 5

    def test_exact_last_row(self, tmp_path: Path):
        rows = self._sample_rows(10)
        f = tmp_path / "test.csv"
        _write_csv(f, rows)
        result = read_csv_page(str(f), offset=9, limit=1)
        assert len(result["rows"]) == 1
        assert result["hasMore"] is False

    def test_raises_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            read_csv_page(str(tmp_path / "missing.csv"))
