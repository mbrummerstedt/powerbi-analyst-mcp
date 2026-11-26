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
import sys
import tempfile
import uuid
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from portalocker import Lock
from portalocker.exceptions import LockException

from .output import open_regular_fd

LOG_FILENAME = "powerbi_query_log.jsonl"


def _log_path(output_dir: str) -> Path:
    return Path(output_dir) / LOG_FILENAME


@contextmanager
def _log_lock(path: Path):
    try:
        with Lock(path.with_suffix(".lock"), mode="ab", timeout=5, opener=open_regular_fd):
            yield
    except LockException as exc:
        raise OSError("Could not lock query history.") from exc


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
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with _log_lock(path), open(path, "a", encoding="utf-8", opener=open_regular_fd) as fh:
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
    if since_days < 0 or limit < 0:
        raise ValueError("Since days and limit must be non-negative.")
    if limit == 0:
        return []

    path = _log_path(output_dir)
    cutoff = None
    if since_days > 0:
        now = datetime.now()
        cutoff = now - timedelta(days=min(since_days, (now - datetime.min).days))

    keyword_lower = keyword.lower() if keyword else None

    try:
        path.lstat()
    except FileNotFoundError:
        return []
    results: deque[dict] = deque(maxlen=min(limit, sys.maxsize))
    with _log_lock(path), open(path, encoding="utf-8", opener=open_regular_fd) as fh:
        for line in fh:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue

            if cutoff is not None:
                try:
                    ts = datetime.fromisoformat(entry["timestamp"])
                    if ts.tzinfo is not None:
                        ts = ts.astimezone().replace(tzinfo=None)
                    if ts < cutoff:
                        continue
                except (KeyError, TypeError, ValueError):
                    continue

            if dataset_id and entry.get("dataset_id") != dataset_id:
                continue

            if keyword_lower:
                searchable = " ".join(
                    str(entry.get(f) or "") for f in ("query_summary", "dax_query", "result_name")
                ).lower()
                if keyword_lower not in searchable:
                    continue

            results.append(entry)

    return list(reversed(results))


def delete_query_log_entry(output_dir: str, entry_id: str) -> bool:
    """
    Remove a single entry from the log by its UUID.

    Rewrites the JSONL file excluding the matching entry.

    Returns True if the entry was found and removed, False otherwise.
    """
    path = _log_path(output_dir)
    if not path.parent.is_dir():
        return False

    with _log_lock(path):
        replacement = None
        try:
            found = False
            with open(path, encoding="utf-8", opener=open_regular_fd) as source:
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", prefix=".powerbi_query_log-",
                    dir=path.parent, delete=False,
                ) as target:
                    replacement = Path(target.name)
                    for line in source:
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            entry = None
                        if isinstance(entry, dict) and entry.get("id") == entry_id:
                            found = True
                        else:
                            target.write(line)
            if found:
                replacement.replace(path)
        except FileNotFoundError:
            return False
        finally:
            if replacement is not None:
                replacement.unlink(missing_ok=True)

        return found
