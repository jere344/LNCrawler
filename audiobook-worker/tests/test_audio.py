import subprocess

import pytest

from worker import audio

pytestmark = pytest.mark.skipif(
    subprocess.run(["sh", "-c", "command -v ffmpeg && command -v ffprobe"], capture_output=True).returncode != 0,
    reason="needs ffmpeg and ffprobe on PATH",
)


def _ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


@pytest.fixture(scope="module")
def source_mp3(tmp_path_factory):
    """20 s of tone bursts: 1 s silent lead-in, 2 s tone / 2 s silence, 2 s silent tail."""
    path = str(tmp_path_factory.mktemp("audio") / "source.mp3")
    expr = r"aevalsrc=if(lt(t\,1)+gte(t\,18)\,0\,if(lt(mod(t\,4)\,2)\,0.3*sin(2*PI*220*t)\,0)):s=44100:d=20"
    _ffmpeg("-f", "lavfi", "-i", expr, "-c:a", "libmp3lame", "-b:a", "128k", path)
    return path


def test_encode_checked_produces_a_file_that_validates(source_mp3, tmp_path):
    dst = str(tmp_path / "chapter.ogg")
    audio.encode_checked(source_mp3, dst)
    assert audio.validate(dst) == []


def test_encode_trims_the_silent_edges(source_mp3, tmp_path):
    dst = str(tmp_path / "trimmed.ogg")
    audio.encode_chapter(source_mp3, dst)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", dst],
        capture_output=True,
        text=True,
        check=True,
    )
    duration = float(probe.stdout.strip())
    # 20 s in, with 1 s of lead-in and 2 s of tail trimmed down to the allowed edges.
    assert 10 < duration < 19


def test_validate_rejects_the_mp3_source(source_mp3):
    failures = audio.validate(source_mp3)
    assert any("codec" in f or "container" in f for f in failures)


def test_validate_rejects_a_non_media_file(tmp_path):
    bad = tmp_path / "bad.ogg"
    bad.write_bytes(b"definitely not an ogg file")
    failures = audio.validate(str(bad))
    assert failures == ["ffprobe could not read the file"]


def test_missing_binary_is_retryable():
    with pytest.raises(audio.AudioError) as info:
        audio._exec(["lncrawler-no-such-binary-for-tests"])
    assert info.value.retryable is True


def test_a_timed_out_tool_run_is_retryable(monkeypatch):
    seen = {}

    def run(cmd, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout"))

    monkeypatch.setattr(audio.subprocess, "run", run)
    with pytest.raises(audio.AudioError) as info:
        audio._run(["ffmpeg", "-i", "chapter.mp3"])
    assert info.value.retryable is True
    assert info.value.reasons == ["ffmpeg timed out after 900 s"]
    assert seen["timeout"] == audio.SUBPROCESS_TIMEOUT_S == 900


def test_failed_encode_tool_run_is_retryable(tmp_path):
    with pytest.raises(audio.AudioError) as info:
        audio.encode_checked(str(tmp_path / "missing.mp3"), str(tmp_path / "out.ogg"))
    assert info.value.retryable is True


def test_final_validation_failure_is_not_retryable(tmp_path, monkeypatch):
    monkeypatch.setattr(audio, "encode_chapter", lambda src, dst, **kw: None)
    monkeypatch.setattr(audio, "validate", lambda path: ["integrated loudness -30 LUFS"])
    with pytest.raises(audio.AudioError) as info:
        audio.encode_checked("src.mp3", str(tmp_path / "out.ogg"))
    assert info.value.retryable is False
    assert info.value.reasons == ["integrated loudness -30 LUFS"]


def test_validate_flags_a_long_internal_pause(tmp_path):
    """Opus with no trim: 5 s of silence in the middle is over the 3 s limit."""
    src = tmp_path / "gap.ogg"
    expr = r"aevalsrc=if(between(t\,5\,10)\,0\,0.3*sin(2*PI*220*t)):s=44100:d=15"
    _ffmpeg("-f", "lavfi", "-i", expr, "-ac", "1", "-ar", "48000", "-c:a", "libopus", "-b:a", "24k", str(src))
    failures = audio.validate(str(src))
    assert any("internal silence" in f for f in failures), failures


def test_the_third_attempt_is_used_when_the_first_two_fail_the_peak(tmp_path, monkeypatch):
    encoded = []
    verdicts = iter([["true peak -1.4 dBTP, want <= -1.5"], ["true peak -1.4 dBTP, want <= -1.5"], []])
    monkeypatch.setattr(audio, "encode_chapter", lambda src, dst, **kw: encoded.append(kw))
    monkeypatch.setattr(audio, "validate", lambda path: next(verdicts))
    audio.encode_checked("src.mp3", str(tmp_path / "out.ogg"))
    assert [kw["target_tp"] for kw in encoded] == [-2.0, -2.5, -3.0]
    assert encoded[2]["trim"] == audio.TRIM_RETUNED


def test_a_crashed_check_gets_the_next_attempt(tmp_path, monkeypatch):
    encoded = []
    outcomes = iter([audio.AudioError(["ffmpeg analysis exited 1"]), []])

    def validate(path):
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(audio, "encode_chapter", lambda src, dst, **kw: encoded.append(kw))
    monkeypatch.setattr(audio, "validate", validate)
    audio.encode_checked("src.mp3", str(tmp_path / "out.ogg"))
    assert len(encoded) == 2


def test_a_crashed_check_on_the_last_attempt_is_raised(tmp_path, monkeypatch):
    def validate(path):
        raise audio.AudioError(["ffmpeg analysis exited 1"])

    monkeypatch.setattr(audio, "encode_chapter", lambda src, dst, **kw: None)
    monkeypatch.setattr(audio, "validate", validate)
    with pytest.raises(audio.AudioError) as info:
        audio.encode_checked("src.mp3", str(tmp_path / "out.ogg"))
    assert info.value.retryable is True
    assert info.value.reasons == ["ffmpeg analysis exited 1"]
