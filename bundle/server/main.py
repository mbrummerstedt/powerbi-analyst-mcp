#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launch strategy (in order):
  1. uvx / uv tool run on PATH         — already installed system-wide
  2. pip install uv, then retry        — bootstraps uv, calls via full path
     uvx.exe and uv.exe both checked   — pip install uv may only create uv.exe
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
    Yield (binary_path, args) pairs to try, in preference order.
    Checks both PATH and common install locations relative to sys.executable.
    uvx and uv tool run are functionally identical.
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

    # PATH first
    for name, _ in locations:
        found = shutil.which(name)
        if found:
            args = [PACKAGE] if name == "uvx" else ["tool", "run", PACKAGE]
            yield found, args

    # Known install locations relative to sys.executable
    for name, paths in locations:
        args = [PACKAGE] if name == "uvx" else ["tool", "run", PACKAGE]
        for p in paths:
            if p.exists():
                yield str(p), args


def _run():
    for binary, args in _candidates():
        result = subprocess.run([binary] + args, env=os.environ)
        sys.exit(result.returncode)


def main():
    # Strategy 1: uv/uvx already available
    _run()

    # Strategy 2: install uv via pip, then call via full path
    # Note: pip install uv may create only uv.exe (not uvx.exe) on Windows
    print("Installing uv (one-time setup)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv", "--quiet"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install uv: {e}", file=sys.stderr)
        sys.exit(1)

    _run()

    print(
        "Could not find uv/uvx after installing. "
        "Please report this to your administrator.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
