"""Raw Kokoro speed on this box, outside Castwright: CUDA vs CPU.

Run inside the bench container:
    docker compose exec castwright /opt/venv/bin/python /bench/bench_kokoro.py
    docker compose exec castwright /opt/venv/bin/python /bench/bench_kokoro.py \
        --chapter "/novels/<novel>/<source>/json/00001.json"

Two call shapes are timed:
  per-sentence  one call per sentence, like Castwright does today;
  per-paragraph consecutive sentences merged, the upside of merging
                same-speaker lines later.
xRT = seconds of audio produced per second of compute (higher is better).
"""
import argparse
import time

import onnxruntime as ort
from kokoro_onnx import Kokoro

from benchlib import DEFAULT_TEXT, VramSampler, chapter_text, gpu_info, merge, split_sentences

KOKORO_DIR = "/app/server/tts-sidecar/voices/kokoro"
MODEL = f"{KOKORO_DIR}/kokoro-v1.0.onnx"
VOICES = f"{KOKORO_DIR}/voices-v1.0.bin"


def bench(provider, chunks, voice, label):
    opts = ort.SessionOptions()
    providers = [provider] if provider == "CPUExecutionProvider" else [provider, "CPUExecutionProvider"]
    try:
        sess = ort.InferenceSession(MODEL, sess_options=opts, providers=providers)
    except Exception as exc:
        print(f"  {provider}: session failed: {exc}")
        return None
    active = sess.get_providers()[0]
    if active != provider:
        print(f"  {provider}: NOT active, onnxruntime fell back to {active}")
        return None
    kokoro = Kokoro.from_session(sess, VOICES)
    kokoro.create("Warm up.", voice=voice, speed=1.0, lang="en-us")

    sampler = VramSampler()
    sampler.start()
    audio_s, t0 = 0.0, time.perf_counter()
    for text in chunks:
        try:
            samples, sr = kokoro.create(text, voice=voice, speed=1.0, lang="en-us")
        except Exception as exc:
            # CUDA kernels missing for this GPU arch surface here, not at session creation.
            print(f"  {provider}: synthesis failed: {exc}")
            sampler.stop()
            return None
        audio_s += len(samples) / sr
    wall = time.perf_counter() - t0
    sampler.stop()
    vram = f", peak VRAM {sampler.peak_mb} MiB" if provider != "CPUExecutionProvider" and sampler.peak_mb else ""
    print(f"  {provider:<22} {label:<14} {len(chunks):>4} calls  "
          f"audio {audio_s:7.1f}s  wall {wall:7.1f}s  xRT {audio_s / wall:5.2f}{vram}")
    return audio_s / wall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", help="lncrawler chapter JSON (<source>/json/NNNNN.json)")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--max-sentences", type=int, default=60)
    ap.add_argument("--merge-chars", type=int, default=400)
    ap.add_argument("--providers", default="CUDAExecutionProvider,CPUExecutionProvider")
    args = ap.parse_args()

    if hasattr(ort, "preload_dlls"):
        try:
            ort.preload_dlls()
        except Exception:
            pass

    text = chapter_text(args.chapter) if args.chapter else DEFAULT_TEXT
    sentences = split_sentences(text)[: args.max_sentences]
    paragraphs = merge(sentences, args.merge_chars)

    print(f"onnxruntime {ort.__version__} ({ort.get_device()}), available: {ort.get_available_providers()}")
    print(f"GPU: {gpu_info()}")
    print(f"text: {'chapter ' + args.chapter if args.chapter else 'built-in sample'}, "
          f"{len(sentences)} sentences, {sum(map(len, sentences))} chars, voice {args.voice}\n")

    results = {}
    for provider in args.providers.split(","):
        if provider not in ort.get_available_providers():
            print(f"  {provider}: not available in this onnxruntime build")
            continue
        results[(provider, "sentence")] = bench(provider, sentences, args.voice, "per-sentence")
        results[(provider, "paragraph")] = bench(provider, paragraphs, args.voice, "per-paragraph")

    best = max((v for v in results.values() if v), default=None)
    print()
    if best is None:
        print("VERDICT: nothing ran. Check the errors above.")
        return
    nightly_min = 60
    chapter_audio_min = 20  # ~3,000-word web-novel chapter
    per_night = best * nightly_min / chapter_audio_min
    print(f"Best xRT {best:.2f} -> roughly {per_night:.0f} chapters (~{chapter_audio_min} min each) "
          f"per {nightly_min}-minute window, before Castwright's own overhead.")
    print("VERDICT: " + ("GO" if best >= 3 else "GO, small nightly batch" if best >= 1 else "NO-GO on this path"))


if __name__ == "__main__":
    main()
