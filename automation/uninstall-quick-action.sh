#!/bin/zsh
# Remove the "Transcribe with Whisp" Finder Quick Action for the current user.
#
# Usage: automation/uninstall-quick-action.sh

set -euo pipefail

DEST="$HOME/Library/Services/Transcribe with Whisp.workflow"

if [[ ! -e "$DEST" ]]; then
    echo "Not installed: $DEST"
    exit 0
fi

rm -rf "$DEST"
killall Finder >/dev/null 2>&1 || true
echo "Removed: $DEST"
