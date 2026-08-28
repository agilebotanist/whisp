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
"""

from __future__ import annotations

import argparse
import glob
import platform
import sys
from collections.abc import Iterable
from pathlib import Path

try:
    from importlib.metadata import PackageNotFoundError, version

    __version__ = version("whisp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".mkv", ".mp4", ".mov"}

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
DEFAULT_MODEL = "large-v3-turbo"


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
) -> None:
    """Transcribe one audio file, writing a raw .txt transcript and optional .srt."""
    dest_dir = output_dir or audio_path.parent
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_txt = dest_dir / f"{audio_path.stem}_transcript_raw.txt"
    out_srt = dest_dir / f"{audio_path.stem}.srt"

    if not quiet:
        lang_label = language or "auto"
        print(f"\N{SPEAKER WITH THREE SOUND WAVES} {audio_path.name} (model={model_name}, language={lang_label}) …")

    result = mlx_whisper.transcribe(
        str(audio_path),
        path_or_hf_repo=model_repo,
        language=language,
        temperature=0.0,
        condition_on_previous_text=False,
        word_timestamps=False,
        verbose=None,
    )
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
    parser.add_argument("inputs", nargs="+", help="Audio files, folders, or glob patterns.")
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
    parser.add_argument("--version", action="version", version=f"whisp {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    files = sorted(iter_input_files(args.inputs))
    if not files:
        print("No audio files found. Supported: " + ", ".join(sorted(AUDIO_EXTS)), file=sys.stderr)
        return 1

    model_repo = resolve_model(args.model)
    mlx_whisper = load_backend()

    succeeded = failed = 0
    for audio in files:
        try:
            transcribe_file(
                mlx_whisper, audio, args.model, model_repo,
                args.language, args.srt, args.output_dir, args.quiet,
            )
            succeeded += 1
        except Exception as exc:
            failed += 1
            print(f"\N{CROSS MARK} Error on {audio}: {exc}", file=sys.stderr)

    if not args.quiet or failed:
        print(f"\nDone: {succeeded} succeeded, {failed} failed, {len(files)} total.")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
