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

### 2.9 Finder integration lives outside the CLI, not inside it

The right-click Quick Action, Folder Action, and desktop `.command` shortcut (`automation/`, see [automation/README.md](automation/README.md)) are all thin wrappers that shell out to the installed `whisp` command — none of them are implemented as CLI flags or Python code in `whisp.py`. That's deliberate: they're macOS shell-integration concerns (Automator `.workflow` bundles, Finder Services registration, Folder Actions/`System Events`), orthogonal to what the CLI itself does, and none of it needs to be testable the way `whisp.py`'s logic does — REQUIREMENTS §6 excludes a GUI from scope, and these are OS-level conveniences around the CLI, not a GUI for it. Each installer resolves `whisp`'s actual location at install time and hardcodes it into the generated artifact, rather than relying on `PATH` at run time — Services and Folder Actions both run in a bare shell that never sources `.zshrc`, so a plain `whisp` command name alone wouldn't resolve.

The `.workflow`/`.scpt` formats were reverse-engineered from real Apple-shipped examples on disk (`/System/Library/Services/Encode Selected Audio Files.workflow` for the Quick Action's XML schema, `/System/Library/PrivateFrameworks/FolderActionsKit.framework`'s `.sdef` for the Folder Action's AppleScript vocabulary), and every install/uninstall path was exercised end-to-end on real hardware — not just written and assumed correct. Two bugs only surfaced that way and are worth remembering if this code is touched again: (1) `System Events` errors ("Can't get folder action ...") when a folder action is referenced by a raw path string instead of by name, and again when deleting an element while still iterating the live collection that contains it — look up the name first in a read-only pass, then delete by name as a separate step; (2) the Folder Action's own output must not be written back into the folder it watches, or the output files themselves count as newly added items and re-trigger it — hence `--output-dir <watched>/Transcripts`, with that subfolder pre-created at install time so even its first creation can't trigger the handler.

Both the Quick Action and Folder Action call `whisp` through a shared serialized wrapper (`automation/whisp-transcribe.sh`, installed to `~/Library/Application Support/Whisp/`) rather than calling it directly, because Finder-driven triggers are inherently concurrent in a way the CLI's own batch loop isn't: two Quick Action invocations, or two Folder Action drops minutes apart with the first still running, are two separate OS-level trigger events with no shared process to serialize them naturally the way `main()`'s `for audio in files` loop does for one CLI invocation. Without a lock, each trigger spawns its own `whisp` process, and each independently loads a full copy of the model into GPU memory (`mlx_whisper`'s `ModelHolder` cache is a process-level class attribute — it doesn't help across processes), so concurrent triggers would contend for the same GPU and slow each other down rather than genuinely running in parallel. The wrapper uses an atomic `mkdir`-based mutex rather than `flock` — macOS doesn't ship `flock(1)` — and later arrivals wait rather than being dropped or erroring. This only applies to the two Finder-triggered paths; the desktop shortcut is a single foreground process per double-click, so there's nothing concurrent to serialize against.

### 2.10 Progress tracking: a background thread polling mlx_whisper's own tqdm bar

`mlx_whisper.transcribe()` is one big blocking call — it returns only once the entire file is done, with no callback or generator interface for incremental results. That's a real problem for a tool whose files can run 30+ minutes: there's no built-in way to show it's making progress, or to know how far along it is. Three things (the `whisp` no-args dashboard, `--verbose`'s live line, and the per-file `_progress.log`) all need the same underlying data, so there's exactly one mechanism producing it, not three.

**How it works**: `mlx_whisper.transcribe()` internally shows a `tqdm` progress bar over mel-spectrogram frames — but only when its `verbose` parameter is `False` specifically (not `None`, not `True`; its own source computes `disable=verbose is not False`). `transcribe_file()` always calls it with `verbose=False` internally now, regardless of the CLI's own `--verbose` flag, and runs that call on a background `threading.Thread` so the main thread stays free. From the main thread, `frame_progress()` polls `tqdm.tqdm._instances` (tqdm's own process-wide registry of live bar instances — documented, intentional, not a private-API hack) roughly once a second, filtering for `unit == "frames"` to specifically find *this* bar rather than huggingface_hub's unrelated download-progress bars, which also use tqdm and are live at the same time during a first-ever model download. `.n / .total` on that instance is the real fraction of the file processed — not a time-based estimate — which is what FR-19 requires and why `frame_progress()` is worth the extra complexity over just guessing from elapsed time (REQUIREMENTS' NFR-1 already establishes throughput isn't constant or predictable across machines — a real incident in this project: a 117-minute file took nowhere near what casual benchmarks would suggest on the machine this was built on, which is exactly the scenario a time-based estimate would get visibly wrong).

This was verified directly before being built into `whisp.py` at all: a standalone script ran a real (short) transcription in a background thread while the main thread polled `tqdm.tqdm._instances`, confirming genuine incrementing values (`(0, 14915)` → `(2616, 14915)` → … → `(13080, 14915)`) were observable externally, with silent audio (which Whisper fast-forwards through via its no-speech-probability skip, per its `should_skip` check in the decode loop) confirmed as a bad test signal since it produces almost no observable intermediate progress — real speech audio is needed to validate this kind of change.

**Where the data goes**: `write_status()` publishes each poll to `~/Library/Application Support/Whisp/status/<pid>.json` (`STATUS_DIR`), overwritten in place as the current file progresses and as a `whisp` process moves from file to file within one batch; removed only once by `main()`'s `finally` block when the whole batch ends, not per-file — so the dashboard reflects "this process is busy" continuously across a multi-file run, not blank in the gap between files. `read_status_files()` (what `whisp` with no args calls) treats a status file whose `pid` is no longer alive as stale and deletes it opportunistically — covers a crashed or `kill -9`'d process leaving a file behind, which the `finally` block can't run for. `automation/whisp-transcribe.sh` uses the same liveness-based staleness convention for its own `queue/<pid>.txt` markers (written while spin-waiting on the automation lock, read by `read_queue_files()`), so a killed queued job doesn't linger in the dashboard forever either.

Both `STATUS_DIR` and `QUEUE_DIR` are plain module-level globals (not constructor/function parameters) specifically so tests can `monkeypatch.setattr` them — see the `isolated_state_dirs` autouse fixture in `tests/test_whisp.py`. Without it, running the test suite would read and write the real path on whatever machine runs it, including potentially colliding with a genuinely running job — this was caught and fixed before it shipped, not after.

**The per-file log** (`<name>_progress.log`, next to where that file's output will land) is deliberately separate from the JSON status file rather than derived from it: it's meant to be `tail -f`'d directly by a human who already knows which file they're waiting on and doesn't want to think about dashboards or PIDs, especially after kicking something off through the Quick Action or Folder Action, where there's no Terminal window to have shown anything in the first place. Like the status file, it's ephemeral — opened fresh per file, removed in a `finally` block on both success and failure — because its job is live visibility during the run, not a permanent record (the real, permanent record is the transcript output itself, or the `❌ Error on <file>: ...` line `main()` already prints to stderr on failure).

**Known limitation**: `verbose=False` is what makes `frame_progress()` work, but it also means mlx_whisper's own tqdm bar (and huggingface_hub's model-download bars, and its own `print("Detected language: ...")`) render for real, directly to stdout/stderr — and none of that is currently suppressed by whisp's own `--quiet`, which only ever governed whisp's *own* print statements. In practice this only matters for interactive terminal use with `--quiet` set (the Quick Action and Folder Action have no attached terminal for it to reach); fixing it properly would mean redirecting the real stdout/stderr file descriptors around the background thread's execution, which is process-wide, not thread-local — risky to do without also swallowing the main thread's own `--verbose` output if both flags are ever set together. Deliberately left alone rather than risking that interaction; documented in README's troubleshooting instead.

## 3. Non-goals (see REQUIREMENTS §6 for the full list)

Two are worth calling out here because they were live design questions, not just omissions:

- **No CPU/CUDA fallback.** Considered and rejected (§2.1) — it would mean maintaining two backends and two dependency graphs for a tool whose target user (per REQUIREMENTS §2) is already on Apple Silicon.
- **No streaming/live transcription.** Whisp's contract is "point it at files"; a live-audio mode is a different tool with a different runtime shape (continuous capture, partial results, different error semantics), not an incremental addition.

## 4. Testing strategy

- **Unit tests** (`tests/test_whisp.py`) cover file discovery (single file, directory recursion, glob expansion, dedup, missing/unsupported paths), model name resolution (short names, alias, passthrough, invalid), SRT timestamp/formatting, status/queue file read-write-cleanup, dashboard rendering, and the full `transcribe_file`/`main` orchestration — all against `FakeMlxWhisper`, never the real backend.
- An **autouse fixture** (`isolated_state_dirs`) monkeypatches `STATUS_DIR`/`QUEUE_DIR` to a per-test `tmp_path` for every test, not just the ones that look like they need it — `transcribe_file()` writes status unconditionally now, so without this every test run would touch the real machine-wide state directory.
- **Deliberately not unit tested**: real MLX inference correctness (that's MLX Whisper's own test surface, not Whisp's), actual ffmpeg audio decoding, and genuine `tqdm._instances` progress observation (an integration concern — validated once, manually, with real speech audio before §2.10's mechanism was built, per REQUIREMENTS §7's acceptance criteria; a fake backend can't exercise real tqdm bars).
- Tests run in any Python 3.10+ environment — CI can run them on non-Apple-Silicon runners, since `whisp.main()` never imports `mlx_whisper` for real once `load_backend` is monkeypatched, and a bare `whisp` (dashboard) never calls `load_backend()` at all.

## 5. Future considerations

Not committed to, but the design doesn't foreclose them:

- **Word-level timestamps**: `mlx_whisper.transcribe(word_timestamps=True)` is already supported upstream; would need a new output format (e.g. WebVTT with word cues) to be worth exposing.
- **Config file** for repeat settings (default model, default `--srt`, default `--output-dir`) if flag repetition becomes a real complaint — no evidence of that need yet.
- **Suppressing mlx_whisper's own stdout/stderr noise under `--quiet`** — see §2.10's known limitation; needs process-wide fd redirection done carefully enough not to also swallow `--verbose` output when both flags are set.
- **A `--skip-existing` flag** (skip a file if its `_transcript_raw.txt` already exists and is newer than the source) — would help the desktop shortcut and repeated batch runs on a growing folder avoid redoing work; raised in conversation but not yet a firm requirement.
