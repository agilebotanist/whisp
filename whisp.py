#!/usr/bin/env python3
"""
whisp — transcribe audio into raw, as-spoken text (and optional SRT subtitles).

Powered by MLX Whisper, Apple's Metal-accelerated Whisper implementation for
Apple Silicon. Accepts individual files, folders, and glob patterns, and
processes them as a single batch.

Examples:
    whisp recording.m4a
    whisp file1.m4a file2.wav file3.mp3
    whisp ./recordings --srt
    whisp "*.m4a" "archive/**/*.wav" --model medium
    whisp meeting.m4a --language fr
    whisp                              # no files: show currently running jobs
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import platform
import subprocess
import sys
import threading
import time
from collections.abc import Iterable
from pathlib import Path

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("whisp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".mkv", ".mp4", ".mov"}

# Where running whisp processes publish status for `whisp` (no args) to read.
# Module-level so tests can monkeypatch it rather than touching real state.
STATE_DIR = Path.home() / "Library" / "Application Support" / "Whisp"
STATUS_DIR = STATE_DIR / "status"
QUEUE_DIR = STATE_DIR / "queue"

# --model accepts these short names, or any full "org/repo" on the Hugging
# Face Hub for advanced use (e.g. a quantized or fine-tuned MLX checkpoint).
MODEL_REPOS: dict[str, str] = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "turbo": "mlx-community/whisper-large-v3-turbo",  # alias
}
DEFAULT_MODEL = "small"


def iter_input_files(inputs: list[str]) -> Iterable[Path]:
    """Expand files, folders, and glob patterns into unique audio file paths."""
    seen: set[Path] = set()

    def emit(p: Path) -> Iterable[Path]:
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS and p not in seen:
            seen.add(p)
            yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS and f not in seen:
                    seen.add(f)
                    yield f

    for raw in inputs:
        if any(ch in raw for ch in "*?[]"):
            matches = sorted(glob.glob(raw, recursive=True))
            if not matches:
                print(f"warning: no matches for pattern: {raw}", file=sys.stderr)
            for match in matches:
                yield from emit(Path(match))
            continue

        p = Path(raw)
        if not p.exists():
            print(f"warning: skipping {raw} (not found)", file=sys.stderr)
            continue
        found = list(emit(p))
        if not found and p.is_file():
            print(f"warning: skipping {raw} (unsupported extension)", file=sys.stderr)
        yield from found


def resolve_model(name: str) -> str:
    """Map a short model name to its MLX Hugging Face repo id."""
    if name in MODEL_REPOS:
        return MODEL_REPOS[name]
    if "/" in name:
        return name  # explicit Hugging Face repo id or local checkpoint path
    valid = ", ".join(sorted(set(MODEL_REPOS) - {"turbo"}))
    sys.exit(f"Unknown model '{name}'. Choose one of: {valid} (or pass a full org/repo id).")


def srt_timestamp(seconds: float) -> str:
    """Format seconds as an SRT timestamp: HH:MM:SS,mmm."""
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments: list[dict], out_path: Path) -> None:
    """Write transcription segments to an SRT subtitle file."""
    with out_path.open("w", encoding="utf-8") as srt:
        index = 0
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            index += 1
            start = srt_timestamp(seg["start"])
            end = srt_timestamp(seg["end"])
            srt.write(f"{index}\n{start} --> {end}\n{text}\n\n")


def probe_duration(audio_path: Path) -> float | None:
    """Total audio duration in seconds via ffprobe, or None if it can't be determined."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def frame_progress() -> tuple[int, int] | None:
    """(frames_done, frames_total) from mlx_whisper's internal tqdm bar, if active."""
    try:
        import tqdm
    except ImportError:
        return None
    for inst in list(tqdm.tqdm._instances):
        if getattr(inst, "unit", None) == "frames" and inst.total:
            return inst.n, inst.total
    return None


def format_hms(seconds: float) -> str:
    """Format a duration in seconds as H:MM:SS, or M:SS under an hour."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pid_alive(pid: int) -> bool:
    """Whether a process with this pid currently exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, just owned by someone else
    return True


def write_status(pid: int, **fields) -> None:
    """Write (or overwrite) this pid's status file. Best-effort: never raises."""
    try:
        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        path = STATUS_DIR / f"{pid}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"pid": pid, **fields}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def remove_status(pid: int) -> None:
    try:
        (STATUS_DIR / f"{pid}.json").unlink(missing_ok=True)
    except OSError:
        pass


def read_status_files() -> list[dict]:
    """Status of every currently-alive whisp job, cleaning up stale entries as found."""
    if not STATUS_DIR.is_dir():
        return []
    jobs = []
    for path in sorted(STATUS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = data.get("pid")
        if not isinstance(pid, int) or not pid_alive(pid):
            path.unlink(missing_ok=True)  # left behind by a crashed/killed process
            continue
        jobs.append(data)
    return jobs


def read_queue_files() -> list[dict]:
    """Files waiting on the automation lock (see automation/whisp-transcribe.sh)."""
    if not QUEUE_DIR.is_dir():
        return []
    queued = []
    for path in sorted(QUEUE_DIR.glob("*.txt")):
        pid_text = path.stem
        if not pid_text.isdigit() or not pid_alive(int(pid_text)):
            path.unlink(missing_ok=True)
            continue
        try:
            queued.append({"pid": int(pid_text), "file": path.read_text(encoding="utf-8").strip()})
        except OSError:
            continue
    return queued


def progress_bar(percent: float, width: int = 20) -> str:
    filled = max(0, min(width, round(percent / 100 * width)))
    return "█" * filled + "░" * (width - filled)


def print_dashboard() -> None:
    """Show currently running/queued whisp jobs — what `whisp` with no args prints."""
    jobs = read_status_files()
    queued = read_queue_files()

    if not jobs and not queued:
        print("No whisp jobs currently running.")
    else:
        if jobs:
            print(f"{len(jobs)} job(s) running:\n")
            for job in jobs:
                name = Path(job.get("file", "?")).name
                model = job.get("model", "?")
                percent = job.get("percent")
                started_at = job.get("started_at")
                elapsed = format_hms(time.time() - started_at) if started_at else "?"
                if percent is not None:
                    bar = progress_bar(percent)
                    pct_label = f"{percent:5.1f}%"
                else:
                    bar = "?" * 20
                    pct_label = "  ?.?%"
                print(f"  {name}\n    [{bar}] {pct_label}   {elapsed} elapsed   model={model}")
        if queued:
            if jobs:
                print()
            print(f"{len(queued)} job(s) queued:\n")
            for job in queued:
                print(f"  {Path(job['file']).name}")

    print("\nRun `whisp <files...>` to transcribe. `whisp --help` for all options.")


def load_backend():
    """Import mlx_whisper, failing with a clear message if the platform can't run it."""
    if sys.platform != "darwin" or platform.machine() != "arm64":
        sys.exit(
            "whisp requires an Apple Silicon Mac (arm64/macOS): it relies on MLX, "
            "Apple's Metal-accelerated ML framework.\n"
            f"Detected platform: {sys.platform}/{platform.machine()}"
        )
    try:
        import mlx_whisper
    except ImportError as exc:
        sys.exit(
            f"mlx-whisper is not installed ({exc}).\n"
            "Install it with: pip install mlx-whisper\n"
            "See README.md for full setup instructions."
        )
    return mlx_whisper


def transcribe_file(
    mlx_whisper,
    audio_path: Path,
    model_name: str,
    model_repo: str,
    language: str | None,
    write_srt_file: bool,
    output_dir: Path | None,
    quiet: bool,
    verbose: bool = False,
) -> None:
    """Transcribe one audio file, writing a raw .txt transcript and optional .srt."""
    dest_dir = output_dir or audio_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_txt = dest_dir / f"{audio_path.stem}_transcript_raw.txt"
    out_srt = dest_dir / f"{audio_path.stem}.srt"

    if not quiet:
        lang_label = language or "auto"
        print(f"\N{SPEAKER WITH THREE SOUND WAVES} {audio_path.name} (model={model_name}, language={lang_label}) …")

    pid = os.getpid()
    duration = probe_duration(audio_path)
    started_at = time.time()
    write_status(pid, file=str(audio_path), model=model_name, duration=duration,
                 position=0.0, percent=0.0, started_at=started_at)

    # A plain-text, tail -f-able progress log next to the eventual output —
    # separate from the JSON status file (which feeds `whisp` with no args):
    # this one is per-file, colocated with its output, and useful even when
    # you're not thinking to run the dashboard. Removed once the file is
    # done; it's a progress indicator, not a permanent artifact.
    log_path = dest_dir / f"{audio_path.stem}_progress.log"
    log_file = log_path.open("w", encoding="utf-8")
    dur_label_full = format_hms(duration) if duration else "unknown"
    log_file.write(f"[{time.strftime('%H:%M:%S')}] Starting {audio_path.name} "
                    f"(model={model_name}, duration={dur_label_full})\n")
    log_file.flush()

    outcome: dict = {}

    def _run() -> None:
        try:
            # verbose=False (not None/True) is what enables mlx_whisper's own
            # internal tqdm progress bar, which is what makes frame_progress()
            # able to observe live position — see DESIGN.md §2.9's follow-up.
            outcome["result"] = mlx_whisper.transcribe(
                str(audio_path),
                path_or_hf_repo=model_repo,
                language=language,
                temperature=0.0,
                condition_on_previous_text=False,
                word_timestamps=False,
                verbose=False,
            )
        except Exception as exc:  # re-raised on the calling thread, below
            outcome["error"] = exc

    try:
        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        while worker.is_alive():
            progress = frame_progress()
            if progress:
                n, total = progress
                percent = n / total * 100
                position = percent / 100 * duration if duration else None
                write_status(pid, file=str(audio_path), model=model_name, duration=duration,
                             position=position, percent=percent, started_at=started_at)
                pos_label = format_hms(position) if position is not None else "?"
                dur_label = format_hms(duration) if duration else "?"
                progress_line = f"{pos_label} / {dur_label}  ({percent:.0f}%)"
                log_file.write(f"[{time.strftime('%H:%M:%S')}] {progress_line}\n")
                log_file.flush()
                if verbose and not quiet:
                    print(f"\r  {progress_line}", end="", flush=True)
            worker.join(timeout=1.0)
        if verbose and not quiet:
            print()

        if "error" in outcome:
            raise outcome["error"]
        write_status(pid, file=str(audio_path), model=model_name, duration=duration,
                     position=duration, percent=100.0, started_at=started_at)
        log_file.write(f"[{time.strftime('%H:%M:%S')}] Done.\n")
    finally:
        log_file.close()
        log_path.unlink(missing_ok=True)

    result = outcome["result"]
    segments: list[dict] = result.get("segments", [])

    with out_txt.open("w", encoding="utf-8") as f:
        for seg in segments:
            text = (seg.get("text") or "").strip()
            if text:
                f.write(text + "\n")

    if write_srt_file:
        write_srt(segments, out_srt)

    if not quiet:
        summary = f"\N{WHITE HEAVY CHECK MARK} {audio_path.name} \N{RIGHTWARDS ARROW} {out_txt.name}"
        if write_srt_file:
            summary += f" (+ {out_srt.name})"
        print(summary)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="whisp",
        description="Transcribe audio into raw, as-spoken text using MLX Whisper (Apple Silicon).",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "inputs", nargs="*",
        help="Audio files, folders, or glob patterns. Omit entirely to show currently running jobs.",
    )
    parser.add_argument(
        "-l", "--language", default=None,
        help="Force a language code (e.g. fr, en). Omit to auto-detect per file.",
    )
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL,
        help=f"tiny|base|small|medium|large-v3|large-v3-turbo, or a full org/repo id "
             f"(default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Write outputs here instead of alongside each source file.",
    )
    parser.add_argument("--srt", action="store_true", help="Also write .srt subtitle files.")
    parser.add_argument("-q", "--quiet", action="store_true", help="Only print errors and the final summary.")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Print a live position/percent line while transcribing long files.",
    )
    parser.add_argument("--version", action="version", version=f"whisp {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.inputs:
        print_dashboard()
        return 0

    files = sorted(iter_input_files(args.inputs))
    if not files:
        print("No audio files found. Supported: " + ", ".join(sorted(AUDIO_EXTS)), file=sys.stderr)
        return 1

    model_repo = resolve_model(args.model)
    mlx_whisper = load_backend()

    succeeded = failed = 0
    try:
        for audio in files:
            try:
                transcribe_file(
                    mlx_whisper, audio, args.model, model_repo,
                    args.language, args.srt, args.output_dir, args.quiet, args.verbose,
                )
                succeeded += 1
            except Exception as exc:
                failed += 1
                print(f"\N{CROSS MARK} Error on {audio}: {exc}", file=sys.stderr)
    finally:
        remove_status(os.getpid())

    if not args.quiet or failed:
        print(f"\nDone: {succeeded} succeeded, {failed} failed, {len(files)} total.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
