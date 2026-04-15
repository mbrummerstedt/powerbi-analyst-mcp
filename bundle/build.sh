#!/usr/bin/env bash
# Build dist/miinto-powerbi-analyst.mcpb from bundle/ config + live source.
# Always creates a fresh zip — no incremental updates, no stale pycache.
#
# Credentials (POWERBI_CLIENT_ID, POWERBI_TENANT_ID) are injected into the
# manifest at build time from the repo root .env file. The committed
# manifest.json uses "${POWERBI_CLIENT_ID}" / "${POWERBI_TENANT_ID}"
# placeholders so no secrets sit in the working tree.
#
# Prerequisites:
#   - bundle/manifest.json must exist and contain no placeholder values
#   - python3
#   - .env with POWERBI_CLIENT_ID and POWERBI_TENANT_ID
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$BUNDLE_DIR")"

if [[ ! -f "$BUNDLE_DIR/manifest.json" ]]; then
  echo "Error: bundle/manifest.json not found."
  echo "  cp bundle/manifest.template.json bundle/manifest.json"
  exit 1
fi

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "Error: .env not found at repo root."
  echo "  Create one with POWERBI_CLIENT_ID and POWERBI_TENANT_ID."
  exit 1
fi

# Load .env (export so python3 subprocess inherits)
set -a
# shellcheck disable=SC1091
source "$REPO_ROOT/.env"
set +a

: "${POWERBI_CLIENT_ID:?POWERBI_CLIENT_ID missing from .env}"
: "${POWERBI_TENANT_ID:?POWERBI_TENANT_ID missing from .env}"

if grep -q "FILL_IN_\|YOUR_AZURE" "$BUNDLE_DIR/manifest.json"; then
  echo "Error: manifest.json still contains placeholder values."
  exit 1
fi

python3 - <<EOF
import zipfile, pathlib, json, sys, re, os, tempfile

bundle = pathlib.Path("$BUNDLE_DIR")
repo   = pathlib.Path("$REPO_ROOT")

manifest = json.loads((bundle / "manifest.json").read_text())

# Inject credentials from environment into env block
env_block = manifest["server"]["mcp_config"].setdefault("env", {})
env_block["POWERBI_CLIENT_ID"] = os.environ["POWERBI_CLIENT_ID"]
env_block["POWERBI_TENANT_ID"] = os.environ["POWERBI_TENANT_ID"]

name     = manifest["name"]
out      = repo / "dist" / f"{name}.mcpb"
out.parent.mkdir(parents=True, exist_ok=True)

config_files = ["pyproject.toml", ".python-version"]
missing = [f for f in config_files if not (bundle / f).exists()]
if missing:
    sys.exit(f"Missing bundle/ files: {missing}")

# --- Validate manifest tools match registered tools in code ---
tools_py = (repo / "powerbi_mcp" / "tools.py").read_text()
code_tools = set(re.findall(r"@mcp\.tool\(\)\s+async def (\w+)", tools_py))
manifest_tools = {t["name"] for t in manifest.get("tools", [])}

missing_from_manifest = code_tools - manifest_tools
missing_from_code = manifest_tools - code_tools

if missing_from_manifest or missing_from_code:
    msgs = []
    if missing_from_manifest:
        msgs.append(f"Tools in code but NOT in manifest: {sorted(missing_from_manifest)}")
    if missing_from_code:
        msgs.append(f"Tools in manifest but NOT in code: {sorted(missing_from_code)}")
    sys.exit("ERROR: Manifest/code tool mismatch!\n  " + "\n  ".join(msgs))

print(f"Tool check OK: {len(code_tools)} tools in both code and manifest.")

# Write the injected manifest to a temp file and zip it (avoid mutating the source)
with tempfile.TemporaryDirectory() as tmp:
    injected = pathlib.Path(tmp) / "manifest.json"
    injected.write_text(json.dumps(manifest, indent=2))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(injected, "manifest.json")
        for f in config_files:
            z.write(bundle / f, f)
        for p in sorted((repo / "powerbi_mcp").rglob("*")):
            if "__pycache__" in p.parts or p.suffix == ".pyc":
                continue
            z.write(p, p.relative_to(repo))

names = zipfile.ZipFile(out).namelist()
print(f"Built {out} ({len(names)} files)")
for n in names:
    print(f"  {n}")
EOF
