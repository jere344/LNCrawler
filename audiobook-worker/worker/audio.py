"""ffmpeg/ffprobe: encode a chapter to the contract's Ogg/Opus format, and check it the way prod does."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess

log = logging.getLogger("worker.audio")

LOUDNESS_I = -18.0
LOUDNESS_LRA = 11
MAX_BITRATE_BPS = 40_000
MIN_DURATION_S = 10.0
DURATION_TOLERANCE = 0.01
LOUDNESS_TOLERANCE = 1.0
MAX_TRUE_PEAK_DBTP = -1.5
EDGE_SILENCE_MAX_S = 0.5
INTERNAL_SILENCE_MAX_S = 3.0
SILENCE_NOISE = "-50dB"
SUBPROCESS_TIMEOUT_S = 900

# Trims leading and trailing silence down to 0.3 s. The areverse pair turns the second silenceremove onto the end of the
# chapter. Internal pauses over 2.5 s are removed entirely (stop_silence defaults to 0), not shortened to 2.5 s.
TRIM = (
    "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-50dB,"
    "areverse,"
    "silenceremove=start_periods=1:start_silence=0.3:start_threshold=-50dB,"
    "areverse,"
    "silenceremove=stop_periods=-1:stop_duration=2.5:stop_threshold=-50dB"
)
# Retune for the later attempts: tighter internal pauses, more headroom on the peak.
TRIM_RETUNED = TRIM.replace("stop_duration=2.5", "stop_duration=2.0")
ATTEMPTS: tuple[dict[str, object], ...] = (
    {"trim": TRIM, "target_tp": -2.0},
    {"trim": TRIM_RETUNED, "target_tp": -2.5},
    {"trim": TRIM_RETUNED, "target_tp": -3.0},
)


class AudioError(Exception):
    """retryable=False only for a final validation failure. Tool crashes and missing binaries are retryable."""

    def __init__(self, reasons: list[str], retryable: bool = True):
        super().__init__("; ".join(reasons))
        self.reasons = list(reasons)
        self.retryable = retryable


def _exec(cmd: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=SUBPROCESS_TIMEOUT_S
        )
    except OSError as exc:
        raise AudioError([f"{cmd[0]} could not run: {exc}"], retryable=True) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioError([f"{cmd[0]} timed out after {SUBPROCESS_TIMEOUT_S} s"], retryable=True) from exc


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    proc = _exec(cmd)
    if proc.returncode != 0:
        tail = proc.stderr.strip().splitlines()[-5:]
        raise AudioError([f"{cmd[0]} exited {proc.returncode}: {' | '.join(tail)}"], retryable=True)
    return proc


_LOUDNORM_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")


def _loudnorm_measure(src: str, trim: str, target_tp: float) -> dict[str, str]:
    af = f"{trim},loudnorm=I={LOUDNESS_I}:TP={target_tp}:LRA={LOUDNESS_LRA}:print_format=json"
    proc = _run(["ffmpeg", "-hide_banner", "-nostdin", "-i", src, "-af", af, "-f", "null", "-"])
    blocks = _LOUDNORM_JSON.findall(proc.stderr)
    if not blocks:
        raise AudioError(["loudnorm pass 1 printed no measurements"], retryable=True)
    try:
        data = json.loads(blocks[-1])
        return {
            "measured_I": data["input_i"],
            "measured_TP": data["input_tp"],
            "measured_LRA": data["input_lra"],
            "measured_thresh": data["input_thresh"],
            "offset": data["target_offset"],
        }
    except (ValueError, KeyError) as exc:
        raise AudioError([f"loudnorm pass 1 output unreadable: {exc}"], retryable=True) from exc


def encode_chapter(src: str, dst: str, *, trim: str = TRIM, target_tp: float = -2.0) -> None:
    """Two-pass loudnorm, then Opus at 24 kbps VBR, mono, 48 kHz, no metadata."""
    m = _loudnorm_measure(src, trim, target_tp)
    af = (
        f"{trim},loudnorm=I={LOUDNESS_I}:TP={target_tp}:LRA={LOUDNESS_LRA}"
        f":measured_I={m['measured_I']}:measured_TP={m['measured_TP']}"
        f":measured_LRA={m['measured_LRA']}:measured_thresh={m['measured_thresh']}"
        f":offset={m['offset']}:linear=true"
    )
    _run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", src,
            "-af", af,
            "-ac", "1", "-ar", "48000",
            "-c:a", "libopus", "-b:a", "24k", "-vbr", "on", "-application", "audio",
            "-map_metadata", "-1",
            dst,
        ]
    )


def _probe(path: str) -> dict | None:
    """None when ffprobe cannot read the file (a validation failure). A missing binary raises."""
    proc = _exec(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout or "{}")
    except ValueError:
        return None


_LUFS = re.compile(r"Integrated loudness:\s+I:\s+(-?[\d.]+) LUFS")
_TRUE_PEAK = re.compile(r"True peak:\s+Peak:\s+(-?[\d.]+|-inf) dBFS")
_SILENCE = re.compile(r"silence_(start|end): (-?[\d.]+)(?: \| silence_duration: ([\d.]+))?")
_TIME = re.compile(r"time=(\d+):(\d\d):(\d\d\.\d+)")


def _silences(stderr: str, decoded_s: float | None) -> list[tuple[float, float]]:
    """(start, end) pairs from silencedetect output, in order."""
    out: list[tuple[float, float]] = []
    start: float | None = None
    for kind, value, _dur in _SILENCE.findall(stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            out.append((start, float(value)))
            start = None
    if start is not None and decoded_s is not None:
        out.append((start, decoded_s))
    return out


def validate(path: str) -> list[str]:
    """Returns the failed checks (an empty list means the file passes)."""
    failures: list[str] = []
    info = _probe(path)
    if info is None:
        return ["ffprobe could not read the file"]

    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    fmt = info.get("format", {})
    if not audio:
        return ["no audio stream"]
    stream = audio[0]
    if stream.get("codec_name") != "opus":
        failures.append(f"codec {stream.get('codec_name')!r}, want opus")
    if "ogg" not in str(fmt.get("format_name", "")).split(","):
        failures.append(f"container {fmt.get('format_name')!r}, want ogg")
    if int(stream.get("channels") or 0) != 1:
        failures.append(f"channels {stream.get('channels')}, want 1")
    if int(stream.get("sample_rate") or 0) != 48000:
        failures.append(f"sample rate {stream.get('sample_rate')}, want 48000")

    try:
        declared = float(fmt["duration"])
    except (KeyError, TypeError, ValueError):
        return failures + ["container declares no duration"]
    if declared <= MIN_DURATION_S:
        failures.append(f"duration {declared:.1f} s, want > {MIN_DURATION_S:.0f} s")
    size = os.path.getsize(path)
    if declared > 0 and size * 8 / declared > MAX_BITRATE_BPS:
        failures.append(f"average bitrate {size * 8 / declared / 1000:.1f} kbps, want <= 40")

    proc = _exec(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-i", path,
            "-af", "ebur128=peak=true,silencedetect=n=-50dB:d=0.5",
            "-f", "null", "-",
        ]
    )
    if proc.returncode != 0:
        raise AudioError([f"ffmpeg analysis exited {proc.returncode}"], retryable=True)
    err = proc.stderr

    times = _TIME.findall(err)
    decoded_s = None
    if times:
        h, m, s = times[-1]
        decoded_s = int(h) * 3600 + int(m) * 60 + float(s)
    if decoded_s is None:
        failures.append("could not measure decoded duration")
    elif abs(decoded_s - declared) > DURATION_TOLERANCE * declared:
        failures.append(f"decoded {decoded_s:.2f} s vs declared {declared:.2f} s, want within 1%")

    lufs = _LUFS.search(err)
    if not lufs:
        failures.append("no integrated loudness measured")
    elif abs(float(lufs.group(1)) - LOUDNESS_I) > LOUDNESS_TOLERANCE:
        failures.append(f"integrated loudness {lufs.group(1)} LUFS, want {LOUDNESS_I:.0f} +/- 1")

    peak = _TRUE_PEAK.search(err)
    if not peak:
        failures.append("no true peak measured")
    elif peak.group(1) != "-inf" and float(peak.group(1)) > MAX_TRUE_PEAK_DBTP:
        failures.append(f"true peak {peak.group(1)} dBTP, want <= -1.5")

    for start, end in _silences(err, decoded_s):
        length = end - start
        if start <= 0.01 and length > EDGE_SILENCE_MAX_S:
            failures.append(f"leading silence {length:.2f} s, want <= 0.5 s")
        elif decoded_s is not None and end >= decoded_s - 0.05 and length > EDGE_SILENCE_MAX_S:
            failures.append(f"trailing silence {length:.2f} s, want <= 0.5 s")
        elif length > INTERNAL_SILENCE_MAX_S:
            failures.append(f"internal silence {length:.2f} s at {start:.2f} s, want <= 3 s")
    return failures


def encode_checked(src: str, dst: str) -> None:
    """Encode and validate. A failing file is encoded again with the next ATTEMPTS entry."""
    failures: list[str] = []
    for attempt, params in enumerate(ATTEMPTS, 1):
        encode_chapter(src, dst, **params)  # type: ignore[arg-type]
        try:
            failures = validate(dst)
        except AudioError as exc:
            # The analysis tool crashed, which says nothing about the file: the next attempt gets a check too.
            if not exc.retryable or attempt == len(ATTEMPTS):
                raise
            log.warning("encode attempt %d could not be checked: %s", attempt, "; ".join(exc.reasons))
            continue
        if not failures:
            return
        log.warning("encode attempt %d failed validation: %s", attempt, "; ".join(failures))
    raise AudioError(failures, retryable=False)
