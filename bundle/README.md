# Claude Desktop Bundle (.mcpb)

A `.mcpb` file (MCP Bundle) is a ZIP archive that Claude Desktop installs via drag-and-drop. It is the recommended way to distribute this connector to colleagues — with credentials either pre-configured (org bundle) or prompted at install time (generic bundle).

The format was previously called `.dxt` (Desktop Extensions). The spec is maintained at [github.com/modelcontextprotocol/mcpb](https://github.com/modelcontextprotocol/mcpb).

---

## Two manifests — one committed, one not

| File | Committed | Purpose |
|---|---|---|
| `manifest.template.json` | Yes | Generic version — prompts the user for CLIENT_ID and TENANT_ID at install time via Claude's UI |
| `manifest.json` | **No** (git-ignored) | Org-specific version — credentials hardcoded, zero configuration for end users |

For internal distribution (e.g. Miinto), use `manifest.json`. For public distribution, use `manifest.template.json`.

---

## For maintainers — building the bundle

### 1. Prerequisites

Install the official `mcpb` CLI (recommended):

```bash
npm install -g @anthropic-ai/mcpb
```

Or use the manual `build.sh` script (requires `zip` and `python3`, no extra installs).

### 2. For an org-specific bundle (e.g. Miinto)

Copy the template and fill in your organisation's Azure AD credentials:

```bash
cd bundle/
cp manifest.template.json manifest.json
```

Edit `manifest.json`:
- Change `"name"` to something org-specific (e.g. `"miinto-powerbi-analyst"`)
- Change `"display_name"` accordingly
- Replace the two placeholder values in `"env"`:

```json
"POWERBI_CLIENT_ID": "FILL_IN_MIINTO_CLIENT_ID",   ← your Application (client) ID
"POWERBI_TENANT_ID": "FILL_IN_MIINTO_TENANT_ID"    ← your Directory (tenant) ID
```

Also remove the `"user_config"` block from `manifest.json` — it's only needed in the template.

`manifest.json` is git-ignored. The template (`manifest.template.json`) is committed and safe to share publicly.

### 3. Build

**With the mcpb CLI (recommended):**

```bash
cd bundle/
mcpb pack --manifest manifest.json --output ../dist/
```

**With the manual build script:**

```bash
cd bundle/
./build.sh
```

Output: `dist/<name>.mcpb` (e.g. `dist/miinto-powerbi-analyst.mcpb`)

`build.sh` will error if placeholder values are still present in `manifest.json`.

---

## For colleagues — installing the bundle

### Prerequisites

- [Claude Desktop](https://claude.ai/download) (macOS or Windows)
- Python 3.11+ with `uvx` available

  If `uvx` is not installed:

  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh

  # Windows (PowerShell)
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

### Install steps

1. Obtain the `.mcpb` file from your maintainer (e.g. `miinto-powerbi-analyst.mcpb`).
2. Open **Claude Desktop** → **Settings** (top-right menu) → **Developer**.
3. Drag and drop the `.mcpb` file onto the Developer settings window.
4. If using the generic template bundle, Claude will prompt you to enter your CLIENT_ID and TENANT_ID. For the org bundle, no configuration is needed.
5. Click **Enable** when prompted.
6. Start a new conversation and type: *authenticate with Power BI*
7. Claude will return a URL and a one-time code. Open the URL in your browser, enter the code, and sign in with your Microsoft account.

That's it. Authentication is cached in your OS keychain — you won't need to repeat this unless you explicitly log out.

---

## How the template vs org bundle differ

**Template (`manifest.template.json`) — for general/public use:**

Uses `user_config` to prompt users for their Azure credentials at install time:

```json
"user_config": {
  "client_id": { "type": "string", "title": "Azure Application (Client) ID", ... },
  "tenant_id": { "type": "string", "title": "Azure Directory (Tenant) ID", ... }
},
"env": {
  "POWERBI_CLIENT_ID": "${user_config.client_id}",
  "POWERBI_TENANT_ID": "${user_config.tenant_id}"
}
```

**Org manifest (`manifest.json`) — for internal distribution:**

Credentials hardcoded in `env`, no `user_config` block needed. Zero setup for end users.

```json
"env": {
  "POWERBI_CLIENT_ID": "actual-client-id",
  "POWERBI_TENANT_ID": "actual-tenant-id"
}
```

---

## File structure

```
bundle/
├── manifest.template.json   # Committed — generic, uses user_config for credentials
├── manifest.json            # Git-ignored — org-specific with hardcoded credentials
├── .gitignore               # Ignores manifest.json and *.mcpb
├── build.sh                 # Manual build script (alternative to mcpb CLI)
├── server/
│   └── README.md            # Notes that the server comes from PyPI via uvx
└── README.md                # This file
```

Built `.mcpb` files land in `dist/` (also git-ignored).

---

## Notes

- **No code is bundled.** The connector launches via `uvx powerbi-analyst-mcp`, which downloads and runs the latest published version from PyPI. The bundle is just the manifest.
- **Credentials are not secrets.** `POWERBI_CLIENT_ID` is a public Azure AD app registration identifier. `POWERBI_TENANT_ID` is your directory ID. Neither is sensitive. The actual credential is the OAuth token, which stays in each user's local OS keychain.
- **Per-user authentication.** Each colleague authenticates as themselves — queries run under their own Power BI permissions, preserving access control and audit trails.
- **Updates are automatic.** When a new version of `powerbi-analyst-mcp` is published to PyPI, `uvx` picks it up automatically on next launch. No need to redistribute the `.mcpb` file unless the manifest changes.
