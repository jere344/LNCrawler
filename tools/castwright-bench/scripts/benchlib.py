"""Shared bench helpers. Stdlib only (pynvml optional): imported from both the
Castwright venv and the separate faster-qwen3-tts venv."""
import html
import json
import re
import threading
import time
import wave
from html.parser import HTMLParser

DEFAULT_TEXT = """\
The caravan reached the river crossing an hour after dusk, when the water had turned the colour of old iron.
"We camp here," said Mara, sliding down from the wagon. "Nobody crosses that ford in the dark."
Tobin looked at the far bank and frowned. "The merchants behind us will not wait for morning."
"Then the merchants can drown," she answered, and began unbuckling the harness.
For a while the only sounds were the river and the tired complaints of the horses.
Somewhere upstream a heron lifted off the shallows, its wings beating slow and heavy against the cold air.
The old guide, who had said nothing since noon, finally sat down by the fire and held out his hands to the flames.
"Twenty years I have crossed this river," he said quietly. "It has never once been in a hurry, and neither should we."
Mara laughed despite herself, and even Tobin managed a crooked smile.
By the time the moon cleared the hills, the camp was quiet, and the river kept talking to itself in the dark.
"""

CHAPTER_MIN = 20  # audio minutes in a ~3,000-word web-novel chapter


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("p", "br", "div", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data)


def chapter_text(path):
    with open(path, encoding="utf-8") as f:
        body = json.load(f).get("body") or ""
    parser = _Text()
    parser.feed(body)
    text = html.unescape("".join(parser.parts))
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def split_sentences(text):
    out = []
    for line in text.splitlines():
        out += [s.strip() for s in re.split(r"(?<=[.!?…\"”])\s+", line) if s.strip()]
    return out


def merge(sentences, max_chars):
    chunks, cur = [], ""
    for s in sentences:
        if cur and len(cur) + len(s) + 1 > max_chars:
            chunks.append(cur)
            cur = s
        else:
            cur = f"{cur} {s}".strip()
    if cur:
        chunks.append(cur)
    return chunks


class VramSampler(threading.Thread):
    """Peak GPU memory used on device 0 (whole device, via NVML)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.peak_mb = None
        self._stop = threading.Event()
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._h = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.peak_mb = 0
        except Exception:
            self._nvml = None

    def run(self):
        while self._nvml and not self._stop.is_set():
            used = self._nvml.nvmlDeviceGetMemoryInfo(self._h).used // 2**20
            self.peak_mb = max(self.peak_mb, used)
            time.sleep(0.2)

    def stop(self):
        self._stop.set()


def gpu_info():
    try:
        import pynvml

        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        name = pynvml.nvmlDeviceGetName(h)
        cc = pynvml.nvmlDeviceGetCudaComputeCapability(h)
        mem = pynvml.nvmlDeviceGetMemoryInfo(h)
        drv = pynvml.nvmlSystemGetDriverVersion()
        return f"{name}, sm_{cc[0]}{cc[1]}, {mem.total // 2**20} MiB, driver {drv}"
    except Exception as exc:
        return f"no NVIDIA GPU visible ({exc.__class__.__name__})"


def write_wav(path, pcm16, rate):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)


def projection(name, xrt):
    return (f"  {name:<22} best xRT {xrt:5.2f}  -> {xrt * 60 / CHAPTER_MIN:5.1f} chapters per hour, "
            f"{xrt * 480 / CHAPTER_MIN:5.1f} per 8-hour night")
