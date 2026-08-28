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
```

**Options**:

| Flag | Description |
|---|---|
| `-l, --language <code>` | Force a language (e.g. `fr`, `en`). Omit to auto-detect per file. |
| `-m, --model <name>` | `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (default), or a full `org/repo` id on the Hugging Face Hub. |
| `-o, --output-dir <dir>` | Write outputs here instead of next to each source file. |
| `--srt` | Also generate `.srt` subtitle files. |
| `-q, --quiet` | Only print errors and the final summary. |
| `--version` | Print the installed version and exit. |

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

## Desktop shortcut (run Whisp on a fixed folder)

To transcribe a specific folder (e.g. your Voice Memos exports) by double-clicking an icon instead of opening a terminal:

1. Find whisp's full path once: `which whisp` (e.g. `/opt/homebrew/bin/whisp` for a pipx/Homebrew install, or `~/.venv/bin/whisp` for a venv install).
2. Create a file named `Transcribe.command` on your Desktop with:

   ```bash
   #!/bin/zsh
   WHISP="/opt/homebrew/bin/whisp"     # from `which whisp` above
   FOLDER="$HOME/Voice Memos"           # the folder to transcribe

   "$WHISP" "$FOLDER" --srt
   echo
   echo "Done. Press any key to close this window."
   read -r -k 1
   ```

3. Make it executable and double-clickable:

   ```bash
   chmod +x ~/Desktop/Transcribe.command
   ```

4. Double-click `Transcribe.command` in Finder. It opens Terminal, transcribes everything in `FOLDER`, and waits for a keypress before closing.

Optional touches:

- **Custom icon**: select the file in Finder → `Cmd+I` → drag an image onto the icon in the top-left of the Get Info panel.
- **One shortcut per folder**: duplicate the `.command` file and change `FOLDER` for each folder you transcribe regularly.
- **Drag-and-drop instead of a fixed folder**: an Automator "Quick Action" (Automator → New → Quick Action → *Run Shell Script*, with input set to "files or folders") lets you right-click any folder in Finder and run Whisp on it via `for f in "$@"; do "$WHISP" "$f" --srt; done`.

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
