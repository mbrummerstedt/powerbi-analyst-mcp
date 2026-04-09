"""
Helpers for persisting large DAX query results to CSV files.

When a query returns more rows than the inline threshold, results are written
to a CSV file on disk so the MCP tool response stays compact.  A paginated
reader lets agents retrieve specific slices without loading the whole file.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path

_NAME_MAX_LEN = 40


def _sanitize_name(name: str) -> str:
    """
    Turn an arbitrary string into a safe, readable filename segment.

    - Converts to lowercase
    - Replaces runs of non-alphanumeric characters with a single underscore
    - Strips leading/trailing underscores
    - Truncates to ``_NAME_MAX_LEN`` characters
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:_NAME_MAX_LEN].rstrip("_")


def save_rows_to_csv(
    rows: list[dict],
    output_dir: str,
    name: str | None = None,
) -> str:
    """
    Write *rows* to a timestamped CSV file under *output_dir*.

    Parameters
    ----------
    rows:
        Non-empty list of dicts (all rows must share the same keys).
    output_dir:
        Directory path (absolute or relative to the server's working directory).
        Created automatically if it does not exist.
    name:
        Optional human-readable label for the file (e.g. "sales by region 2024").
        Sanitized to a safe slug and truncated to 40 characters.
        The final filename is ``dax_result_{name}_{timestamp}.csv`` when provided,
        or ``dax_result_{timestamp}.csv`` otherwise.

    Returns
    -------
    str
        Absolute path to the created CSV file.
    """
    if not rows:
        raise ValueError("rows must be non-empty")

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if name:
        slug = _sanitize_name(name)
        stem = f"dax_result_{slug}_{timestamp}" if slug else f"dax_result_{timestamp}"
    else:
        stem = f"dax_result_{timestamp}"
    file_path = path / f"{stem}.csv"

    fieldnames = list(rows[0].keys())
    with file_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return str(file_path.resolve())


def read_csv_page(
    file_path: str,
    offset: int = 0,
    limit: int = 100,
) -> dict:
    """
    Read a page of rows from a CSV file produced by :func:`save_rows_to_csv`.

    Parameters
    ----------
    file_path:
        Path to the CSV file.
    offset:
        Zero-based row offset (excluding the header row).
    limit:
        Maximum number of data rows to return.

    Returns
    -------
    dict with keys:
        rows        – list of dicts for the requested slice
        totalRows   – total number of data rows in the file
        offset      – the requested offset
        limit       – the requested limit
        hasMore     – True if rows exist beyond offset + limit
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Result file not found: {file_path}")

    all_rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        all_rows = list(reader)

    total = len(all_rows)
    page = all_rows[offset : offset + limit]

    return {
        "rows": page,
        "totalRows": total,
        "offset": offset,
        "limit": limit,
        "hasMore": (offset + limit) < total,
    }
