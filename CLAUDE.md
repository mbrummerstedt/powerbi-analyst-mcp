# Power BI Analyst MCP Server

## Architecture

- `powerbi_mcp/` — the MCP server package (auth, client, tools, models, output, history)
- `bundle/` — mcpb bundle config (manifest.json, pyproject.toml, build.sh)
- `dist/` — built `.mcpb` bundle output
- `tests/` — pytest suite (unit + integration)

## Bundle Rules

**Every tool registered in `powerbi_mcp/tools.py` must also be listed in `bundle/manifest.json` `tools` array.**
The build script (`bundle/build.sh`) enforces this — it will fail if they're out of sync.

When adding or removing a tool:
1. Add/remove the `@mcp.tool()` function in `tools.py`
2. Add/remove the entry in `bundle/manifest.json` `tools` array
3. Run `bash bundle/build.sh` — it validates the match before building

## Version Bumping

Version lives in two places — keep them in sync:
- `bundle/manifest.json` → `"version": "X.Y.Z"`
- `bundle/pyproject.toml` → `version = "X.Y.Z"`

## Building the Bundle

```bash
bash bundle/build.sh
```

Output: `dist/miinto-powerbi-analyst.mcpb`

## Security — Bundle and Manifest Contain Secrets

`bundle/manifest.json` and `dist/*.mcpb` contain baked-in org credentials
(`POWERBI_CLIENT_ID`, `POWERBI_TENANT_ID`). Both are in `.gitignore` for this reason.

**NEVER:**
- `git add -f bundle/manifest.json` or `git add -f dist/`
- Attach the `.mcpb` file to a GitHub release
- Publish the bundle anywhere public

The bundle is for **internal distribution only** — share it directly with users, not via public URLs or release assets.

## Running Tests

```bash
.venv/bin/python -m pytest tests/ -x -q
```

Integration tests (tagged `integration`) require a live Power BI token and are skipped by default.

## Dataset Discovery

The preferred discovery flow for app-managed orgs is `list_apps` → `list_datasets`, not `list_workspaces`.
`list_workspaces` is a fallback for when no apps are installed.
