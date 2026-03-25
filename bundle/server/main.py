#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launch strategy (in order):
  1. uvx powerbi-analyst-mcp        — clean isolated env, preferred
  2. py -3.x server/main.py         — re-launch under Python 3.10+ (Windows only, when python = 3.9)
  3. pip install + direct import    — fallback when uv is not installed
"""
import subprocess
import sys
import os

MIN_PYTHON = (3, 10)
PACKAGE = "powerbi-analyst-mcp"
MODULE = "powerbi_mcp.app"


def _relaunch_with_newer_python():
    """On Windows, try the py launcher to find Python 3.10+."""
    for version in ("3.13", "3.12", "3.11", "3.10"):
        try:
            result = subprocess.run(
                ["py", f"-{version}", __file__] + sys.argv[1:],
                env=os.environ,
            )
            sys.exit(result.returncode)
        except FileNotFoundError:
            continue
    print(
        f"Error: Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required "
        f"but was not found. Install Python 3.12 from https://python.org",
        file=sys.stderr,
    )
    sys.exit(1)


def main():
    # Check Python version — on Windows, 'python' may resolve to 3.9
    if sys.version_info < MIN_PYTHON:
        _relaunch_with_newer_python()

    # Strategy 1: uvx (preferred — clean isolated environment)
    try:
        result = subprocess.run(["uvx", PACKAGE], env=os.environ)
        sys.exit(result.returncode)
    except FileNotFoundError:
        pass

    # Strategy 2: pip install into current env, then import directly
    print(
        f"uv not found — installing {PACKAGE} via pip (one-time setup)...",
        file=sys.stderr,
    )
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", PACKAGE, "--quiet"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"pip install failed: {e}", file=sys.stderr)
        sys.exit(1)

    from powerbi_mcp.app import main as server_main
    server_main()


if __name__ == "__main__":
    main()
