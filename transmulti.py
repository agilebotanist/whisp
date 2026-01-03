#!/usr/bin/env python3
"""
Batch transcribe audio files into raw as-spoken transcripts (and optional SRT subtitles).

This script provides a powerful batch processing interface for transcribing multiple
audio files using the faster-whisper library. It supports files, folders, and glob patterns.

Usage examples:
  python transmulti.py Buc.m4a
  python transmulti.py file1.m4a file2.wav
  python transmulti.py /path/to/folder
  python transmulti.py "*.m4a" "*.wav"

Options:
  --language fr         # force French; omit to auto-detect per segment
  --model large-v3      # tiny | base | small | medium | large-v3 (default: large-v3)
  --device cpu          # cpu (recommended on M-series) | cuda
  --compute int8        # int8 | int8_float32 | float16 | float32 (default: int8)
  --srt                 # also write .srt subtitles
"""

import sys
import argparse
from pathlib import Path
from typing import Iterable, List
from faster_whisper import WhisperModel
import glob

# Supported audio file extensions
AUDIO_EXTS = {".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".wma", ".mkv", ".mp4", ".mov"}

def iter_input_files(inputs: List[str]) -> Iterable[Path]:
    """
    Expand files, folders, and glob patterns into a list of audio files.

    Args:
        inputs: List of file paths, directory paths, or glob patterns

    Yields:
        Path objects for each unique audio file found

    This function intelligently handles:
    - Individual files: yields if they have a supported audio extension
    - Directories: recursively searches for all audio files
    - Glob patterns (*.m4a, **/*.wav, etc.): expands and yields matching files
    """
    seen = set()  # Track files we've already yielded to avoid duplicates

    for inp in inputs:
        p = Path(inp)

        # Check if the input contains glob wildcard characters
        if any(ch in inp for ch in "*?[]"):
            # Expand the glob pattern
            for g in glob.glob(inp, recursive=True):
                gp = Path(g)
                # If it's a file with a supported extension, yield it
                if gp.is_file() and gp.suffix.lower() in AUDIO_EXTS and gp not in seen:
                    seen.add(gp)
                    yield gp
                # If it's a directory, recursively find audio files within it
                elif gp.is_dir():
                    for f in gp.rglob("*"):
                        if f.is_file() and f.suffix.lower() in AUDIO_EXTS and f not in seen:
                            seen.add(f)
                            yield f
            continue

        # Handle direct file paths
        if p.is_file() and p.suffix.lower() in AUDIO_EXTS and p not in seen:
            seen.add(p)
            yield p
        # Handle directory paths
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in AUDIO_EXTS and f not in seen:
                    seen.add(f)
                    yield f
        else:
            # Path doesn't exist or has unsupported extension
            print(f"⚠️  Skipping: {inp} (not found or unsupported extension)", file=sys.stderr)

def srt_timestamp(seconds: float) -> str:
    """
    Convert seconds to SRT subtitle timestamp format.

    Args:
        seconds: Time in seconds (can be fractional)

    Returns:
        Formatted timestamp string in SRT format: HH:MM:SS,mmm

    Example:
        srt_timestamp(65.5) -> "00:01:05,500"
    """
    ms = int(round(seconds * 1000))  # Convert to milliseconds
    h, rem = divmod(ms, 3600_000)    # Extract hours
    m, rem = divmod(rem, 60_000)     # Extract minutes
    s, ms = divmod(rem, 1000)        # Extract seconds and milliseconds
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(segments, out_path: Path):
    """
    Write transcription segments to an SRT subtitle file.

    Args:
        segments: Iterable of transcription segments with start, end, and text attributes
        out_path: Path where the SRT file should be written

    SRT format structure:
        1
        00:00:00,000 --> 00:00:05,000
        First subtitle text

        2
        00:00:05,500 --> 00:00:10,000
        Second subtitle text
    """
    with open(out_path, "w", encoding="utf-8") as srt:
        for i, seg in enumerate(segments, start=1):
            # Convert segment timestamps to SRT format
            start = srt_timestamp(seg.start)
            end = srt_timestamp(seg.end)
            text = (seg.text or "").strip()

            # Skip empty segments
            if not text:
                continue

            # Write SRT entry: index, timestamps, text, blank line
            srt.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def transcribe_file(model: WhisperModel, audio_path: Path, language: str | None, write_srt_file: bool):
    """
    Transcribe a single audio file and write output files.

    Args:
        model: Initialized WhisperModel instance
        audio_path: Path to the audio file to transcribe
        language: Language code (e.g., 'fr', 'en') or None for auto-detection
        write_srt_file: If True, also generate an SRT subtitle file

    Outputs:
        - *_transcript_raw.txt: Plain text transcript (one segment per line)
        - *.srt: SRT subtitle file (if write_srt_file is True)
    """
    # Generate output file paths
    out_txt = audio_path.with_name(audio_path.stem + "_transcript_raw.txt")
    out_srt = audio_path.with_name(audio_path.stem + ".srt")

    lang_label = language if language else "auto"
    print(f"🔊 Transcribing {audio_path} (language={lang_label}) …")

    # Transcribe the audio with settings optimized for raw, as-spoken output
    segments, info = model.transcribe(
        str(audio_path),
        language=language,                 # None => auto-detect (handles FR/EN mixes)
        beam_size=1,                       # Single beam for faster decoding
        vad_filter=False,                  # No voice activity detection filtering
        condition_on_previous_text=False,  # Don't condition on context for 'raw' feel
        temperature=0.0,                   # Deterministic output
        without_timestamps=False           # Keep timestamps for SRT generation
    )

    # Materialize the segments iterator into a list
    # (needed if writing both txt and srt, as we iterate twice)
    seg_list = list(segments)

    # Write raw text transcript (one segment per line)
    with open(out_txt, "w", encoding="utf-8") as f:
        for seg in seg_list:
            text = (seg.text or "").strip()
            if text:
                f.write(text + "\n")

    # Optionally write SRT subtitle file
    if write_srt_file:
        write_srt(seg_list, out_srt)

    # Print success message
    done = f"✅ {audio_path.name} → {out_txt.name}"
    if write_srt_file:
        done += f" (+ {out_srt.name})"
    print(done)

def main():
    """
    Main entry point for batch audio transcription.

    Parses command-line arguments, discovers audio files, loads the model,
    and processes each file in the batch.
    """
    # Set up command-line argument parser
    parser = argparse.ArgumentParser(description="Batch raw transcription with faster-whisper.")
    parser.add_argument("inputs", nargs="+", help="Files, folders, or glob patterns.")
    parser.add_argument("--language", default=None, help="e.g., fr. Omit for auto-detect (recommended for mixed FR/EN).")
    parser.add_argument("--model", default="large-v3", help="tiny/base/small/medium/large-v3 (default: large-v3)")
    parser.add_argument("--device", default="cpu", help="cpu or cuda (default: cpu)")
    parser.add_argument("--compute", default="int8", help="int8 | int8_float32 | float16 | float32 (default: int8)")
    parser.add_argument("--srt", action="store_true", help="Also write .srt subtitles.")
    args = parser.parse_args()

    # Discover all audio files from the provided inputs
    files = list(iter_input_files(args.inputs))
    if not files:
        print("No audio files found. Supported: " + ", ".join(sorted(AUDIO_EXTS)))
        sys.exit(1)

    # Load the Whisper model once for the entire batch
    # This is more efficient than loading it separately for each file
    model = WhisperModel(args.model, device=args.device, compute_type=args.compute)

    # Process each audio file in the batch
    for audio in files:
        try:
            transcribe_file(model, audio, args.language, args.srt)
        except Exception as e:
            # Continue processing other files even if one fails
            print(f"❌ Error on {audio}: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
