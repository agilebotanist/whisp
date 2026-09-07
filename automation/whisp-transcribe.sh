#!/bin/zsh
# Serialized wrapper around `whisp`, used by both the Quick Action and the
# Folder Action so concurrent triggers don't pile up.
#
# Installed to a stable location outside the repo (by install-quick-action.sh
# and install-folder-action.sh) because the Quick Action / Folder Action
# artifacts that call it are copied out of the repo — this needs to keep
# working after the repo checkout is gone.
#
# Why serialize at all: mlx_whisper loads its own copy of the model into GPU
# memory per process (no cross-process cache sharing). Two whisp processes
# running at once roughly doubles memory pressure and makes both slower by
# contending for the same GPU, rather than actually running in parallel.
# Concurrent triggers (two files dropped minutes apart, the first still
# processing) wait their turn here instead.
#
# Usage: whisp-transcribe.sh <file> [-- whisp-args...]

set -euo pipefail

export PATH="__WHISP_BIN_DIR__:$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <file> [-- whisp-args...]" >&2
    exit 1
fi

FILE="$1"
shift
if [[ "${1:-}" == "--" ]]; then
    shift
fi

STATE_DIR="$HOME/Library/Application Support/Whisp"
LOCK_DIR="$STATE_DIR/lock"
QUEUE_DIR="$STATE_DIR/queue"
mkdir -p "$STATE_DIR" "$QUEUE_DIR"

# While waiting on the lock, record what we're waiting to process — `whisp`
# with no arguments reads this directory to show queued (not yet started)
# jobs alongside actively running ones. Keyed by our own pid, same as the
# lock: if we're killed before acquiring it, whisp's dashboard treats a
# marker whose pid is no longer alive as stale and removes it.
echo "$FILE" > "$QUEUE_DIR/$$.txt"

# mkdir is atomic on a POSIX filesystem, so this is a safe cross-process
# mutex with no extra dependency (flock isn't shipped on macOS). Whoever's
# mkdir succeeds owns the lock; everyone else polls until it's free.
while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    sleep 2
done
rm -f "$QUEUE_DIR/$$.txt"
trap 'rmdir "$LOCK_DIR"' EXIT

whisp "$FILE" "$@"
