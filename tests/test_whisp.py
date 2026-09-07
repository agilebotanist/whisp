"""Unit tests for whisp.py.

These tests never import the real mlx_whisper backend (and so don't require
Apple Silicon or a downloaded model): transcribe_file() and main() take the
backend as a parameter / via load_backend(), so a lightweight fake is
substituted instead.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import whisp


@pytest.fixture(autouse=True)
def isolated_state_dirs(tmp_path, monkeypatch):
    """Point whisp's status/queue dirs at a scratch path for every test.

    Without this, transcribe_file() and print_dashboard() would read/write
    the real ~/Library/Application Support/Whisp on whatever machine runs
    the suite — including colliding with a genuinely running whisp job.
    """
    monkeypatch.setattr(whisp, "STATUS_DIR", tmp_path / "state" / "status")
    monkeypatch.setattr(whisp, "QUEUE_DIR", tmp_path / "state" / "queue")


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
    # Always False, regardless of the CLI's own --verbose: that's what
    # enables mlx_whisper's internal tqdm bar, which is how frame_progress()
    # observes live position. The CLI's --verbose controls a separate
    # printed line driven by that same polling, not this backend kwarg.
    assert backend.calls[0][1]["verbose"] is False


def test_transcribe_file_verbose_prints_progress_and_cleans_up_log(tmp_path: Path, capsys):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    backend = FakeMlxWhisper(make_segments())

    whisp.transcribe_file(
        backend, audio, "large-v3-turbo", "mlx-community/whisper-large-v3-turbo",
        language=None, write_srt_file=False, output_dir=None, quiet=True, verbose=True,
    )

    assert backend.calls[0][1]["verbose"] is False
    # The per-file progress log is a transient progress indicator, removed
    # once the file is done — not a permanent artifact left in the output dir.
    assert not (tmp_path / "clip_progress.log").exists()


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
    assert args.verbose is False
    assert args.output_dir is None


def test_parser_accepts_zero_inputs():
    args = whisp.build_parser().parse_args([])
    assert args.inputs == []


# --- probe_duration ----------------------------------------------------

def test_probe_duration_missing_file_returns_none(tmp_path: Path):
    assert whisp.probe_duration(tmp_path / "does-not-exist.wav") is None


def test_probe_duration_missing_ffprobe_returns_none(tmp_path: Path, monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise FileNotFoundError("ffprobe not found")

    monkeypatch.setattr(whisp.subprocess, "run", fake_run)
    assert whisp.probe_duration(tmp_path / "clip.wav") is None


# --- format_hms / progress_bar ------------------------------------------

@pytest.mark.parametrize(
    "seconds, expected",
    [(0, "0:00"), (65, "1:05"), (3661, "1:01:01")],
)
def test_format_hms(seconds, expected):
    assert whisp.format_hms(seconds) == expected


def test_progress_bar_bounds():
    assert whisp.progress_bar(0, width=10) == "░" * 10
    assert whisp.progress_bar(100, width=10) == "█" * 10
    assert whisp.progress_bar(50, width=10) == "█" * 5 + "░" * 5


# --- pid_alive -----------------------------------------------------------

def test_pid_alive_current_process():
    assert whisp.pid_alive(os.getpid()) is True


def test_pid_alive_bogus_pid():
    assert whisp.pid_alive(2**30) is False


# --- status file read/write ---------------------------------------------

def test_write_read_remove_status_roundtrip():
    pid = os.getpid()
    whisp.write_status(pid, file="clip.wav", model="tiny", duration=10.0,
                        position=5.0, percent=50.0, started_at=123.0)

    jobs = whisp.read_status_files()
    assert len(jobs) == 1
    assert jobs[0]["pid"] == pid
    assert jobs[0]["percent"] == 50.0

    whisp.remove_status(pid)
    assert whisp.read_status_files() == []


def test_read_status_files_cleans_up_dead_pid(tmp_path: Path):
    whisp.STATUS_DIR.mkdir(parents=True, exist_ok=True)
    stale = whisp.STATUS_DIR / "1073741824.json"
    stale.write_text('{"pid": 1073741824, "file": "old.wav"}', encoding="utf-8")

    assert whisp.read_status_files() == []
    assert not stale.exists()


def test_read_queue_files_cleans_up_dead_pid():
    whisp.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    stale = whisp.QUEUE_DIR / "1073741824.txt"
    stale.write_text("old.wav", encoding="utf-8")

    assert whisp.read_queue_files() == []
    assert not stale.exists()


def test_read_queue_files_lists_alive_pid():
    pid = os.getpid()
    whisp.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    (whisp.QUEUE_DIR / f"{pid}.txt").write_text("waiting.wav", encoding="utf-8")

    queued = whisp.read_queue_files()
    assert queued == [{"pid": pid, "file": "waiting.wav"}]


# --- print_dashboard -----------------------------------------------------

def test_print_dashboard_no_jobs(capsys):
    whisp.print_dashboard()
    out = capsys.readouterr().out
    assert "No whisp jobs currently running." in out
    assert "whisp <files...>" in out


def test_print_dashboard_shows_running_job(capsys):
    pid = os.getpid()
    whisp.write_status(pid, file="/x/clip.wav", model="large-v3-turbo", duration=100.0,
                        position=42.0, percent=42.0, started_at=time.time())

    whisp.print_dashboard()
    out = capsys.readouterr().out
    assert "clip.wav" in out
    assert "42.0%" in out
    assert "large-v3-turbo" in out

    whisp.remove_status(pid)


def test_print_dashboard_shows_queued_job(capsys):
    pid = os.getpid()
    whisp.QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    (whisp.QUEUE_DIR / f"{pid}.txt").write_text("/x/waiting.wav", encoding="utf-8")

    whisp.print_dashboard()
    out = capsys.readouterr().out
    assert "waiting.wav" in out
    assert "queued" in out


# --- main: bare invocation shows dashboard -------------------------------

def test_main_no_inputs_shows_dashboard_without_touching_backend(capsys, monkeypatch):
    def fail_if_called():
        raise AssertionError("load_backend() should not be called for a bare invocation")

    monkeypatch.setattr(whisp, "load_backend", fail_if_called)

    exit_code = whisp.main([])

    assert exit_code == 0
    assert "No whisp jobs currently running." in capsys.readouterr().out


def test_main_removes_status_after_batch_completes(tmp_path: Path, monkeypatch):
    audio = tmp_path / "clip.wav"
    audio.write_bytes(b"")
    backend = FakeMlxWhisper(make_segments())
    monkeypatch.setattr(whisp, "load_backend", lambda: backend)

    exit_code = whisp.main([str(audio), "--quiet"])

    assert exit_code == 0
    assert whisp.read_status_files() == []
