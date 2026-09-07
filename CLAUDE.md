# CLAUDE.md

Guidance for Claude Code (or any coding agent) working in this repository.

## What this is

Whisp is a single-file, Apple Silicon–native CLI tool (`whisp.py`) that transcribes audio into raw text and optional SRT subtitles, using MLX Whisper. Full behavior spec: [REQUIREMENTS.md](REQUIREMENTS.md). Architecture and rationale: [DESIGN.md](DESIGN.md). User-facing docs: [README.md](README.md).

## Repository layout

```
whisp.py             # the entire CLI — file discovery, model resolution, transcription, argparse
pyproject.toml       # PEP 621 packaging; entry point: whisp = "whisp:main"
tests/test_whisp.py  # unit tests (no GPU/model/network required — backend is injected)
automation/          # Finder Quick Action, Folder Action, desktop shortcut installers (shell out to whisp; see automation/README.md)
README.md            # install + usage (human-facing)
REQUIREMENTS.md      # functional / non-functional requirements
DESIGN.md            # architecture + decisions
```

There is intentionally no `src/` package — one module, one file. Don't split it into a package unless the tool grows a second major responsibility (see DESIGN.md §1).

`automation/` is not Python and has no test suite — its `.workflow`/`.scpt` formats are undocumented-by-Apple and were reverse-engineered from real system examples, then verified by actually installing and running them (see DESIGN.md §2.9 before touching them). Don't hand-edit the XML/AppleScript there from memory; re-verify against a real example on disk the way DESIGN.md §2.9 describes, and re-run the relevant `automation/install-*.sh` end to end rather than assuming a change is correct.

## Installation and usage (macOS, Apple Silicon)

This tool **requires an Apple Silicon Mac** (M1+, macOS 13.5+). It has no CPU/Intel/CUDA fallback — that's a deliberate scope decision (DESIGN.md §2.1), not a bug to fix.

```bash
# Prerequisites
brew install ffmpeg
brew install python@3.12   # if you don't already have Python 3.10+

# Install the CLI (from a checkout of this repo)
brew install pipx && pipx ensurepath
pipx install .
# or: python3 -m venv .venv && source .venv/bin/activate && pip install .

# Verify
whisp --version
whisp --help
```

Usage:

```bash
whisp recording.m4a                       # -> recording_transcript_raw.txt
whisp ~/Voice\ Memos --srt                # folder, recursive, + .srt files
whisp "*.m4a" "archive/**/*.wav"          # glob patterns
whisp meeting.m4a --language fr           # force language
whisp note.m4a --model small              # smaller/faster model
```

Full flag reference and troubleshooting: see [README.md](README.md).

## Development workflow

```bash
# Editable install with dev dependencies
pip install -e ".[dev]"

# Run the test suite
pytest
```

- Tests never require a real model, network access, or Apple Silicon: `transcribe_file()` and `main()` take the transcription backend as an injectable, and tests substitute a `FakeMlxWhisper` (see `tests/test_whisp.py`). Keep that seam intact when editing — don't call `mlx_whisper.transcribe` directly from anywhere except `load_backend()`'s caller chain.
- If you touch CLI flags, update all three: `whisp.py` (`build_parser`), `README.md` (options table), `REQUIREMENTS.md` (FR list) — they're expected to stay in sync.
- If you touch the MLX Whisper API surface (`mlx_whisper.transcribe(...)` kwargs), verify against the actual installed version — its signature has changed across releases; don't assume the kwargs documented here are stable forever.

## Conventions

- Python 3.10+ syntax is assumed (`X | Y` unions, `list[...]`/`dict[...]` generics) — no `typing.List`/`Optional` imports.
- No inline comments explaining *what* code does; only *why*, where it's non-obvious (see existing comments in `whisp.py` for the bar to meet).
- Exit codes matter: `main()` returns non-zero on any per-file failure or bad input, even though the batch keeps running past individual failures (REQUIREMENTS FR-11/FR-13). Preserve this if refactoring the main loop.
- Determinism (`temperature=0.0`, `condition_on_previous_text=False`) is intentional, not a placeholder — see DESIGN.md §2.8 before changing it or exposing it as a flag.

## What not to do here

- Don't add a faster-whisper / CPU / CUDA fallback path "for portability" — it was deliberately removed (DESIGN.md §2.1); if requirements change, that's a REQUIREMENTS.md edit first, not a silent code change.
- Don't reintroduce `transcmd.py` / `transmulti.py` as separate scripts — they were merged into `whisp.py` because one was a strict subset of the other (DESIGN.md §2.3).
- Don't fabricate or guess Hugging Face repo ids for models — verify against `https://huggingface.co/mlx-community` before adding to `MODEL_REPOS` in `whisp.py`.
