#!/usr/bin/env python3
"""
Entry point for the Power BI Analyst MCP bundle.

Launches the server via uvx, which downloads and runs
powerbi-analyst-mcp from PyPI automatically.
"""
import os
import subprocess
import sys


if __name__ == "__main__":
    result = subprocess.run(["uvx", "powerbi-analyst-mcp"], env=os.environ)
    sys.exit(result.returncode)
