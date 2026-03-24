# Server

This connector's server code is published on PyPI as [`powerbi-analyst-mcp`](https://pypi.org/project/powerbi-analyst-mcp/).

The bundle does not ship the Python source — it instructs Claude Desktop to launch the server via `uvx`, which downloads and runs the latest published version from PyPI automatically.

**No manual installation required.** `uvx` is included with Python 3.11+ (via the `uv` tool).

If `uvx` is not available on a machine, install `uv` first:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```
