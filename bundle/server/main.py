#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launch strategy (in order):
  1. uvx on PATH                — already installed system-wide
  2. pip install uv, then uvx  — bootstraps uv, calls it via full path
"""
import pathlib
import platform
import subprocess
import sys
import os

PACKAGE = "powerbi-analyst-mcp"


def _uvx_candidates():
    """Return candidate uvx paths: PATH first, then next to sys.executable."""
    import shutil
    found = shutil.which("uvx")
    if found:
        yield found

    python_dir = pathlib.Path(sys.executable).parent
    if platform.system() == "Windows":
        yield python_dir / "Scripts" / "uvx.exe"
        yield python_dir / "uvx.exe"
    else:
        yield python_dir / "uvx"
        yield python_dir.parent / "bin" / "uvx"


def _run_uvx():
    for candidate in _uvx_candidates():
        if pathlib.Path(candidate).exists():
            result = subprocess.run([str(candidate), PACKAGE], env=os.environ)
            sys.exit(result.returncode)
    return False


def main():
    # Strategy 1: uvx already available
    _run_uvx()

    # Strategy 2: install uv via pip, then call uvx by full path
    print("Installing uv (one-time setup)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv", "--quiet"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install uv: {e}", file=sys.stderr)
        sys.exit(1)

    # Call uvx by full path — don't rely on PATH being updated
    _run_uvx()

    print(
        "Could not find uvx after installing uv. "
        "Please report this to your administrator.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
