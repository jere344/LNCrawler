"""Thermal guard: pauses the GPU containers while the card runs hot, then resumes them.

    python guard.py

Every POLL_S it reads the GPU temperature (nvidia-smi) and, when CPU_TEMP_URL is set, the hottest CPU sensor from a
LibreHardwareMonitor web server (Windows exposes no CPU sensor to Docker). At LIMIT_C or above it pauses TARGETS
(docker pause: the processes freeze, nothing is lost). It resumes them once every reading is at or below RESUME_C and
at least MIN_PAUSE_S have passed. The worker itself is never paused, so its heartbeats keep the part's lease.
It owns the paused state of TARGETS: a target paused or resumed by hand is put back on the next poll. A failed pause
is retried every poll; with no temperature for 3 polls the targets stay paused until readings return.
Stdlib only; talks to the Docker engine through /var/run/docker.sock.
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request

LIMIT_C = float(os.environ.get("LIMIT_C", "80"))
RESUME_C = float(os.environ.get("RESUME_C", "68"))
MIN_PAUSE_S = float(os.environ.get("MIN_PAUSE_S", "120"))
POLL_S = float(os.environ.get("POLL_S", "10"))
TARGETS = [t.strip() for t in os.environ.get("TARGETS", "").split(",") if t.strip()]
CPU_TEMP_URL = os.environ.get("CPU_TEMP_URL", "")
STATUS_EVERY_S = float(os.environ.get("STATUS_EVERY_S", "600"))

log = logging.getLogger("thermal")


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, path: str):
        super().__init__("localhost", timeout=30)
        self._path = path

    def connect(self) -> None:
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(30)
        self.sock.connect(self._path)


def docker(method: str, path: str) -> tuple[int, bytes]:
    conn = _UnixConnection("/var/run/docker.sock")
    try:
        conn.request(method, path)
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def paused(name: str) -> bool | None:
    """True or False, or None when the container does not exist or is not running."""
    status, body = docker("GET", f"/containers/{name}/json")
    if status != 200:
        return None
    state = json.loads(body).get("State", {})
    if not state.get("Running"):
        return None
    return bool(state.get("Paused"))


def set_paused(names: list[str], pause: bool) -> bool:
    """Pauses or resumes each container. False when any of them could not be reached or changed; the next poll tries
    again."""
    ok = True
    for name in names:
        try:
            now = paused(name)
            if now is None or now == pause:
                continue
            status, body = docker("POST", f"/containers/{name}/{'pause' if pause else 'unpause'}")
        except Exception as exc:
            log.error("%s %s failed: %s", "pause" if pause else "unpause", name, exc)
            ok = False
            continue
        if status >= 300:
            log.error("%s %s failed: HTTP %s %s", "pause" if pause else "unpause", name, status, body[:200])
            ok = False
        else:
            log.info("%s %s", "paused" if pause else "resumed", name)
    return ok


def gpu_temps() -> list[float]:
    out = subprocess.run(
        ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=20, check=True,
    ).stdout
    return [float(line) for line in out.split() if line.strip()]


def cpu_temp() -> float | None:
    """The hottest CPU temperature a LibreHardwareMonitor data.json reports, or None."""
    if not CPU_TEMP_URL:
        return None
    with urllib.request.urlopen(CPU_TEMP_URL, timeout=10) as response:
        tree = json.load(response)
    found: list[float] = []

    def walk(node: dict, cpu: bool) -> None:
        cpu = cpu or "cpu" in str(node.get("ImageURL", "")).lower()
        value = str(node.get("Value", ""))
        if cpu and value.endswith("°C"):
            try:
                found.append(float(value.replace("°C", "").replace(",", ".").strip()))
            except ValueError:
                pass
        for child in node.get("Children", []):
            walk(child, cpu)

    walk(tree, False)
    return max(found) if found else None


def readings() -> dict[str, float]:
    out: dict[str, float] = {}
    for n, temp in enumerate(gpu_temps()):
        out[f"gpu{n}"] = temp
    try:
        cpu = cpu_temp()
    except Exception as exc:  # a missing sensor server must not stop the GPU guard
        log.warning("cpu temperature unavailable: %s", exc)
        cpu = None
    if cpu is not None:
        out["cpu"] = cpu
    return out


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    if not TARGETS:
        log.error("TARGETS is empty")
        return 1

    def stop(*_: object) -> None:
        log.info("stopping: resuming targets")
        set_paused(TARGETS, False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    log.info("limit %.0f C, resume at %.0f C after at least %.0f s, targets %s, cpu sensor %s",
             LIMIT_C, RESUME_C, MIN_PAUSE_S, ",".join(TARGETS), CPU_TEMP_URL or "none")
    hot_since: float | None = None
    last_status = float("-inf")
    failures = 0
    while True:
        try:
            temps = readings()
            if not temps:
                raise RuntimeError("nvidia-smi reported no GPU")
            failures = 0
        except Exception as exc:
            failures += 1
            log.error("temperature read failed (%d in a row): %s", failures, exc)
            if failures >= 3:  # blind: stay paused rather than run unwatched
                if hot_since is None:
                    log.error("no temperature for 3 polls: pausing targets until readings return")
                    hot_since = time.monotonic()
                set_paused(TARGETS, True)
            time.sleep(POLL_S)
            continue
        hottest = max(temps.values())
        shown = " ".join(f"{k}={v:.0f}C" for k, v in temps.items())
        now = time.monotonic()
        if hot_since is None and hottest >= LIMIT_C:
            log.warning("too hot (%s): pausing for at least %.0f s", shown, MIN_PAUSE_S)
            hot_since = now
            set_paused(TARGETS, True)
        elif hot_since is not None and hottest <= RESUME_C and now - hot_since >= MIN_PAUSE_S:
            log.info("cooled (%s) after %.0f s: resuming", shown, now - hot_since)
            hot_since = None
            set_paused(TARGETS, False)
        elif hot_since is not None:
            set_paused(TARGETS, True)  # retries a pause that failed, and re-pauses a target resumed by hand
        else:
            set_paused(TARGETS, False)  # a target left paused by a previous run, or by hand
        if now - last_status >= STATUS_EVERY_S:
            log.info("status %s %s", shown, "PAUSED" if hot_since is not None else "running")
            last_status = now
        time.sleep(POLL_S)

if __name__ == "__main__":
    sys.exit(main())
