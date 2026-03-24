#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# build.sh — Creates a .mcpb bundle from the contents of this directory.
#
# Prefer the official CLI if available:
#   npm install -g @anthropic-ai/mcpb
#   mcpb pack --manifest manifest.json --output ../dist/
#
# This script is a fallback that requires only zip + python3.
#
# Usage:
#   cd bundle/
#   ./build.sh
#
# Output: ../dist/<name>.mcpb (e.g. dist/miinto-powerbi-analyst.mcpb)
#
# Prerequisites:
#   - manifest.json must exist (copy manifest.template.json and fill in values)
#   - python3 (to read the name from manifest.json)
#   - zip
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check manifest.json exists
if [[ ! -f manifest.json ]]; then
  echo "Error: manifest.json not found."
  echo ""
  echo "  cp manifest.template.json manifest.json"
  echo "  # then edit manifest.json and set POWERBI_CLIENT_ID and POWERBI_TENANT_ID"
  echo ""
  exit 1
fi

# Check that placeholder values have been replaced
if grep -q "FILL_IN_\|YOUR_AZURE" manifest.json; then
  echo "Error: manifest.json still contains placeholder values."
  echo "Edit manifest.json and replace FILL_IN_MIINTO_CLIENT_ID and FILL_IN_MIINTO_TENANT_ID."
  exit 1
fi

# Read the bundle name from manifest.json
BUNDLE_NAME=$(python3 -c "import json; print(json.load(open('manifest.json'))['name'])")
OUTPUT_DIR="$SCRIPT_DIR/../dist"
OUTPUT="$OUTPUT_DIR/${BUNDLE_NAME}.mcpb"

mkdir -p "$OUTPUT_DIR"

# Build the zip/mcpb — include manifest and server/, skip build artifacts
TMP_ZIP=$(mktemp /tmp/mcpb_XXXXXX).zip
zip -j "$TMP_ZIP" manifest.json                         # manifest at root
zip -r "$TMP_ZIP" server/                               # server/ directory
[[ -f icon.png ]]   && zip -j "$TMP_ZIP" icon.png
[[ -f README.md ]]  && zip -j "$TMP_ZIP" README.md

mv "$TMP_ZIP" "$OUTPUT"

echo ""
echo "Bundle created: $OUTPUT"
echo ""
echo "To install:"
echo "  1. Open Claude Desktop → Settings → Developer"
echo "  2. Drag and drop $OUTPUT onto the window"
echo "  OR"
echo "  3. Share $OUTPUT with colleagues — they drag and drop it the same way"
echo ""
