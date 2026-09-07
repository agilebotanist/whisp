#!/bin/zsh
# Install the "Transcribe with Whisp" Finder Quick Action for the current user.
#
# Usage: automation/install-quick-action.sh
#
# Copies automation/Transcribe with Whisp.workflow into ~/Library/Services,
# wired up to call the shared serialized-transcribe helper (see lib.sh and
# whisp-transcribe.sh — it's what keeps concurrent triggers from piling up
# multiple whisp processes at once), then restarts Finder so it picks up
# the new Service immediately instead of waiting for the next login.

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
SRC="$SCRIPT_DIR/Transcribe with Whisp.workflow"
DEST="$HOME/Library/Services/Transcribe with Whisp.workflow"

source "$SCRIPT_DIR/lib.sh"

if [[ ! -d "$SRC" ]]; then
    echo "error: template not found at: $SRC" >&2
    exit 1
fi

WHISP_BIN_DIR="$(resolve_whisp_bin_dir)"
HELPER="$(install_whisp_transcribe_helper "$WHISP_BIN_DIR" "$SCRIPT_DIR")"

rm -rf "$DEST"
cp -R "$SRC" "$DEST"

# The template ships with a placeholder; substitute the installed helper's
# actual path so the Service's bare shell can find it.
sed -i '' "s#__WHISP_HELPER__#${HELPER}#g" "$DEST/Contents/Resources/document.wflow"

if ! plutil -lint "$DEST/Contents/Info.plist" >/dev/null; then
    echo "error: installed Info.plist failed validation" >&2
    exit 1
fi
if ! plutil -lint "$DEST/Contents/Resources/document.wflow" >/dev/null; then
    echo "error: installed document.wflow failed validation" >&2
    exit 1
fi

killall Finder >/dev/null 2>&1 || true

echo "Installed: $DEST"
echo "Using whisp at: $WHISP_BIN_DIR/whisp"
echo "Via helper: $HELPER"
echo
echo "Right-click any audio file (or folder) in Finder → Quick Actions → \"Transcribe with Whisp\"."
echo "If it doesn't appear immediately, log out and back in, or enable it under"
echo "System Settings → Keyboard → Keyboard Shortcuts → Services."
