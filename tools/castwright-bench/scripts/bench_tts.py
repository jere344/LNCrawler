"""Kokoro vs Qwen3-TTS on a real chapter, through Castwright's own sidecar.

Uses the same calls Castwright makes when rendering a book:
  Kokoro       /synthesize, one call per sentence;
  Qwen serial  /synthesize, one call per sentence (designed voice, 0.6B Base clone);
  Qwen batch   /synthesize-batch, N sentences per forward (Castwright's Qwen path).

    docker compose exec castwright /opt/venv/bin/python /bench/bench_tts.py \
        --chapter "/novels/<novel>/<source>/json/00001.json"

Writes a short listening sample per engine to /out/sample-<engine>.wav.
xRT = seconds of audio per second of compute (higher is better, 1 = real time).
"""
import argparse
import json
import time
import urllib.error
import urllib.request

from benchlib import DEFAULT_TEXT, VramSampler, chapter_text, gpu_info, projection, split_sentences, write_wav

SIDECAR = "http://127.0.0.1:9000"
QWEN_VOICE_ID = "bench-narrator"
QWEN_PERSONA = ("A warm, mature male storyteller with a calm, low voice and clear diction, "
                "reading a fantasy novel aloud with gentle, expressive pacing.")
REF_TEXT = ("The old road wound between the hills, and every traveller who walked it "
            "had a story to tell before the night was over.")
REF_WAV, REF_TXT = "/out/qwen-ref.wav", "/out/qwen-ref.txt"


def post(path, body, timeout=1800):
    req = urllib.request.Request(f"{SIDECAR}{path}", data=json.dumps(body).encode(),
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{path} -> HTTP {exc.code}: {exc.read()[:300].decode(errors='replace')}") from None


def pcm_seconds(pcm, rate):
    return len(pcm) / 2 / rate


def synth(engine, model, voice, text):
    pcm, headers = post("/synthesize", {"engine": engine, "model": model, "voice": voice, "text": text})
    return pcm, int(headers.get("X-Sample-Rate") or headers.get("x-sample-rate") or 24000)


def synth_batch(model, voice, texts):
    body, _ = post("/synthesize-batch", {"engine": "qwen", "model": model,
                                         "items": [{"voice": voice, "text": t} for t in texts]})
    header, _, pcm = body.partition(b"\n")
    meta = json.loads(header)
    return pcm, int(meta["sampleRate"]), meta.get("genMs")


class Run:
    def __init__(self, label):
        self.label, self.audio, self.wall, self.calls = label, 0.0, 0.0, 0
        self.sample, self.rate = b"", 24000
        self.vram = VramSampler()

    def __enter__(self):
        self.vram.start()
        self._t0 = time.perf_counter()
        return self

    def add(self, pcm, rate):
        self.audio += pcm_seconds(pcm, rate)
        self.calls += 1
        self.rate = rate
        if len(self.sample) < rate * 2 * 30:  # keep ~30 s for listening
            self.sample += pcm

    def __exit__(self, *exc):
        self.wall = time.perf_counter() - self._t0
        self.vram.stop()

    @property
    def xrt(self):
        return self.audio / self.wall if self.wall else 0.0

    def report(self):
        vram = f"  peak VRAM {self.vram.peak_mb} MiB" if self.vram.peak_mb else ""
        print(f"  {self.label:<26} {self.calls:>4} calls  audio {self.audio:7.1f}s  "
              f"wall {self.wall:7.1f}s  xRT {self.xrt:5.2f}{vram}")

    def save(self, name):
        if not self.sample:
            return
        path = f"/out/sample-{name}.wav"
        write_wav(path, self.sample, self.rate)
        print(f"  listening sample: {path}")


def bench_kokoro(sentences, voice):
    print("Kokoro (kokoro-v1)")
    synth("kokoro", "kokoro-v1", voice, "Warm up.")
    with Run("per-sentence") as run:
        for s in sentences:
            run.add(*synth("kokoro", "kokoro-v1", voice, s))
    run.report()
    run.save("kokoro")
    return run.xrt


def bench_qwen(sentences, model, batch_sizes, serial_n):
    print(f"Qwen3-TTS ({model})")
    t0 = time.perf_counter()
    ref, headers = post("/qwen/design-voice", {"voiceId": QWEN_VOICE_ID, "instruct": QWEN_PERSONA,
                                               "language": "English", "calibrationText": REF_TEXT})
    print(f"  voice design (1.7B, once per character): {time.perf_counter() - t0:.0f}s incl. model load")
    # Same voice for bench_faster.py: its clone takes this audition as reference.
    rate = int(headers.get("X-Sample-Rate") or headers.get("x-sample-rate") or 24000)
    write_wav(REF_WAV, ref, rate)
    with open(REF_TXT, "w", encoding="utf-8") as f:
        f.write(REF_TEXT)
    print(f"  designed voice reference: {REF_WAV}")
    synth("qwen", model, QWEN_VOICE_ID, "Warm up.")

    best = 0.0
    if serial_n:
        with Run("per-sentence") as run:
            for s in sentences[:serial_n]:
                run.add(*synth("qwen", model, QWEN_VOICE_ID, s))
        run.report()
        run.save("qwen")
        best = run.xrt
    for size in batch_sizes:
        with Run(f"batch of {size}") as run:
            for i in range(0, len(sentences), size):
                pcm, rate, _ = synth_batch(model, QWEN_VOICE_ID, sentences[i:i + size])
                run.audio += pcm_seconds(pcm, rate)
                run.calls += 1
                run.rate = rate
                if not run.sample:
                    run.sample = pcm[: rate * 2 * 30]
        run.report()
        if not serial_n:
            run.save("qwen")
        best = max(best, run.xrt)
    return best


def main():
    global SIDECAR
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", help="lncrawler chapter JSON (<source>/json/NNNNN.json)")
    ap.add_argument("--max-sentences", type=int, default=48)
    ap.add_argument("--kokoro-voice", default="af_heart")
    ap.add_argument("--qwen-model", default="qwen3-tts-0.6b", choices=["qwen3-tts-0.6b", "qwen3-tts-1.7b"])
    ap.add_argument("--batch", default="8,16", help="Qwen batch sizes to try, comma-separated ('' to skip)")
    ap.add_argument("--qwen-serial", type=int, default=8, help="sentences for the unbatched Qwen run (0 to skip)")
    ap.add_argument("--skip-kokoro", action="store_true")
    ap.add_argument("--skip-qwen", action="store_true")
    ap.add_argument("--sidecar", default=SIDECAR)
    args = ap.parse_args()
    SIDECAR = args.sidecar.rstrip("/")

    health = json.loads(urllib.request.urlopen(f"{SIDECAR}/health", timeout=30).read())
    text = chapter_text(args.chapter) if args.chapter else DEFAULT_TEXT
    sentences = split_sentences(text)[: args.max_sentences]
    print(f"GPU: {gpu_info()}")
    print(f"sidecar: kokoro device {health.get('devices', {}).get('kokoro')}, "
          f"qwen device {health.get('devices', {}).get('qwen')}")
    print(f"text: {'chapter ' + args.chapter if args.chapter else 'built-in sample'}, "
          f"{len(sentences)} sentences, {sum(map(len, sentences))} chars\n")

    results = {}
    if not args.skip_kokoro:
        try:
            results["Kokoro"] = bench_kokoro(sentences, args.kokoro_voice)
        except Exception as exc:
            print(f"  Kokoro failed: {exc}")
    if not args.skip_qwen:
        sizes = [int(x) for x in args.batch.split(",") if x.strip()]
        try:
            results["Qwen"] = bench_qwen(sentences, args.qwen_model, sizes, args.qwen_serial)
        except Exception as exc:
            print(f"  Qwen failed: {exc}")

    print("\nChapters of ~20 min audio, before Castwright's analysis/export overhead:")
    for name, xrt in results.items():
        if xrt:
            print(projection(name, xrt))


if __name__ == "__main__":
    main()
