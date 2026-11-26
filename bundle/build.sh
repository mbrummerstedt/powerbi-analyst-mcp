#!/usr/bin/env bash
# Build dist/miinto-powerbi-analyst.mcpb from bundle/ config + live source.
# Always creates a fresh zip — no incremental updates, no stale pycache.
#
# The internal archive includes organization IDs loaded from .env by uv.
# Copy bundle/manifest.template.json to bundle/manifest.json before building.
set -euo pipefail

BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$BUNDLE_DIR")"

if [[ ! -f "$REPO_ROOT/.env" ]]; then
  echo "Error: .env not found at repo root."
  echo "  Create one with POWERBI_CLIENT_ID and POWERBI_TENANT_ID."
  exit 1
fi

uv run --no-project --python "$(cat "$BUNDLE_DIR/.python-version")" --env-file "$REPO_ROOT/.env" python - "$BUNDLE_DIR" <<'PYTHON'
import zipfile, pathlib, json, sys, re, os, tempfile, tomllib

bundle = pathlib.Path(sys.argv[1])
repo = bundle.parent
manifest_path = bundle / "manifest.json"
if not manifest_path.exists():
    sys.exit("Copy bundle/manifest.template.json to bundle/manifest.json before building.")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
with (bundle / "pyproject.toml").open("rb") as project:
    manifest["version"] = tomllib.load(project)["project"]["version"]
for key in ("POWERBI_CLIENT_ID", "POWERBI_TENANT_ID"):
    if not os.environ.get(key):
        sys.exit(f"{key} missing from environment")

# Inject credentials from environment into env block
env_block = manifest["server"]["mcp_config"].setdefault("env", {})
env_block["POWERBI_CLIENT_ID"] = os.environ["POWERBI_CLIENT_ID"]
env_block["POWERBI_TENANT_ID"] = os.environ["POWERBI_TENANT_ID"]

name = manifest["name"]
if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
    sys.exit("Invalid bundle name")
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

# Publish the completed private archive atomically.
with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
    archive = pathlib.Path(tmp) / "bundle.mcpb"
    with archive.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, indent=2))
            for f in config_files:
                z.write(bundle / f, f)
            for p in sorted((repo / "powerbi_mcp").glob("*.py")):
                if p.is_symlink():
                    sys.exit(f"Refusing symlink in bundle: {p.name}")
                z.write(p, p.relative_to(repo))
            names = z.namelist()
    archive.chmod(0o600)
    archive.replace(out)

print(f"Built {out} ({len(names)} files)")
for n in names:
    print(f"  {n}")
PYTHON
