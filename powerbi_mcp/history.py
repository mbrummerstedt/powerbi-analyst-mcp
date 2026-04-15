"""
Query history log for auditability and cross-session reuse.

Every successful DAX execution is appended to a JSONL file alongside the CSV
output.  Agents can search the log to find prior queries, reuse working DAX,
and locate saved result files from earlier sessions.

The LLM acts as the semantic search layer — the ``search_query_log`` function
handles filtering and pagination, and the agent reasons over the results to
find the most relevant match.

Architecture note: if semantic embedding search is ever needed (e.g. for very
large histories), the interface stays the same — only the search implementation
in ``search_query_log`` would change to query a vector store instead of
scanning the JSONL file.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

LOG_FILENAME = "powerbi_query_log.jsonl"


def _log_path(output_dir: str) -> Path:
    return Path(output_dir) / LOG_FILENAME


def make_log_entry(
    *,
    dataset_id: str,
    dax_query: str,
    row_count: int,
    columns: list[str],
    query_summary: str | None = None,
    result_name: str | None = None,
    csv_path: str | None = None,
    max_rows: int | None = None,
) -> dict:
    """Build a log entry dict with a fresh UUID and timestamp."""
    return {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "dataset_id": dataset_id,
        "query_summary": query_summary,
        "dax_query": dax_query,
        "result_name": result_name,
        "row_count": row_count,
        "columns": columns,
        "csv_path": csv_path,
        "max_rows": max_rows,
    }


def append_query_log(output_dir: str, entry: dict) -> None:
    """
    Append a single log entry to the JSONL history file.

    Creates the output directory and log file if they do not exist.
    """
    path = _log_path(output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def search_query_log(
    output_dir: str,
    *,
    keyword: str | None = None,
    dataset_id: str | None = None,
    since_days: int = 90,
    limit: int = 20,
) -> list[dict]:
    """
    Search the query log, returning up to *limit* matching entries newest-first.

    Parameters
    ----------
    output_dir:
        Directory containing the JSONL log file.
    keyword:
        Case-insensitive substring matched against ``query_summary``,
        ``dax_query``, and ``result_name``.
    dataset_id:
        If provided, only entries for this dataset are returned.
    since_days:
        Only return entries from the last N days. Use ``0`` for all time.
    limit:
        Maximum number of entries to return (default 20).

    Returns
    -------
    list[dict]
        Matching entries, newest first. Empty list if the log file does not
        exist or no entries match.
    """
    path = _log_path(output_dir)
    if not path.exists():
        return []

    cutoff = None
    if since_days > 0:
        cutoff = datetime.now() - timedelta(days=since_days)

    keyword_lower = keyword.lower() if keyword else None

    # Read all lines, reverse for newest-first, filter, collect up to limit.
    with path.open(encoding="utf-8") as fh:
        lines = fh.readlines()

    results: list[dict] = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Time filter
        if cutoff is not None:
            try:
                ts = datetime.fromisoformat(entry["timestamp"])
                if ts < cutoff:
                    # Since we're reading newest-first and entries are appended
                    # chronologically, once we hit an entry older than the
                    # cutoff we can stop entirely.
                    break
            except (KeyError, ValueError):
                continue

        # Dataset filter
        if dataset_id and entry.get("dataset_id") != dataset_id:
            continue

        # Keyword filter (matches query_summary, dax_query, result_name)
        if keyword_lower:
            searchable = " ".join(
                str(entry.get(f) or "") for f in ("query_summary", "dax_query", "result_name")
            ).lower()
            if keyword_lower not in searchable:
                continue

        results.append(entry)
        if len(results) >= limit:
            break

    return results


def delete_query_log_entry(output_dir: str, entry_id: str) -> bool:
    """
    Remove a single entry from the log by its UUID.

    Rewrites the JSONL file excluding the matching entry.

    Returns True if the entry was found and removed, False otherwise.
    """
    path = _log_path(output_dir)
    if not path.exists():
        return False

    with path.open(encoding="utf-8") as fh:
        lines = fh.readlines()

    found = False
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except json.JSONDecodeError:
            kept.append(line)
            continue
        if entry.get("id") == entry_id:
            found = True
        else:
            kept.append(line)

    if found:
        with path.open("w", encoding="utf-8") as fh:
            fh.writelines(kept)

    return found
