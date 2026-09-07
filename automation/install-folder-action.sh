#!/bin/zsh
# Attach the Whisp Folder Action to a folder: any audio file added to it
# (drag, save, export) gets transcribed automatically, with a notification
# when done. No Terminal window, no click — this is the "zero-click" option
# in README.md's "Finder integration" section.
#
# Usage: automation/install-folder-action.sh <folder>
#
# Safe to re-run: recompiles the script and re-attaches idempotently. Safe
# to run for multiple folders — they all share one compiled script.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <folder>" >&2
    exit 1
fi

SCRIPT_DIR="${0:A:h}"
TEMPLATE="$SCRIPT_DIR/Auto-transcribe.applescript"
SCRIPT_NAME="Whisp Auto-transcribe.scpt"
SCRIPTS_DIR="$HOME/Library/Scripts/Folder Action Scripts"
COMPILED="$SCRIPTS_DIR/$SCRIPT_NAME"

source "$SCRIPT_DIR/lib.sh"

FOLDER="${1:A}"
if [[ ! -d "$FOLDER" ]]; then
    echo "error: not a directory: $FOLDER" >&2
    exit 1
fi
if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: template not found at: $TEMPLATE" >&2
    exit 1
fi

# Created up front, before the folder action is attached: its first-ever
# creation would itself count as a new item and re-trigger the handler.
mkdir -p "$FOLDER/Transcripts"

WHISP_BIN_DIR="$(resolve_whisp_bin_dir)"
HELPER="$(install_whisp_transcribe_helper "$WHISP_BIN_DIR" "$SCRIPT_DIR")"

mkdir -p "$SCRIPTS_DIR"
TMPDIR_BUILD="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_BUILD"' EXIT
SUBSTITUTED="$TMPDIR_BUILD/Auto-transcribe.applescript"
sed "s#__WHISP_HELPER__#${HELPER}#g" "$TEMPLATE" > "$SUBSTITUTED"
osacompile -o "$COMPILED" "$SUBSTITUTED"
echo "Compiled: $COMPILED"

osascript >/dev/null <<APPLESCRIPT
tell application "System Events"
    if not (folder actions enabled) then
        set folder actions enabled to true
    end if

    set targetPath to "$FOLDER"
    set scriptPosixPath to "$COMPILED"

    set fa to missing value
    repeat with fa1 in folder actions
        if (path of fa1 as text) is targetPath then
            set fa to fa1
            exit repeat
        end if
    end repeat
    if fa is missing value then
        set fa to make new folder action at end of folder actions with properties {path:targetPath}
    end if
    set enabled of fa to true

    set hasScript to false
    repeat with s1 in scripts of fa
        if (POSIX path of s1) is scriptPosixPath then
            set hasScript to true
        end if
    end repeat
    if not hasScript then
        tell fa to make new script with properties {path:(POSIX file scriptPosixPath)}
    end if
end tell
APPLESCRIPT

# Verify, rather than trust the AppleScript exited 0. Folder actions can't be
# looked up by a bare path string (System Events errors on that) — iterate,
# same as the attach step above.
ATTACHED="$(osascript <<APPLESCRIPT 2>&1 || true
tell application "System Events"
    set targetPath to "$FOLDER"
    repeat with fa1 in folder actions
        if (path of fa1 as text) is targetPath then
            return name of every script of fa1
        end if
    end repeat
    return "NOT-ATTACHED"
end tell
APPLESCRIPT
)"
if [[ "$ATTACHED" != *"$SCRIPT_NAME"* ]]; then
    echo "error: attachment did not verify. 'osascript' said: $ATTACHED" >&2
    exit 1
fi

echo "Attached \"$SCRIPT_NAME\" to: $FOLDER"
echo "Using whisp at: $WHISP_BIN_DIR/whisp"
echo "Via helper: $HELPER"
echo "Output goes to: $FOLDER/Transcripts"
echo
echo "Drop an audio file into that folder to test it — you'll get a notification when done."
echo "Only files added AFTER this point are picked up; anything already in the folder is left alone."
echo "If Folder Actions were previously disabled system-wide, they're now enabled."
