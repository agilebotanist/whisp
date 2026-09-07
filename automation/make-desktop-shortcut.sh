#!/bin/zsh
# Create a double-clickable Desktop shortcut that transcribes a fixed folder.
#
# Usage:
#   automation/make-desktop-shortcut.sh <folder> [shortcut-name] [-- whisp-args...]
#
# Examples:
#   automation/make-desktop-shortcut.sh ~/Voice\ Memos
#   automation/make-desktop-shortcut.sh ~/Voice\ Memos "Transcribe Voice Memos" -- --srt --verbose
#
# Defaults to `--srt` if no whisp-args are given. Opens a Terminal window
# with visible progress when double-clicked (unlike the Quick Action, which
# runs silently) — see README.md's "Finder integration" section for when to
# use which.

set -euo pipefail

SCRIPT_DIR="${0:A:h}"
TEMPLATE="$SCRIPT_DIR/Transcribe.command.template"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <folder> [shortcut-name] [-- whisp-args...]" >&2
    exit 1
fi

FOLDER="${1:A}"
shift

NAME="Transcribe"
if [[ $# -gt 0 && "$1" != "--" ]]; then
    NAME="$1"
    shift
fi
if [[ "${1:-}" == "--" ]]; then
    shift
fi

EXTRA_ARGS=("$@")
if [[ ${#EXTRA_ARGS[@]} -eq 0 ]]; then
    EXTRA_ARGS=(--srt)
fi

if [[ ! -d "$FOLDER" ]]; then
    echo "error: not a directory: $FOLDER" >&2
    exit 1
fi
if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: template not found at: $TEMPLATE" >&2
    exit 1
fi

WHISP_BIN="$(command -v whisp || true)"
if [[ -z "$WHISP_BIN" ]]; then
    echo "error: 'whisp' not found on PATH. Install it first (see README.md), then re-run this script." >&2
    exit 1
fi

DEST="$HOME/Desktop/${NAME}.command"

sed -e "s#__WHISP_BIN__#${WHISP_BIN}#g" \
    -e "s#__FOLDER__#${FOLDER}#g" \
    -e "s#__EXTRA_ARGS__#${EXTRA_ARGS[*]}#g" \
    "$TEMPLATE" > "$DEST"
chmod +x "$DEST"

echo "Created: $DEST"
echo "Double-click it in Finder to transcribe everything in: $FOLDER"
