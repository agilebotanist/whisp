# Whisp

A fast, Apple Silicon–native command-line tool for transcribing audio into raw, as-spoken text — with optional SRT subtitles.

Whisp runs [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper), Apple's Metal-accelerated port of OpenAI's Whisper model built on their [MLX](https://github.com/ml-explore/mlx) framework. It uses the Mac's GPU/Neural Engine directly, so it's significantly faster on M-series chips than CPU-only Whisper implementations.

## Features

- **One command, any input**: individual files, folders (searched recursively), or glob patterns, mixed freely in a single run
- **Apple Silicon–native**: runs on the GPU via MLX/Metal instead of falling back to the CPU
- **Latest model by default**: `large-v3-turbo` — near large-v3 accuracy, several times faster
- **Language auto-detection**, or force a language (e.g. French) for slightly better accuracy on known content
- **Two output formats**: a raw as-spoken `.txt` transcript, and optional `.srt` subtitles
- **Batch-friendly**: continues past per-file errors, prints a summary, exits non-zero if anything failed

## Requirements

- **Apple Silicon Mac** (M1 or later). MLX requires the Metal GPU — there is no Intel Mac or CUDA fallback.
- **macOS 13.5+**
- **Python 3.10+**
- **[Homebrew](https://brew.sh)** (recommended, for installing `ffmpeg` and optionally Python)

## Installation (macOS)

Whisp installs as a real `whisp` command on your `PATH` — no `python whisp.py` needed.

### 1. Install prerequisites

```bash
# ffmpeg is required to decode audio files
brew install ffmpeg

# Python 3.10+ (skip if you already have one, e.g. via pyenv)
brew install python@3.12
```

### 2. Install Whisp

The recommended way is [pipx](https://pipx.pypa.io), which installs the `whisp` command in an isolated environment without touching your system Python:

```bash
brew install pipx
pipx ensurepath

git clone https://github.com/agilebotanist/whisp.git
cd whisp
pipx install .
```

Alternatively, with plain `pip` in a virtual environment:

```bash
git clone https://github.com/agilebotanist/whisp.git
cd whisp
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

### 3. Verify

```bash
whisp --version
whisp --help
```

The first transcription downloads the selected model from Hugging Face and caches it under `~/.cache/huggingface/`. Subsequent runs use the cached copy.

## Usage

```bash
whisp <inputs...> [options]
```

**Examples**:

```bash
# Single file
whisp recording.m4a

# Multiple files
whisp file1.m4a file2.wav file3.mp3

# An entire folder, searched recursively
whisp ~/Voice\ Memos

# Glob patterns
whisp "*.m4a" "archive/**/*.wav"

# Also write .srt subtitles
whisp lecture.m4a --srt

# Force French instead of auto-detecting
whisp meeting.m4a --language fr

# Use a smaller/faster model
whisp quick-note.m4a --model small

# Send outputs to a specific folder instead of next to the source files
whisp ~/Voice\ Memos --output-dir ~/Transcripts

# No files: show whatever's currently running (see "Checking progress" below)
whisp
```

**Options**:

| Flag | Description |
|---|---|
| `-l, --language <code>` | Force a language (e.g. `fr`, `en`). Omit to auto-detect per file. |
| `-m, --model <name>` | `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (default), or a full `org/repo` id on the Hugging Face Hub. |
| `-o, --output-dir <dir>` | Write outputs here instead of next to each source file. |
| `--srt` | Also generate `.srt` subtitle files. |
| `-q, --quiet` | Only print errors and the final summary. |
| `-v, --verbose` | Print a live position/percent line while transcribing, so long files show they're progressing. |
| `--version` | Print the installed version and exit. |

## Checking progress

Three ways to see what a running (or queued) transcription is doing, without interrupting it:

- **`whisp` with no arguments** shows every currently running or queued job, machine-wide — across every terminal, the Quick Action, and the Folder Action alike:

  ```text
  $ whisp
  1 job(s) running:

    Sorbonne 2.m4a
      [██████████████░░░░░░] 68.4%   32:10 elapsed   model=large-v3-turbo

  Run `whisp <files...>` to transcribe. `whisp --help` for all options.
  ```

- **`--verbose`** prints a live `position / total (percent%)` line in the terminal you launched it from.
- **A per-file progress log**, `<name>_progress.log`, is written next to each file's eventual output for the duration of that file's transcription (removed once it's done) — `tail -f` it from another terminal to watch it update in real time:

  ```bash
  tail -f "Sorbonne 2_progress.log"
  ```

  This is the one to reach for when you kicked something off through the Quick Action or Folder Action (both run with `--quiet`, no Terminal window) and want to check on it after the fact.

All three read from the same underlying progress tracking, so they always agree. The percentage is real — computed from the actual audio position mlx_whisper has reached (via its own internal progress counter), not a time-based guess — so accuracy doesn't depend on knowing this machine's throughput in advance.

Note: the first transcription of any given model downloads it first — there's no progress signal during that one-time download, only once decoding actually starts.

**Outputs** (written next to each source file, or into `--output-dir`):

- `<name>_transcript_raw.txt` — plain text, one segment per line
- `<name>.srt` — SRT subtitles (only with `--srt`)

## Supported audio formats

`.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.wma`, `.mkv`, `.mp4`, `.mov`

## Model selection guide

| Model | Relative speed | Accuracy | Use case |
|---|---|---|---|
| `tiny` | Fastest | Low | Quick drafts, testing |
| `base` | Very fast | Fair | Simple audio, speed priority |
| `small` | Fast | Good | Balanced performance |
| `medium` | Moderate | Very good | High quality, reasonable speed |
| `large-v3` | Slower | Best | Maximum accuracy |
| `large-v3-turbo` | Fast | Near-`large-v3` | **Default** — best speed/accuracy trade-off |

## Finder integration

Three ways to run Whisp without opening a terminal each time, from most to least "just point and click." Installers for all three are in [automation/](automation/) — see [automation/README.md](automation/README.md) for the full reference; the essentials are below.

The Quick Action and Folder Action share a locking helper: if you trigger a second transcription while the first is still running (e.g. dropping two files a few minutes apart), it queues instead of running alongside the first — two `whisp` processes at once would each load their own copy of the model into GPU memory and slow each other down.

### Right-click "Transcribe with Whisp" (Quick Action)

Select one or more audio files (or a folder) in Finder, right-click → **Quick Actions → Transcribe with Whisp**. It runs `whisp <selection> --srt --quiet` on whatever you selected and pops a macOS notification when it starts and again when it's done — no Terminal window opens.

```bash
automation/install-quick-action.sh     # installs into ~/Library/Services
automation/uninstall-quick-action.sh   # removes it
```

**Toggling visibility**: System Settings → Keyboard → Keyboard Shortcuts → Services (or Extensions → Finder), find "Transcribe with Whisp".

<details>
<summary>Recreate it by hand instead (Automator GUI)</summary>

This version calls `whisp` directly, so it skips the queuing behavior described above — two triggered at once really will run concurrently. Run `automation/install-quick-action.sh` instead if you want that.

1. Open **Automator** → **File → New** → choose **Quick Action** → **Choose**.
2. At the top, set **"Workflow receives current"** to **files or folders**, in **Finder**.
3. Search the actions library for **Run Shell Script**, drag it into the workflow.
4. Set **Shell** to `/bin/zsh` and **Pass input** to **as arguments**.
5. Paste this into the script box (adjust the `PATH` line if `whisp` lives somewhere other than these two locations — check with `which whisp`):

   ```bash
   export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
   osascript -e 'display notification "Starting…" with title "Whisp"' >/dev/null 2>&1
   ok=0
   fail=0
   for f in "$@"; do
     if whisp "$f" --srt --quiet; then
       ok=$((ok+1))
     else
       fail=$((fail+1))
     fi
   done
   osascript -e "display notification \"$ok done, $fail failed\" with title \"Whisp\"" >/dev/null 2>&1
   ```

6. **File → Save**, name it `Transcribe with Whisp`.

</details>

### Folder Action (fully automatic — zero clicks)

Watches a chosen folder and transcribes anything *added to it after this point* — existing files are left alone. Output goes to a `Transcripts` subfolder (not the watched folder itself — writing output back into the watched folder would count as a new item and re-trigger the action on itself).

```bash
automation/install-folder-action.sh ~/Voice\ Memos     # attach to a folder
automation/uninstall-folder-action.sh ~/Voice\ Memos   # detach
```

<details>
<summary>Recreate it by hand instead (Automator GUI)</summary>

This version calls `whisp` directly, so it skips the queuing behavior described above. Run `automation/install-folder-action.sh` instead if you want that.

1. **Automator → File → New** → **Folder Action** → **Choose**.
2. Next to **"Folder Action receives files and folders added to"**, pick the folder to watch.
3. Add **Run Shell Script**, shell `/bin/zsh`, input **as arguments**, and use a script like the Quick Action's above, but add `--output-dir "$1:h"/Transcripts` (or a fixed path) so output doesn't land back in the watched folder.
4. **File → Save**, name it e.g. `Auto-transcribe Voice Memos`.
5. Confirm it's active: right-click the watched folder → **Services → Folder Actions Setup…** → make sure **Enable Folder Actions** and the action's own checkbox are both checked.

</details>

### Desktop shortcut (double-click to transcribe one fixed folder)

A `.command` file you double-click, which opens a Terminal window, runs, and shows progress — good when you want to *see* it work rather than get a silent notification. Unlike the Folder Action, it re-transcribes the whole folder on every run, not just what's new.

```bash
automation/make-desktop-shortcut.sh ~/Voice\ Memos
# or, with a custom name and flags:
automation/make-desktop-shortcut.sh ~/Voice\ Memos "Transcribe Voice Memos" -- --srt --verbose
```

Optional touches:

- **Custom icon**: select the file in Finder → `Cmd+I` → drag an image onto the icon in the top-left of the Get Info panel.
- **One shortcut per folder**: run `make-desktop-shortcut.sh` again with a different folder and name.

## Configuration tips

### Mixed-language content

Omit `--language` to auto-detect per segment — recommended for recordings that switch languages.

### Single-language content

Forcing the language (e.g. `--language fr`) gives slightly better accuracy and skips detection overhead.

### Large batches / limited time

Use `--model small` or `--model medium` to trade some accuracy for speed.

## Output format

### Raw transcript (`.txt`)

Each segment on its own line, preserving the as-spoken flow:

```
Bonjour, bienvenue à cette présentation.
Aujourd'hui nous allons parler de l'intelligence artificielle.
C'est un sujet très important dans le monde moderne.
```

### SRT subtitles

```
1
00:00:00,000 --> 00:00:03,500
Bonjour, bienvenue à cette présentation.

2
00:00:03,500 --> 00:00:07,000
Aujourd'hui nous allons parler de l'intelligence artificielle.
```

## Troubleshooting

**How do I know it's actually working, on a long file with no output?**
See [Checking progress](#checking-progress) above — run `whisp` with no arguments from any terminal, or `tail -f` the `_progress.log` file next to where the output will land. The very first transcription of a given model also downloads it first — there's no progress signal during that one-time download, only once decoding actually starts.

**`--quiet` still prints some download/progress noise**
`--quiet` suppresses whisp's own messages, but mlx_whisper's internal model-download and decoding progress bars write directly to the terminal and aren't currently suppressed by it — a known cosmetic gap. Harmless, and irrelevant when running through the Quick Action or Folder Action (no Terminal window either way).

**`whisp requires an Apple Silicon Mac`**
MLX only runs on Apple Silicon (M1+). There is no supported CPU/Intel/CUDA fallback for this tool.

**`ffmpeg: command not found` / audio fails to decode**
Install ffmpeg: `brew install ffmpeg`.

**Model download fails or is slow**
Downloads come from the Hugging Face Hub. If you're behind a proxy or mirror, set `HF_ENDPOINT` before running:
```bash
export HF_ENDPOINT=https://huggingface.co
whisp recording.m4a
```

**Out of memory / system feels sluggish on a large batch**
Switch to a smaller model: `whisp *.m4a --model medium` (or `small`).

## Further reading

- [REQUIREMENTS.md](REQUIREMENTS.md) — functional and non-functional requirements
- [DESIGN.md](DESIGN.md) — architecture and design decisions
- [CLAUDE.md](CLAUDE.md) — install/usage reference for AI coding agents working in this repo

## License

Apache License 2.0 — see [LICENSE](LICENSE).

## Acknowledgments

- Built with [MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) and [MLX](https://github.com/ml-explore/mlx) by Apple
- Based on OpenAI's [Whisper](https://github.com/openai/whisper) speech recognition model
- Converted MLX model weights hosted by the [mlx-community](https://huggingface.co/mlx-community) on Hugging Face

## Contributing

Contributions are welcome — feel free to open an issue or pull request.
