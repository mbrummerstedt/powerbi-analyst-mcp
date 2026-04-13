#!/usr/bin/env bash
# Build dist/miinto-powerbi-analyst.mcpb from bundle/ config + live source.
# Always creates a fresh zip — no incremental updates, no stale pycache.
#
# Prerequisites:
#   - bundle/manifest.json must exist and contain no placeholder values
#   - python3
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$BUNDLE_DIR")"

if [[ ! -f "$BUNDLE_DIR/manifest.json" ]]; then
  echo "Error: bundle/manifest.json not found."
  echo "  cp bundle/manifest.template.json bundle/manifest.json"
  echo "  # then fill in your org credentials"
  exit 1
fi

if grep -q "FILL_IN_\|YOUR_AZURE" "$BUNDLE_DIR/manifest.json"; then
  echo "Error: manifest.json still contains placeholder values."
  exit 1
fi

python3 - <<EOF
import zipfile, pathlib, json, sys, re

bundle = pathlib.Path("$BUNDLE_DIR")
repo   = pathlib.Path("$REPO_ROOT")

manifest = json.loads((bundle / "manifest.json").read_text())
name     = manifest["name"]
out      = repo / "dist" / f"{name}.mcpb"
out.parent.mkdir(parents=True, exist_ok=True)

config_files = ["manifest.json", "pyproject.toml", ".python-version"]
missing = [f for f in config_files if not (bundle / f).exists()]
if missing:
    sys.exit(f"Missing bundle/ files: {missing}")

# --- Validate manifest tools match registered tools in code ---
tools_py = (repo / "powerbi_mcp" / "tools.py").read_text()
# Find all @mcp.tool() decorated async functions
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

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
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
