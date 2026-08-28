"""Unit tests for whisp.py.

These tests never import the real mlx_whisper backend (and so don't require
Apple Silicon or a downloaded model): transcribe_file() and main() take the
backend as a parameter / via load_backend(), so a lightweight fake is
substituted instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import whisp


class FakeMlxWhisper:
    """Stand-in for the mlx_whisper module, returning canned segments."""

    def __init__(self, segments: list[dict]) -> None:
        self.segments = segments
        self.calls: list[tuple[str, dict]] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append((audio, kwargs))
        text = " ".join(s["text"] for s in self.segments)
        return {"text": text, "segments": self.segments, "language": kwargs.get("language") or "en"}


def make_segments() -> list[dict]:
    return [
        {"start": 0.0, "end": 1.5, "text": " Bonjour tout le monde "},
        {"start": 1.5, "end": 3.0, "text": "  "},  # blank after strip: must be skipped
        {"start": 3.0, "end": 5.25, "text": "Ça marche bien"},
    ]


# --- srt_timestamp -----------------------------------------------------

@pytest.mark.parametrize(
    "seconds, expected",
    [
        (0.0, "00:00:00,000"),
        (1.5, "00:00:01,500"),
        (65.0, "00:01:05,000"),
        (3661.234, "01:01:01,234"),
    ],
)
def test_srt_timestamp(seconds, expected):
    assert whisp.srt_timestamp(seconds) == expected


# --- resolve_model -------------------------------------------------------

@pytest.mark.parametrize(
    "name, expected_repo",
    [
        ("tiny", "mlx-community/whisper-tiny-mlx"),
        ("large-v3", "mlx-community/whisper-large-v3-mlx"),
        ("large-v3-turbo", "mlx-community/whisper-large-v3-turbo"),
        ("turbo", "mlx-community/whisper-large-v3-turbo"),  # alias
    ],
)
def test_resolve_model_known_names(name, expected_repo):
    assert whisp.resolve_model(name) == expected_repo


def test_resolve_model_passthrough_repo_id():
    custom = "mlx-community/whisper-large-v3-turbo-q4"
    assert whisp.resolve_model(custom) == custom


def test_resolve_model_unknown_exits():
    with pytest.raises(SystemExit):
        whisp.resolve_model("not-a-real-model")


# --- iter_input_files ------------------------------------------------------

def test_iter_input_files_single_file(tmp_path: Path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    found = list(whisp.iter_input_files([str(audio)]))
    assert found == [audio]


def test_iter_input_files_unsupported_extension_is_skipped(tmp_path: Path, capsys):
    doc = tmp_path / "notes.txt"
    doc.write_text("hello")
    found = list(whisp.iter_input_files([str(doc)]))
    assert found == []
    assert "unsupported" in capsys.readouterr().err


def test_iter_input_files_directory_recursive(tmp_path: Path):
    sub = tmp_path / "nested"
    sub.mkdir()
    a = tmp_path / "a.mp3"
    b = sub / "b.m4a"
    c = sub / "c.txt"
    a.write_bytes(b"")
    b.write_bytes(b"")
    c.write_bytes(b"")
    found = set(whisp.iter_input_files([str(tmp_path)]))
    assert found == {a, b}


def test_iter_input_files_glob_pattern(tmp_path: Path):
    a = tmp_path / "one.wav"
    b = tmp_path / "two.wav"
    a.write_bytes(b"")
    b.write_bytes(b"")
    found = set(whisp.iter_input_files([str(tmp_path / "*.wav")]))
    assert found == {a, b}


def test_iter_input_files_deduplicates(tmp_path: Path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    found = list(whisp.iter_input_files([str(audio), str(audio), str(tmp_path)]))
    assert found == [audio]


def test_iter_input_files_missing_path_warns(capsys):
    found = list(whisp.iter_input_files(["/no/such/path.wav"]))
    assert found == []
    assert "not found" in capsys.readouterr().err


# --- write_srt -------------------------------------------------------------

def test_write_srt_format(tmp_path: Path):
    out = tmp_path / "out.srt"
    whisp.write_srt(make_segments(), out)
    content = out.read_text(encoding="utf-8")
    assert content == (
        "1\n00:00:00,000 --> 00:00:01,500\nBonjour tout le monde\n\n"
        "2\n00:00:03,000 --> 00:00:05,250\nÇa marche bien\n\n"
    )


# --- transcribe_file ---------------------------------------------------

def test_transcribe_file_writes_raw_transcript(tmp_path: Path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    backend = FakeMlxWhisper(make_segments())

    whisp.transcribe_file(
        backend, audio, "large-v3-turbo", "mlx-community/whisper-large-v3-turbo",
        language=None, write_srt_file=False, output_dir=None, quiet=True,
    )

    out_txt = tmp_path / "clip_transcript_raw.txt"
    assert out_txt.exists()
    assert out_txt.read_text(encoding="utf-8") == "Bonjour tout le monde\nÇa marche bien\n"
    assert not (tmp_path / "clip.srt").exists()
    assert backend.calls[0][1]["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo"


def test_transcribe_file_writes_srt_when_requested(tmp_path: Path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    backend = FakeMlxWhisper(make_segments())

    whisp.transcribe_file(
        backend, audio, "large-v3-turbo", "mlx-community/whisper-large-v3-turbo",
        language="fr", write_srt_file=True, output_dir=None, quiet=True,
    )

    assert (tmp_path / "clip.srt").exists()
    assert backend.calls[0][1]["language"] == "fr"


def test_transcribe_file_respects_output_dir(tmp_path: Path):
    audio_dir = tmp_path / "source"
    audio_dir.mkdir()
    audio = audio_dir / "clip.wav"
    audio.write_bytes(b"")
    out_dir = tmp_path / "out"
    backend = FakeMlxWhisper(make_segments())

    whisp.transcribe_file(
        backend, audio, "tiny", "mlx-community/whisper-tiny-mlx",
        language=None, write_srt_file=False, output_dir=out_dir, quiet=True,
    )

    assert (out_dir / "clip_transcript_raw.txt").exists()
    assert not (audio_dir / "clip_transcript_raw.txt").exists()


# --- main ------------------------------------------------------------------

def test_main_returns_1_when_no_files_found(capsys):
    exit_code = whisp.main(["/no/such/file.wav"])
    assert exit_code == 1
    assert "No audio files found" in capsys.readouterr().err


def test_main_invalid_model_exits(tmp_path: Path):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    with pytest.raises(SystemExit):
        whisp.main([str(audio), "--model", "bogus"])


def test_main_success_with_fake_backend(tmp_path: Path, monkeypatch):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    backend = FakeMlxWhisper(make_segments())
    monkeypatch.setattr(whisp, "load_backend", lambda: backend)

    exit_code = whisp.main([str(audio), "--srt", "--quiet"])

    assert exit_code == 0
    assert (tmp_path / "clip_transcript_raw.txt").exists()
    assert (tmp_path / "clip.srt").exists()


def test_main_reports_failures_with_nonzero_exit(tmp_path: Path, monkeypatch):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")

    class BrokenBackend:
        def transcribe(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(whisp, "load_backend", lambda: BrokenBackend())

    exit_code = whisp.main([str(audio), "--quiet"])

    assert exit_code == 1
    assert not (tmp_path / "clip_transcript_raw.txt").exists()


# --- build_parser ------------------------------------------------------

def test_parser_defaults():
    args = whisp.build_parser().parse_args(["clip.wav"])
    assert args.model == whisp.DEFAULT_MODEL
    assert args.language is None
    assert args.srt is False
    assert args.quiet is False
    assert args.output_dir is None
