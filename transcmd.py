#!/usr/bin/env python3
"""
Transcribe French audio into a raw as-spoken transcript.

This script provides a command-line interface for transcribing a single
audio file to text using the faster-whisper library.

Usage:
    python transcmd.py Buc.m4a
Output:
    Buc_transcript_raw.txt
"""

import sys
from pathlib import Path
from faster_whisper import WhisperModel

def main():
    """Main entry point for single-file transcription."""
    # Validate command-line arguments
    if len(sys.argv) < 2:
        print("Usage: python transcmd.py <audiofile>")
        sys.exit(1)

    # Parse input and output file paths
    audio_path = Path(sys.argv[1])
    out_path = audio_path.with_name(audio_path.stem + "_transcript_raw.txt")

    # Initialize the Whisper model
    # - large-v3: Most accurate model (use medium/small for faster processing)
    # - device="cpu": Optimized for Apple M-series chips
    # - compute_type="int8": 8-bit quantization for memory efficiency
    model = WhisperModel("large-v3", device="cpu", compute_type="int8")

    print(f"🔊 Transcribing {audio_path} (language=fr)…")

    # Transcribe the audio with settings optimized for raw, as-spoken output
    segments, info = model.transcribe(
        str(audio_path),
        language="fr",                       # French language (use None for auto-detect)
        beam_size=1,                         # Faster decoding with single beam
        vad_filter=False,                    # No voice activity detection filtering
        condition_on_previous_text=False,    # Don't condition on previous context (more "raw")
        temperature=0.0,                     # Deterministic output (no randomness)
        without_timestamps=False,            # Keep timestamps in segment objects
    )

    # Write each transcribed segment to the output file
    with open(out_path, "w", encoding="utf-8") as f:
        for seg in segments:
            # Write each segment on a new line, stripped of extra whitespace
            f.write(seg.text.strip() + "\n")

    print(f"✅ Saved raw transcript to {out_path}")

if __name__ == "__main__":
    main()