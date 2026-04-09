#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build.sh — Creates a .mcpb bundle from the contents of this directory.
#
# Usage:
#   cd bundle/
#   ./build.sh
#
# Output: ../dist/<name>.mcpb
#
# Prerequisites:
#   - manifest.json must exist (copy manifest.template.json and fill in values)
#   - python3 (to read the name from manifest.json)
#   - zip
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# --- Validate manifest.json ---
if [[ ! -f manifest.json ]]; then
  echo "Error: manifest.json not found."
  echo ""
  echo "  cp manifest.template.json manifest.json"
  echo "  # then edit manifest.json — set your client_id, tenant_id, etc."
  echo ""
  exit 1
fi

if grep -q "FILL_IN_\|YOUR_AZURE" manifest.json; then
  echo "Error: manifest.json still contains placeholder values."
  exit 1
fi

# --- Read bundle name ---
BUNDLE_NAME=$(python3 -c "import json; print(json.load(open('manifest.json'))['name'])")
OUTPUT_DIR="$SCRIPT_DIR/../dist"
OUTPUT="$OUTPUT_DIR/${BUNDLE_NAME}.mcpb"

mkdir -p "$OUTPUT_DIR"

# --- Build .mcpb (ZIP archive) ---
TMP_ZIP=$(mktemp /tmp/mcpb_XXXXXX).zip

zip -j "$TMP_ZIP" manifest.json pyproject.toml   # root-level files
zip -r "$TMP_ZIP" powerbi_mcp/                    # package directory
[[ -f icon.png ]]  && zip -j "$TMP_ZIP" icon.png

mv "$TMP_ZIP" "$OUTPUT"

echo ""
echo "Bundle created: $OUTPUT"
echo ""
echo "To install:"
echo "  1. Open Claude Desktop → Settings → Developer"
echo "  2. Drag and drop $OUTPUT onto the window"
echo ""
