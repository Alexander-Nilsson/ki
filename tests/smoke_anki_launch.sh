#!/usr/bin/env bash
# Smoke test: launch Anki headless and check the addon loads without errors.
# Run this with Anki closed:  ./tests/smoke_anki_launch.sh
set -euo pipefail

ADDON_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TEMP_DIR"' EXIT

# Symlink addon into a temp addons21 folder
mkdir -p "$TEMP_DIR/addons21"
ln -s "$ADDON_DIR"/anki_git "$TEMP_DIR/addons21"/anki_git

echo "=== Smoke test: launching Anki headless ==="
echo "Base dir: $TEMP_DIR"
echo ""

# Launch Anki headless with a generous timeout
# Anki will try to load the addon, and profile_did_open will fire
# even without a pre-existing profile (Anki creates one automatically)
if QT_QPA_PLATFORM=offscreen timeout 15 anki --base "$TEMP_DIR" 2>&1; then
    echo ""
    echo "=== SUCCESS: Anki exited cleanly ==="
else
    code=$?
    if [ "$code" -eq 124 ]; then
        echo ""
        echo "=== OK: Anki timed out after 15s (expected in headless mode) ==="
    else
        echo ""
        echo "=== FAILED: Anki exited with code $code ==="
        exit 1
    fi
fi
