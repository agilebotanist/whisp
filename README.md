# Whisp - Audio Transcription Tools

A collection of Python scripts for transcribing audio files using OpenAI's Whisper model via the [faster-whisper](https://github.com/guillaumekln/faster-whisper) library. These tools are optimized for generating raw, as-spoken transcripts with optional SRT subtitle output.

## Features

- **Multiple interfaces**: From simple hardcoded examples to full-featured batch processing
- **Batch processing**: Handle multiple files, folders, and glob patterns
- **Language support**: Auto-detection or forced language (optimized for French/English)
- **Multiple output formats**: Plain text transcripts and SRT subtitles
- **Flexible model selection**: Choose from tiny to large-v3 based on accuracy/speed needs
- **Optimized for Apple Silicon**: Default settings tuned for M-series chips

## Scripts


### 1. `transcmd.py` - Single File CLI
Command-line tool for transcribing one audio file at a time.

```bash
python transcmd.py <audiofile>
```

**Example**:
```bash
python transcmd.py recording.m4a
```

**Output**: `recording_transcript_raw.txt`

### 2. `transmulti.py` - Batch Processing (Recommended)
Full-featured batch transcription with extensive options.

```bash
python transmulti.py <inputs> [options]
```

**Examples**:
```bash
# Single file
python transmulti.py audio.m4a

# Multiple files
python transmulti.py file1.m4a file2.wav file3.mp3

# Entire folder
python transmulti.py /path/to/audio/folder

# Glob patterns
python transmulti.py "*.m4a" "recordings/**/*.wav"

# With SRT subtitles
python transmulti.py audio.m4a --srt

# Force French language
python transmulti.py audio.m4a --language fr

# Use smaller/faster model
python transmulti.py audio.m4a --model medium
```

**Options**:
- `--language <code>`: Force language (e.g., `fr`, `en`). Omit for auto-detection
- `--model <name>`: Model size - `tiny`, `base`, `small`, `medium`, `large-v3` (default: `large-v3`)
- `--device <type>`: `cpu` (recommended for M-series) or `cuda` (default: `cpu`)
- `--compute <type>`: `int8`, `int8_float32`, `float16`, `float32` (default: `int8`)
- `--srt`: Also generate SRT subtitle files

**Outputs**:
- `*_transcript_raw.txt`: Plain text transcript (one segment per line)
- `*.srt`: SRT subtitle file (if `--srt` flag is used)

## Installation

### Prerequisites
- Python 3.10 or higher
- pip package manager

### Install Dependencies

```bash
pip install faster-whisper
```

### First Run
On the first run, the script will automatically download the selected Whisper model (models are cached locally for subsequent runs).

## Supported Audio Formats

`.m4a`, `.mp3`, `.wav`, `.aac`, `.flac`, `.ogg`, `.wma`, `.mkv`, `.mp4`, `.mov`

## Model Selection Guide

| Model | Size | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| `tiny` | ~75 MB | Fastest | Low | Quick drafts, testing |
| `base` | ~150 MB | Very Fast | Fair | Simple audio, speed priority |
| `small` | ~500 MB | Fast | Good | Balanced performance |
| `medium` | ~1.5 GB | Moderate | Very Good | High quality, reasonable speed |
| `large-v3` | ~3 GB | Slower | Best | Maximum accuracy (default) |

## Configuration Tips

### For Apple M-Series Chips (M1/M2/M3)
Use the default settings - they're already optimized:
```bash
--device cpu --compute int8
```

### For NVIDIA GPUs
```bash
--device cuda --compute float16
```

### For Mixed Language Content
Omit the `--language` flag to enable auto-detection per segment:
```bash
python transmulti.py audio.m4a
```

### For Pure French/English Content
Force the language for slightly better accuracy:
```bash
python transmulti.py audio.m4a --language fr
```

## Output Format

### Raw Transcript (TXT)
Each transcription segment appears on a new line, preserving the as-spoken flow:

```
Bonjour, bienvenue à cette présentation.
Aujourd'hui nous allons parler de l'intelligence artificielle.
C'est un sujet très important dans le monde moderne.
```

### SRT Subtitles
Standard SRT format with timestamps:

```
1
00:00:00,000 --> 00:00:03,500
Bonjour, bienvenue à cette présentation.

2
00:00:03,500 --> 00:00:07,000
Aujourd'hui nous allons parler de l'intelligence artificielle.
```

## Troubleshooting

### Model Download Issues
If model downloads fail, try setting the `HF_ENDPOINT` environment variable:
```bash
export HF_ENDPOINT=https://huggingface.co
python transmulti.py audio.m4a
```

### Out of Memory Errors
Switch to a smaller model or lower precision:
```bash
python transmulti.py audio.m4a --model medium --compute int8
```

### Slow Performance
Try a smaller model:
```bash
python transmulti.py audio.m4a --model small
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built with [faster-whisper](https://github.com/guillaumekln/faster-whisper) by Guillaume Klein
- Based on OpenAI's [Whisper](https://github.com/openai/whisper) speech recognition model

## Contributing

Contributions are welcome! Feel free to submit issues or pull requests.
