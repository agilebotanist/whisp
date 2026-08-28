# Design

How Whisp is built and why. See [REQUIREMENTS.md](REQUIREMENTS.md) for what it must do.

## 1. Overview

Whisp is a single-module CLI (`whisp.py`) with no internal package hierarchy. That's a deliberate choice, not a placeholder for future modularization: the tool has one job (file discovery → transcribe → write outputs), the whole thing is ~250 lines, and splitting it into a package would add import indirection without adding clarity. If the tool grows a second major responsibility (e.g. a GUI, a server mode), that's the trigger to split it — not before.

```
inputs (files / dirs / globs)
        │
        ▼
 iter_input_files()  ──►  deduplicated, sorted list[Path]
        │
        ▼
 resolve_model()     ──►  short name → mlx-community/... repo id
        │
        ▼
 load_backend()      ──►  platform check, then import mlx_whisper
        │
        ▼
 transcribe_file()  (per file, model reused across the loop)
        │
        ├──► mlx_whisper.transcribe()  ──►  {segments, language, text}
        │
        ├──► <name>_transcript_raw.txt   (always)
        └──► <name>.srt                  (if --srt)
```

## 2. Key decisions

### 2.1 Backend: MLX Whisper, not faster-whisper

The project previously used [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2), with `device="cpu"` on Mac — there is no Metal/GPU support in CTranslate2, so it never used the Mac's GPU at all despite comments in the old code calling that "optimized for Apple Silicon."

[MLX Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) runs on [MLX](https://github.com/ml-explore/mlx), Apple's own array framework, and executes on the Metal GPU / unified memory. It's Apple's answer to "the Mac-native way to run Whisper," which is what was asked for. Trade-off accepted: MLX only targets Apple Silicon, so this is a one-way door — there is no CPU/CUDA fallback path in this codebase. Given the target user is on Apple Silicon (per REQUIREMENTS §2), that trade-off is the right one; §6 of REQUIREMENTS.md records it as an explicit scope decision, not an oversight.

Alternatives considered:

| Option | Verdict |
|---|---|
| `faster-whisper` (previous) | CPU-only on Mac; rejected — doesn't use the GPU, contradicting the goal. |
| `whisper.cpp` + Core ML | Also Apple-accelerated, but C++ with a Python binding layer to maintain; MLX Whisper is pure Python and lower-friction to depend on. |
| `openai-whisper` (reference impl) | PyTorch-based; on Mac falls back to CPU or the slower/older MPS backend. Rejected for the same reason as faster-whisper. |

### 2.2 Model: `large-v3-turbo` by default

`large-v3-turbo` (released by OpenAI in 2024) prunes `large-v3`'s decoder layers, giving several-times-faster decoding for a small, generally imperceptible accuracy cost on non-adversarial audio. It's the better default for an interactive CLI tool; `large-v3` remains available via `--model large-v3` for cases where maximum accuracy matters more than turnaround time.

Model names are short (`tiny` … `large-v3-turbo`) and mapped internally to the corresponding `mlx-community/...` Hugging Face repo (`MODEL_REPOS` in `whisp.py`), rather than requiring users to know or type full repo ids. A `/` in `--model` is treated as "already a full repo id" and passed straight through — this is the escape hatch for quantized (`-q4`, `-8bit`) or fine-tuned MLX checkpoints without the CLI needing to special-case every variant.

### 2.3 One script, two former scripts

`transcmd.py` (single-file, hardcoded French, minimal CLI) was a strict subset of `transmulti.py`'s behavior (batch, language flag, model flag, SRT). Keeping both meant every feature added to one had to be remembered for the other. They're merged into one `whisp.py`; nothing in `transcmd.py` survives as separate behavior because none of it was behavior `transmulti.py` didn't already have.

### 2.4 Packaging: installable CLI via `pyproject.toml`

Whisp installs as a real `whisp` command on `PATH` (`pipx install .` or `pip install .`), rather than being invoked as `python whisp.py`. This is standard PEP 621 packaging: `[project.scripts]` declares the entry point, `setuptools` builds it. A flat `py-modules = ["whisp"]` layout is used instead of a `src/` package layout — there's exactly one module, so a package directory would be empty ceremony.

### 2.5 Dependency injection for testability

`transcribe_file()` and `main()` take the backend (the `mlx_whisper` module, or a fake with the same `.transcribe()` shape) as a parameter/injectable, rather than importing `mlx_whisper` at call time. This is the load-bearing decision behind NFR-6 (testable without a GPU): the unit tests substitute a `FakeMlxWhisper` that returns canned segments, so file discovery, output formatting, error handling, and exit-code logic are all verified on any machine, in milliseconds, with no model download.

The real import is isolated in `load_backend()`, which does two things in order: (1) a cheap `platform.machine() == "arm64"` check that fails fast with an actionable message (NFR-4) before touching any MLX/Torch import machinery; (2) the actual `import mlx_whisper`, wrapped to turn a bare `ImportError` into a message pointing at the README.

### 2.6 Output format: unchanged from the original scripts

Raw transcript = one non-empty segment per line, in order. SRT = standard numbered-cue format. This format was already correct and is preserved as-is; "polish" here means removing duplication and dead ends, not redesigning output the user already relies on.

### 2.7 Batch error handling

A single bad file (corrupt audio, unsupported codec inside a supported container, etc.) must not abort an entire folder's worth of transcription. `main()` catches per-file exceptions, reports them to stderr, and continues; the run's exit code is non-zero if *any* file failed, so scripts/CI calling `whisp` can still detect partial failure even though the batch didn't stop (FR-11, FR-13).

### 2.8 Determinism over exploration

`temperature=0.0` and `condition_on_previous_text=False` are fixed, not exposed as flags. They were deliberate choices in the original scripts (deterministic, "raw" as-spoken output rather than an LLM-smoothed transcript) and that intent is preserved rather than reopened as a configuration surface with no current requirement driving it.

## 3. Non-goals (see REQUIREMENTS §6 for the full list)

Two are worth calling out here because they were live design questions, not just omissions:

- **No CPU/CUDA fallback.** Considered and rejected (§2.1) — it would mean maintaining two backends and two dependency graphs for a tool whose target user (per REQUIREMENTS §2) is already on Apple Silicon.
- **No streaming/live transcription.** Whisp's contract is "point it at files"; a live-audio mode is a different tool with a different runtime shape (continuous capture, partial results, different error semantics), not an incremental addition.

## 4. Testing strategy

- **Unit tests** (`tests/test_whisp.py`) cover file discovery (single file, directory recursion, glob expansion, dedup, missing/unsupported paths), model name resolution (short names, alias, passthrough, invalid), SRT timestamp/formatting, and the full `transcribe_file`/`main` orchestration — all against `FakeMlxWhisper`, never the real backend.
- **Deliberately not unit tested**: real MLX inference correctness (that's MLX Whisper's own test surface, not Whisp's) and actual ffmpeg audio decoding (an integration concern, exercised manually per REQUIREMENTS §7's acceptance criteria).
- Tests run in any Python 3.10+ environment — CI can run them on non-Apple-Silicon runners, since `whisp.main()` never imports `mlx_whisper` for real once `load_backend` is monkeypatched.

## 5. Future considerations

Not committed to, but the design doesn't foreclose them:

- **Word-level timestamps**: `mlx_whisper.transcribe(word_timestamps=True)` is already supported upstream; would need a new output format (e.g. WebVTT with word cues) to be worth exposing.
- **Config file** for repeat settings (default model, default `--srt`, default `--output-dir`) if flag repetition becomes a real complaint — no evidence of that need yet.
- **Progress bar for long files**: currently only whole-file start/done messages; per-segment progress would need streaming from `mlx_whisper.transcribe`, which today returns only after the full file is processed.
