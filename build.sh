#!/usr/bin/env bash
set -euo pipefail

# 1) Locate script
SCRIPT="winrate.py"
if [ ! -f "$SCRIPT" ]; then
  echo "❌ Cannot find $SCRIPT in $(pwd)"
  exit 1
fi

# 2) Ensure PyInstaller is installed
if ! command -v pyinstaller &> /dev/null; then
  echo "📦 Installing PyInstaller…"
  pip install --user pyinstaller
fi

# 3) Build
echo "🏗  Building standalone executable…"
pyinstaller \
  --name Limbus_Auto_Bot \   # name of the exe
  --onefile \                # bundle into one file
  --noconsole \              # no console window (remove if you want logs)
  "$SCRIPT"

# 4) Done
echo
echo "✅  Build complete!"
echo "   → runnable at: dist/limbus_bot"
