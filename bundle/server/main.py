#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launch strategy:
  1. Find uv/uvx via PATH or full path relative to sys.executable
  2. Run the package; if it fails (e.g. Windows pywin32 file lock),
     retry with --no-cache to bypass the build cache entirely
  3. If uv/uvx not found: pip install uv, then retry steps 1-2
"""
import pathlib
import platform
import shutil
import subprocess
import sys
import os

PACKAGE = "powerbi-analyst-mcp"


def _candidates():
    """
    Yield (binary, base_args) pairs in preference order.
    Checks PATH first, then paths relative to sys.executable.
    uvx and 'uv tool run' are functionally identical.
    """
    python_dir = pathlib.Path(sys.executable).parent
    is_windows = platform.system() == "Windows"

    if is_windows:
        locations = [
            ("uvx", [python_dir / "Scripts" / "uvx.exe", python_dir / "uvx.exe"]),
            ("uv",  [python_dir / "Scripts" / "uv.exe",  python_dir / "uv.exe"]),
        ]
    else:
        bin_dir = python_dir.parent / "bin"
        locations = [
            ("uvx", [python_dir / "uvx", bin_dir / "uvx"]),
            ("uv",  [python_dir / "uv",  bin_dir / "uv"]),
        ]

    seen = set()

    for name, _ in locations:
        found = shutil.which(name)
        if found and found not in seen:
            seen.add(found)
            args = [PACKAGE] if name == "uvx" else ["tool", "run", PACKAGE]
            yield found, args

    for name, paths in locations:
        args = [PACKAGE] if name == "uvx" else ["tool", "run", PACKAGE]
        for p in paths:
            s = str(p)
            if p.exists() and s not in seen:
                seen.add(s)
                yield s, args


def _run_with_retry():
    """
    Try each candidate. On non-zero exit (e.g. Windows pywin32 file lock
    in uv build cache), retry the same binary with --no-cache.
    """
    for binary, args in _candidates():
        result = subprocess.run([binary] + args, env=os.environ)
        if result.returncode == 0:
            sys.exit(0)
        # Retry with --no-cache: bypasses build cache, avoids Windows
        # "file in use" errors when pywin32 DLLs are locked by another process
        # Insert --no-cache right after the binary name
        retry_args = ["--no-cache"] + args
        result = subprocess.run([binary] + retry_args, env=os.environ)
        sys.exit(result.returncode)


def main():
    # Strategy 1: uv/uvx already available
    _run_with_retry()

    # Strategy 2: install uv via pip, then retry
    # Note: pip install uv may only create uv.exe (not uvx.exe) on Windows
    print("Installing uv (one-time setup)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv", "--quiet"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install uv: {e}", file=sys.stderr)
        sys.exit(1)

    _run_with_retry()

    print(
        "Could not find uv/uvx after installing. "
        "Please report this to your administrator.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
