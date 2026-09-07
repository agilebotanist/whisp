#!/bin/zsh
# Detach the Whisp Folder Action from a folder (installed via
# install-folder-action.sh). Leaves the compiled script in
# ~/Library/Scripts/Folder Action Scripts/ in place, since it may still be
# attached to other folders.
#
# Usage: automation/uninstall-folder-action.sh <folder>

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <folder>" >&2
    exit 1
fi

FOLDER="${1:A}"
FOLDER_NAME="${FOLDER:t}"

# Folder actions are keyed by name (== the folder's basename, per Apple's
# own Folder Actions Suite definition) — referencing one by a raw path
# string, as opposed to by this name, reliably errors ("Can't get folder
# action <path>"), so look it up by name and then double check its path
# actually matches before deleting, in case two differently-located folders
# happen to share a basename.
osascript <<APPLESCRIPT
tell application "System Events"
    try
        set fa to folder action "$FOLDER_NAME"
    on error
        return "NOT-INSTALLED"
    end try
    if (path of fa as text) is "$FOLDER" then
        delete fa
        return "DELETED"
    else
        return "NAME-COLLISION: \"$FOLDER_NAME\" is attached to " & (path of fa as text) & ", not $FOLDER — leaving it alone"
    end if
end tell
APPLESCRIPT

# Verify, rather than trust osascript's exit code alone.
STILL_THERE="$(osascript -e "tell application \"System Events\" to try
    return path of (folder action \"$FOLDER_NAME\") as text
end try" 2>&1 || true)"
if [[ "$STILL_THERE" == "$FOLDER" ]]; then
    echo "error: still attached after attempting removal." >&2
    exit 1
fi

echo "Detached Whisp folder action from: $FOLDER"
echo "(the compiled script itself is left in ~/Library/Scripts/Folder Action Scripts/,"
echo " in case it's still attached to other folders)"
