# Shared helpers for whisp's automation installers. Sourced, not executed.

# Prints the directory containing the installed `whisp` command, or exits
# with an error message if it's not on PATH.
resolve_whisp_bin_dir() {
    local bin
    bin="$(command -v whisp || true)"
    if [[ -z "$bin" ]]; then
        echo "error: 'whisp' not found on PATH. Install it first (see README.md), then re-run this script." >&2
        exit 1
    fi
    dirname "$bin"
}

# Installs (or updates) the shared serialized-transcribe helper at a stable
# location outside the repo — the Quick Action / Folder Action artifacts
# that call it are copied out of the repo and need it to keep existing.
# Prints the installed path.
install_whisp_transcribe_helper() {
    local whisp_bin_dir="$1"
    local automation_dir="$2"
    local dest_dir="$HOME/Library/Application Support/Whisp"
    local dest="$dest_dir/whisp-transcribe.sh"

    mkdir -p "$dest_dir"
    sed "s#__WHISP_BIN_DIR__#${whisp_bin_dir}#g" "$automation_dir/whisp-transcribe.sh" > "$dest"
    chmod +x "$dest"
    echo "$dest"
}
