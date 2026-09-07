# Requirements

This document specifies what Whisp must do, the constraints it operates under, and what is explicitly out of scope. See [DESIGN.md](DESIGN.md) for how these requirements are met.

## 1. Purpose

Whisp is a command-line tool that turns local audio files into raw, as-spoken text transcripts (and optionally SRT subtitles), using the Mac's own GPU for speed.

## 2. Target environment

| Constraint | Value |
|---|---|
| Operating system | macOS 13.5 or later |
| Hardware | Apple Silicon (M1 or later) — required, not optional |
| Python | 3.10 or later |
| External tools | `ffmpeg` on `PATH` (audio decoding) |
| Network | Required once per model, to download it from the Hugging Face Hub; not required afterward (cached locally) |

Intel Macs, Linux, and Windows are explicitly out of scope (see [§6](#6-out-of-scope)).

## 3. Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | The tool is invoked as `whisp <inputs...> [options]` from any directory once installed. |
| FR-2 | `<inputs>` accepts, in any combination: individual audio file paths, directory paths (searched recursively), and shell glob patterns (e.g. `*.m4a`, `**/*.wav`). |
| FR-3 | Only files with a supported extension are transcribed; unsupported files are reported and skipped, not treated as errors. |
| FR-4 | The same file is never transcribed twice in one run, even if matched by multiple inputs (e.g. an explicit path and a glob that also matches it). |
| FR-5 | The tool auto-detects the spoken language by default. A `--language <code>` flag forces a specific language for all files in the run. |
| FR-6 | The tool selects the Whisper model via `--model`, accepting the short names `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo`, or any explicit `org/repo` id for advanced use. |
| FR-7 | The default model is `small`. |
| FR-8 | For each transcribed file, the tool writes a `<name>_transcript_raw.txt` file: one line per transcribed segment, in order, with empty segments omitted. |
| FR-9 | When `--srt` is passed, the tool additionally writes a `<name>.srt` file with sequential subtitle numbering and `HH:MM:SS,mmm` timestamps, per the SRT format. |
| FR-10 | Output files are written next to each source file by default, or into a single directory when `--output-dir` is given. |
| FR-11 | If a file in a batch fails to transcribe, the tool reports the error for that file and continues with the remaining files rather than aborting the run. |
| FR-12 | After processing, the tool prints a summary: number succeeded, number failed, total processed. |
| FR-13 | The process exit code is `0` only if every file in the run succeeded, and non-zero if the run found no files, was given a bad argument, or any file failed. |
| FR-14 | `--quiet` suppresses per-file progress output, printing only errors and the final summary. |
| FR-15 | `--version` prints the installed version and exits; `--help` prints usage and exits. |
| FR-16 | `--verbose` prints a live position/percent line while a file is transcribing. |
| FR-17 | Invoking the tool with zero file arguments shows every whisp job currently running or queued (across all terminals and the Finder automations), each with model, elapsed time, and percent complete where determinable — instead of an error. |
| FR-18 | While transcribing, a `<name>_progress.log` file is maintained next to where that file's output will land, with a timestamped line per progress update; removed once that file's transcription finishes (success or failure). |
| FR-19 | Percent-complete, wherever shown (dashboard, `--verbose`, the progress log), is computed from the audio decoder's actual position, not estimated from elapsed time and an assumed throughput. |

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | **Performance**: transcription runs on the Apple Silicon GPU/Neural Engine (via MLX/Metal), not the CPU, so batches complete faster than a CPU-bound implementation at equivalent model size. |
| NFR-2 | **Efficiency**: the model is loaded once per run and reused across all files in a batch, not reloaded per file. |
| NFR-3 | **Installability**: a single command (`pipx install .` or `pip install .`) makes `whisp` available on `PATH` as a normal shell command — no `python <script>.py` invocation required. |
| NFR-4 | **Portability of intent, not platform**: the tool fails fast with a clear, actionable message when run on unsupported hardware (non-Apple-Silicon), rather than crashing deep in a dependency with an opaque error. |
| NFR-5 | **Determinism**: given the same file, model, and language, repeated runs produce the same transcript (temperature fixed at `0.0`, no conditioning on prior context). |
| NFR-6 | **Testability**: core logic (file discovery, model resolution, SRT formatting, transcription orchestration) is unit-testable without requiring a real model, a GPU, or network access. |
| NFR-7 | **Maintainability**: a single, dependency-injected transcription entry point, so the ML backend can be swapped or mocked without touching CLI or file-handling logic. |

## 5. Supported audio formats

`.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.wma`, `.mkv`, `.mp4`, `.mov`

## 6. Out of scope

- **Non-Apple-Silicon platforms** (Intel Mac, Linux, Windows, CUDA GPUs). MLX is Apple Silicon–only; there is intentionally no fallback backend to maintain.
- **Real-time / streaming transcription.** Whisp processes complete audio files, not live audio input.
- **Speaker diarization** ("who said what").
- **Translation** (Whisper's translate-to-English mode is not exposed).
- **A GUI.** The `automation/` installers (Finder Quick Action, Folder Action, desktop shortcut — see [automation/README.md](automation/README.md)) wrap the CLI for convenience; they are not a graphical application, and none of their logic lives in `whisp.py` itself (DESIGN.md §2.9).
- **Editing or post-processing transcripts** (punctuation correction, summarization, etc.).

## 7. Acceptance criteria

- Running `pipx install .` (or `pip install .`) from a clean checkout on an Apple Silicon Mac with `ffmpeg` installed produces a working `whisp` command on `PATH`.
- `whisp <file>` produces a `<name>_transcript_raw.txt` next to the source file.
- `whisp <file> --srt` additionally produces a valid `<name>.srt`.
- `whisp <folder>` transcribes every supported file found recursively under `<folder>`.
- `whisp <bad-path>` exits non-zero with a clear message and does not throw an unhandled exception.
- The full unit test suite (`pytest`) passes without requiring network access, a GPU, or Apple Silicon.
