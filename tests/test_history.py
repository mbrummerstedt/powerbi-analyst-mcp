"""
Unit tests for powerbi_mcp/history.py.

Tests the JSONL query log: append, search, and delete operations.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from powerbi_mcp.history import (
    LOG_FILENAME,
    append_query_log,
    delete_query_log_entry,
    make_log_entry,
    search_query_log,
)


def _make_entry(
    *,
    dax_query: str = "EVALUATE Sales",
    query_summary: str | None = "Total sales",
    result_name: str | None = None,
    dataset_id: str = "ds-1",
    row_count: int = 10,
    columns: list[str] | None = None,
    csv_path: str | None = None,
    max_rows: int | None = None,
) -> dict:
    return make_log_entry(
        workspace_id="ws-1",
        dataset_id=dataset_id,
        dax_query=dax_query,
        row_count=row_count,
        columns=columns or ["col1"],
        query_summary=query_summary,
        result_name=result_name,
        csv_path=csv_path,
        max_rows=max_rows,
    )


# ---------------------------------------------------------------------------
# make_log_entry
# ---------------------------------------------------------------------------


class TestMakeLogEntry:
    def test_has_uuid_and_timestamp(self):
        entry = _make_entry()
        assert "id" in entry
        assert len(entry["id"]) == 36  # UUID4 format
        assert "timestamp" in entry
        # Should be parseable as ISO
        datetime.fromisoformat(entry["timestamp"])

    def test_includes_all_fields(self):
        entry = _make_entry(
            query_summary="Revenue by market",
            result_name="revenue_q1",
            csv_path="/tmp/result.csv",
            max_rows=500,
        )
        assert entry["workspace_id"] == "ws-1"
        assert entry["dataset_id"] == "ds-1"
        assert entry["query_summary"] == "Revenue by market"
        assert entry["dax_query"] == "EVALUATE Sales"
        assert entry["result_name"] == "revenue_q1"
        assert entry["row_count"] == 10
        assert entry["columns"] == ["col1"]
        assert entry["csv_path"] == "/tmp/result.csv"
        assert entry["max_rows"] == 500


# ---------------------------------------------------------------------------
# append_query_log
# ---------------------------------------------------------------------------


class TestAppendQueryLog:
    def test_creates_file_and_dir(self, tmp_path: Path):
        out = str(tmp_path / "subdir")
        entry = _make_entry()
        append_query_log(out, entry)
        log_file = Path(out) / LOG_FILENAME
        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["id"] == entry["id"]

    def test_appends_multiple_entries(self, tmp_path: Path):
        out = str(tmp_path)
        for i in range(3):
            append_query_log(out, _make_entry(dax_query=f"EVALUATE T{i}"))
        log_file = Path(out) / LOG_FILENAME
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 3


# ---------------------------------------------------------------------------
# search_query_log
# ---------------------------------------------------------------------------


class TestSearchQueryLog:
    def test_returns_empty_list_when_no_file(self, tmp_path: Path):
        assert search_query_log(str(tmp_path)) == []

    def test_returns_newest_first(self, tmp_path: Path):
        out = str(tmp_path)
        for i in range(5):
            append_query_log(out, _make_entry(dax_query=f"EVALUATE T{i}"))
        results = search_query_log(out, since_days=0)
        queries = [r["dax_query"] for r in results]
        assert queries == [f"EVALUATE T{i}" for i in range(4, -1, -1)]

    def test_keyword_matches_query_summary(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(query_summary="Revenue by market"))
        append_query_log(out, _make_entry(query_summary="Cost breakdown"))
        results = search_query_log(out, keyword="revenue", since_days=0)
        assert len(results) == 1
        assert results[0]["query_summary"] == "Revenue by market"

    def test_keyword_matches_dax_query(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(dax_query="EVALUATE SUMMARIZECOLUMNS('Sales'[Region])"))
        append_query_log(out, _make_entry(dax_query="EVALUATE Products"))
        results = search_query_log(out, keyword="SUMMARIZECOLUMNS", since_days=0)
        assert len(results) == 1

    def test_keyword_matches_result_name(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(result_name="gmv by market"))
        append_query_log(out, _make_entry(result_name="cost analysis"))
        results = search_query_log(out, keyword="gmv", since_days=0)
        assert len(results) == 1
        assert results[0]["result_name"] == "gmv by market"

    def test_keyword_is_case_insensitive(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(query_summary="Revenue By Market"))
        results = search_query_log(out, keyword="revenue by market", since_days=0)
        assert len(results) == 1

    def test_dataset_id_filter(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(dataset_id="ds-A"))
        append_query_log(out, _make_entry(dataset_id="ds-B"))
        results = search_query_log(out, dataset_id="ds-A", since_days=0)
        assert len(results) == 1
        assert results[0]["dataset_id"] == "ds-A"

    def test_since_days_filter(self, tmp_path: Path):
        out = str(tmp_path)
        # Write two entries: one recent, one old
        recent = _make_entry(query_summary="recent")
        old = _make_entry(query_summary="old")
        old["timestamp"] = (datetime.now() - timedelta(days=100)).isoformat()

        # Write old first, then recent (file order = chronological)
        append_query_log(out, old)
        append_query_log(out, recent)

        results = search_query_log(out, since_days=30)
        assert len(results) == 1
        assert results[0]["query_summary"] == "recent"

    def test_limit_respected(self, tmp_path: Path):
        out = str(tmp_path)
        for i in range(10):
            append_query_log(out, _make_entry(dax_query=f"EVALUATE T{i}"))
        results = search_query_log(out, since_days=0, limit=3)
        assert len(results) == 3

    def test_combined_filters(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry(dataset_id="ds-A", query_summary="Revenue Q1"))
        append_query_log(out, _make_entry(dataset_id="ds-B", query_summary="Revenue Q2"))
        append_query_log(out, _make_entry(dataset_id="ds-A", query_summary="Cost Q1"))

        results = search_query_log(out, keyword="revenue", dataset_id="ds-A", since_days=0)
        assert len(results) == 1
        assert results[0]["query_summary"] == "Revenue Q1"


# ---------------------------------------------------------------------------
# delete_query_log_entry
# ---------------------------------------------------------------------------


class TestDeleteQueryLogEntry:
    def test_removes_matching_entry(self, tmp_path: Path):
        out = str(tmp_path)
        e1 = _make_entry(query_summary="keep")
        e2 = _make_entry(query_summary="delete me")
        append_query_log(out, e1)
        append_query_log(out, e2)

        assert delete_query_log_entry(out, e2["id"]) is True

        remaining = search_query_log(out, since_days=0)
        assert len(remaining) == 1
        assert remaining[0]["id"] == e1["id"]

    def test_returns_false_when_id_not_found(self, tmp_path: Path):
        out = str(tmp_path)
        append_query_log(out, _make_entry())
        assert delete_query_log_entry(out, "nonexistent-uuid") is False

    def test_returns_false_when_no_file(self, tmp_path: Path):
        assert delete_query_log_entry(str(tmp_path), "any-id") is False

    def test_preserves_other_entries(self, tmp_path: Path):
        out = str(tmp_path)
        entries = [_make_entry(query_summary=f"entry {i}") for i in range(5)]
        for e in entries:
            append_query_log(out, e)

        delete_query_log_entry(out, entries[2]["id"])

        remaining = search_query_log(out, since_days=0)
        remaining_ids = {r["id"] for r in remaining}
        assert entries[2]["id"] not in remaining_ids
        assert len(remaining) == 4
