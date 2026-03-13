# Contributing to Power BI Analyst MCP

## Project structure

```
powerbi-analyst-mcp/
├── pyproject.toml              # Package metadata and entry point
├── server.py                   # CLI wrapper: handles --login flag for terminal auth
├── requirements.txt            # Runtime dependencies (mirrors pyproject.toml)
├── requirements-dev.txt        # Test dependencies (pytest, respx)
├── pytest.ini                  # asyncio_mode = auto
├── .env.example                # Environment variable template
│
├── powerbi_mcp/
│   ├── __init__.py
│   ├── __main__.py             # Enables: python -m powerbi_mcp
│   ├── app.py                  # FastMCP instance, settings, main() entry point
│   ├── config.py               # Pydantic BaseSettings (POWERBI_CLIENT_ID, POWERBI_TENANT_ID, POWERBI_OUTPUT_DIR)
│   ├── auth.py                 # MSAL device code flow + OS-native secure token cache
│   ├── client.py               # Async httpx wrapper around the Power BI REST API
│   ├── models.py               # Pydantic response models (Workspace, Dataset, etc.)
│   ├── output.py               # CSV helpers: save_rows_to_csv, read_csv_page
│   ├── history.py              # JSONL query audit log: append, search, delete
│   └── tools.py                # All @mcp.tool() registrations
│
├── tests/
│   ├── conftest.py             # Shared fixtures and mock API payloads
│   ├── test_models.py          # Pydantic model validation unit tests
│   ├── test_client.py          # PowerBIClient tests with respx HTTP mocking
│   ├── test_output.py          # CSV save/read helper unit tests
│   ├── test_history.py         # Query audit log unit tests
│   ├── test_tools.py           # Full-stack MCP tool tests (mock HTTP + auth patch)
│   └── integration/
│       └── test_live_api.py    # Real API calls — auto-skipped if no cached token
│
└── .github/workflows/tests.yml # CI: runs mock test suite on every push / PR
```

## Set up a development environment

```bash
git clone https://github.com/mbrummerstedt/powerbi-analyst-mcp.git
cd powerbi-analyst-mcp

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
# or: pip install -r requirements.txt -r requirements-dev.txt
```

If you use [direnv](https://direnv.net/), the `.envrc` file activates the virtual environment automatically when you `cd` into the project.

## Environment variables

When running the server directly (outside of an MCP client), set variables via `.env`:

```bash
cp .env.example .env
```

```dotenv
POWERBI_CLIENT_ID=your-application-client-id-here
POWERBI_TENANT_ID=your-directory-tenant-id-here
# POWERBI_OUTPUT_DIR=powerbi_output   # optional
```

When running via an MCP client (Claude Desktop, Cursor, etc.) the variables are passed through the `env` block in the MCP config instead.

## Running the tests

**Mock tests** (no credentials needed — safe for CI):

```bash
pytest tests/ -v
```

**Integration tests** (requires a cached login token — run `python server.py --login` first):

```bash
pytest tests/integration/ -v
```

The integration tests call the real Power BI REST API and skip automatically if no token is cached.

## Architecture overview

```
powerbi_mcp/app.py
  └── Settings (pydantic-settings)   ← reads POWERBI_CLIENT_ID / POWERBI_TENANT_ID / POWERBI_OUTPUT_DIR
  └── FastMCP instance
  └── register_tools(mcp, client_id, tenant_id, output_dir)
        └── PowerBIAuth               ← MSAL PublicClientApplication + PersistedTokenCache
        └── @mcp.tool() functions
              └── PowerBIClient(token) ← httpx async client
                    └── Pydantic models (Workspace, Dataset, …)
              └── save_rows_to_csv / read_csv_page  ← output.py (large result handling)
              └── append_query_log / search_query_log  ← history.py (JSONL audit log)
```

**Key design decisions:**

- **No service principal.** Authentication uses the device code flow (delegated OAuth 2.0), so data access is always scoped to the signed-in user's own Power BI permissions.
- **OS-native token storage.** `msal-extensions` persists the token cache using the platform's secure store (Keychain / DPAPI / LibSecret) rather than a plain file.
- **Pydantic throughout.** Settings are validated at startup; all API responses are parsed into typed Pydantic models before being handled by tools.
- **Read-only by design.** The two OAuth scopes (`Dataset.Read.All`, `Workspace.Read.All`) and the tool set only allow reads.
- **Context-window-safe results.** `execute_dax` returns small results inline and automatically writes larger results to a named CSV, keeping the agent context lean regardless of query size.

## Adding a new tool

1. Add a method to `PowerBIClient` in `powerbi_mcp/client.py`.
2. If the response shape is new, add a Pydantic model in `powerbi_mcp/models.py`.
3. Register a `@mcp.tool()` function in `powerbi_mcp/tools.py` inside `register_tools`.
4. Add tests in `tests/test_tools.py` (mock) and optionally `tests/integration/test_live_api.py`.
