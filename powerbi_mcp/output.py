"""
Helpers for persisting large DAX query results to CSV files.

When a query returns more rows than the inline threshold, results are written
to a CSV file on disk so the MCP tool response stays compact.  A paginated
reader lets agents retrieve specific slices without loading the whole file.
"""

from __future__ import annotations

import csv
import os
import re
import stat
import tempfile
from datetime import datetime
from pathlib import Path

_NAME_MAX_LEN = 40
_RESULT_FILENAME = re.compile(r"dax_result_(?:[a-z0-9_]+_)?[0-9]{8}_[0-9]{6}(?:-[a-z0-9_]+)?\.csv")


def _check_regular_file(info: os.stat_result) -> None:
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise OSError("Expected a regular file without symbolic or hard links.")


def open_regular_fd(filename: str, flags: int) -> int:
    path = Path(filename)
    try:
        before = path.lstat()
        _check_regular_file(before)
    except FileNotFoundError:
        if not flags & os.O_CREAT:
            raise
        before = None

    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(fd)
        _check_regular_file(opened)
        after = path.lstat()
        _check_regular_file(after)
        if not os.path.samestat(opened, after) or (
            before is not None and not os.path.samestat(opened, before)
        ):
            raise OSError("File changed while it was being opened.")
        if flags & os.O_APPEND and os.name == "posix" and opened.st_mode & 0o077:
            os.fchmod(fd, opened.st_mode & 0o700)
    except OSError:
        os.close(fd)
        raise
    return fd


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
        Non-empty list of dicts. Missing values are written as empty cells.
    output_dir:
        Directory path (absolute or relative to the server's working directory).
        Created automatically if it does not exist.
    name:
        Optional human-readable label for the file (e.g. "sales by region 2024").
        Sanitized to a safe slug and truncated to 40 characters.
        The filename includes a timestamp and a unique suffix.

    Returns
    -------
    str
        Absolute path to the created CSV file.
    """
    if not rows:
        raise ValueError("rows must be non-empty")

    path = Path(output_dir).resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if name:
        slug = _sanitize_name(name)
        stem = f"dax_result_{slug}_{timestamp}" if slug else f"dax_result_{timestamp}"
    else:
        stem = f"dax_result_{timestamp}"
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    fd, file_path = tempfile.mkstemp(prefix=f"{stem}-", suffix=".csv", dir=path)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    except (OSError, csv.Error, UnicodeError):
        Path(file_path).unlink(missing_ok=True)
        raise

    return file_path


def read_csv_page(
    file_path: str,
    offset: int = 0,
    limit: int = 100,
    *,
    output_dir: str | None = None,
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
    output_dir:
        If provided, allow only regular result files directly in this directory.

    Returns
    -------
    dict with keys:
        rows        – list of dicts for the requested slice
        totalRows   – total number of data rows in the file
        offset      – the requested offset
        limit       – the requested limit
        hasMore     – True if rows exist beyond offset + limit
    """
    if offset < 0 or limit < 1:
        raise ValueError("Offset must be non-negative and limit must be positive.")

    path = Path(file_path)
    if output_dir is not None:
        root = Path(output_dir).resolve()
        if path.parent != root or not _RESULT_FILENAME.fullmatch(path.name):
            raise ValueError("File path must be a saved Power BI CSV in the configured output directory.")
    page = []
    total = 0
    with open(path, newline="", encoding="utf-8", opener=open_regular_fd) as fh:
        reader = csv.DictReader(fh)
        for total, row in enumerate(reader, start=1):
            if offset < total <= offset + limit:
                page.append(row)

    return {
        "rows": page,
        "totalRows": total,
        "offset": offset,
        "limit": limit,
        "hasMore": (offset + limit) < total,
    }
