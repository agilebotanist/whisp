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

# Files dropped into a watched folder can arrive via iCloud sync from
# another device (or another person sharing the folder) rather than being
# written locally, so the Folder Action can fire the instant the item's
# metadata appears -- before its bytes have actually downloaded. Wait for
# a real, materialized copy before hand it to whisp, rather than letting
# ffmpeg/mlx_whisper read a partial file.
#
# Checked/driven via NSURLUbiquitousItemDownloadingStatusKey and
# startDownloadingUbiquitousItemAtURLError (Foundation, bridged through
# JXA) -- NOT `brctl download`/`evict`, which no longer exist as CLI
# subcommands on this macOS version (verified directly, not assumed).
#
# IMPORTANT: startDownloadingUbiquitousItemAtURLError crashes (SIGSEGV) if
# called on a path that isn't inside an iCloud ubiquity container --
# verified directly. So it's only ever called after the status check
# below confirms the item actually is a not-yet-current ubiquitous item;
# a plain local file (e.g. the Quick Action run on a non-iCloud path)
# reports an empty status and is left alone entirely.
icloud_download_status() {
    osascript -l JavaScript - "$1" <<'JXA' 2>/dev/null
ObjC.import('Foundation');
function run(argv) {
    const url = $.NSURL.fileURLWithPath($.NSString.alloc.initWithUTF8String(argv[0]));
    const valueRef = Ref();
    const errorRef = Ref();
    if (!url.getResourceValueForKeyError(valueRef, $.NSURLUbiquitousItemDownloadingStatusKey, errorRef)) {
        return "";
    }
    const val = valueRef[0];
    return val ? val.js : "";
}
JXA
}

icloud_start_download() {
    osascript -l JavaScript - "$1" <<'JXA' >/dev/null 2>&1 || true
ObjC.import('Foundation');
function run(argv) {
    const url = $.NSURL.fileURLWithPath($.NSString.alloc.initWithUTF8String(argv[0]));
    $.NSFileManager.defaultManager.startDownloadingUbiquitousItemAtURLError(url, Ref());
}
JXA
}

wait_for_icloud_download() {
    local file="$1"
    local timeout_secs="${WHISP_ICLOUD_TIMEOUT:-1800}"
    local poll_interval=5
    local waited=0
    local dl_status
    dl_status="$(icloud_download_status "$file")"

    # Empty: not a ubiquitous item at all (plain local file, or path
    # vanished) -- nothing to wait for. Also covers the already-current case.
    if [[ -z "$dl_status" || "$dl_status" == "NSURLUbiquitousItemDownloadingStatusCurrent" ]]; then
        return 0
    fi

    echo "Waiting for iCloud download: $(basename "$file")" >&2
    icloud_start_download "$file"

    while [[ "$dl_status" != "NSURLUbiquitousItemDownloadingStatusCurrent" ]]; do
        if (( waited >= timeout_secs )); then
            echo "error: timed out after ${timeout_secs}s waiting for iCloud download: $file" >&2
            return 1
        fi
        sleep "$poll_interval"
        waited=$(( waited + poll_interval ))
        dl_status="$(icloud_download_status "$file")"
    done
}

if ! wait_for_icloud_download "$FILE"; then
    rm -f "$QUEUE_DIR/$$.txt"
    osascript -e 'display notification "iCloud download timed out" with title "Whisp"' >/dev/null 2>&1 || true
    exit 1
fi

# mkdir is atomic on a POSIX filesystem, so this is a safe cross-process
# mutex with no extra dependency (flock isn't shipped on macOS). Whoever's
# mkdir succeeds owns the lock; everyone else polls until it's free.
#
# The EXIT trap below is the normal release path, but it isn't the only
# one: a holder killed (not just exited normally) can leave the lock
# directory behind without the trap firing — observed for real, not
# hypothetical, when a wrapper process was killed while blocked waiting on
# its own whisp child. Without a backstop, every future run would then
# spin-wait on `mkdir` forever against a lock nobody will ever release. So
# the holder's pid is recorded inside the lock, and anyone failing to
# acquire it checks whether that pid is still alive; if not, the lock is
# stale and gets reclaimed rather than waited on indefinitely.
LOCK_PID_FILE="$LOCK_DIR/pid"
while ! mkdir "$LOCK_DIR" 2>/dev/null; do
    if [[ -f "$LOCK_PID_FILE" ]]; then
        holder_pid="$(cat "$LOCK_PID_FILE" 2>/dev/null || true)"
        if [[ -n "$holder_pid" ]] && ! kill -0 "$holder_pid" 2>/dev/null; then
            rm -rf "$LOCK_DIR"  # holder is dead; reclaim rather than wait forever
            continue
        fi
    fi
    sleep 2
done
echo $$ > "$LOCK_PID_FILE"
rm -f "$QUEUE_DIR/$$.txt"
trap 'rm -rf "$LOCK_DIR"' EXIT

whisp "$FILE" "$@"
