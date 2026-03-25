#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launch strategy (in order):
  1. uvx powerbi-analyst-mcp   — preferred, clean isolated env
  2. pip install uv, then uvx  — bootstraps uv if missing, then uses it
"""
import subprocess
import sys
import os

PACKAGE = "powerbi-analyst-mcp"


def try_uvx():
    try:
        result = subprocess.run(["uvx", PACKAGE], env=os.environ)
        sys.exit(result.returncode)
    except FileNotFoundError:
        return False
    return True


def main():
    # Strategy 1: uvx already available
    if try_uvx():
        return

    # Strategy 2: install uv via pip, then retry
    # uv installs uvx into the same Scripts dir as pip (already on PATH)
    print("Installing uv (one-time setup)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv", "--quiet"],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"Failed to install uv: {e}", file=sys.stderr)
        sys.exit(1)

    # uv is now installed — it handles Python version selection internally
    # so even if this process is Python 3.9, uv will find Python 3.10+ for the tool
    try_uvx()
    print(
        "uvx still not found after installing uv. "
        "Try restarting Claude Desktop.",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    main()
