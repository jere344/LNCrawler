"""faster-qwen3-tts (CUDA graphs + static KV cache) on the same chapter and voice.

Runs in its own venv (/opt/fq) and its own one-off container, with the
Castwright container stopped so this run has the whole GPU:

    docker compose stop castwright
    docker compose run --rm --no-deps castwright /opt/fq/bin/python /bench/bench_faster.py \
        --chapter "/novels/<novel>/<source>/json/00001.json"

Clones the voice bench_tts.py designed (/out/qwen-ref.wav + .txt), so run that first.
Modes: icl (reference audio + text in context, Castwright's default) and
xvec (speaker embedding only: shorter prompt, faster, a bit less faithful).
"""
import argparse
import os
import time

import numpy as np
import torch
from faster_qwen3_tts import FasterQwen3TTS

from benchlib import DEFAULT_TEXT, chapter_text, gpu_info, projection, split_sentences, write_wav

MODELS = {"0.6b": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "1.7b": "Qwen/Qwen3-TTS-12Hz-1.7B-Base"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapter", help="lncrawler chapter JSON (<source>/json/NNNNN.json)")
    ap.add_argument("--max-sentences", type=int, default=48)
    ap.add_argument("--model", default="0.6b", choices=sorted(MODELS))
    ap.add_argument("--dtype", default="float32", choices=["float32", "float16", "bfloat16"],
                    help="float32 on Pascal (no bf16, fp16 at 1/64 speed)")
    ap.add_argument("--modes", default="icl,xvec")
    ap.add_argument("--ref-audio", default="/out/qwen-ref.wav")
    ap.add_argument("--ref-text-file", default="/out/qwen-ref.txt")
    args = ap.parse_args()

    if not (os.path.exists(args.ref_audio) and os.path.exists(args.ref_text_file)):
        raise SystemExit(f"No reference voice at {args.ref_audio}: run bench_tts.py first "
                         "(it designs the voice), or pass --ref-audio / --ref-text-file.")
    ref_text = open(args.ref_text_file, encoding="utf-8").read().strip()
    text = chapter_text(args.chapter) if args.chapter else DEFAULT_TEXT
    sentences = split_sentences(text)[: args.max_sentences]
    print(f"GPU: {gpu_info()}  torch {torch.__version__}, cuda available {torch.cuda.is_available()}")
    print(f"text: {len(sentences)} sentences, {sum(map(len, sentences))} chars; "
          f"model {MODELS[args.model]} {args.dtype}\n")

    t0 = time.perf_counter()
    model = FasterQwen3TTS.from_pretrained(MODELS[args.model], device="cuda",
                                           dtype=getattr(torch, args.dtype))
    print(f"  load: {time.perf_counter() - t0:.0f}s")
    t0 = time.perf_counter()
    model.warmup(prefill_len=100)
    print(f"  warmup (CUDA graph capture): {time.perf_counter() - t0:.0f}s")

    results = {}
    for mode in [m.strip() for m in args.modes.split(",") if m.strip()]:
        xvec = mode == "xvec"
        model.generate_voice_clone(text="Warm up.", language="English", ref_audio=args.ref_audio,
                                   ref_text=ref_text, xvec_only=xvec)
        torch.cuda.reset_peak_memory_stats()
        audio_s, sample, sr = 0.0, [], 24000
        t0 = time.perf_counter()
        for s in sentences:
            wavs, sr = model.generate_voice_clone(text=s, language="English", ref_audio=args.ref_audio,
                                                  ref_text=ref_text, xvec_only=xvec)
            a = np.concatenate([np.asarray(w, dtype=np.float32).reshape(-1) for w in wavs])
            audio_s += len(a) / sr
            if sum(map(len, sample)) < sr * 30:
                sample.append(a)
        wall = time.perf_counter() - t0
        peak = torch.cuda.max_memory_allocated() // 2**20
        xrt = audio_s / wall
        results[f"faster-qwen3 {mode}"] = xrt
        print(f"  {mode:<5} per-sentence {len(sentences):>4} calls  audio {audio_s:7.1f}s  "
              f"wall {wall:7.1f}s  xRT {xrt:5.2f}  peak torch VRAM {peak} MiB")
        pcm = (np.clip(np.concatenate(sample), -1, 1) * 32767).astype("<i2").tobytes()
        path = f"/out/sample-faster-{mode}.wav"
        write_wav(path, pcm, sr)
        print(f"  listening sample: {path}")

    print("\nChapters of ~20 min audio, before Castwright's analysis/export overhead:")
    for name, xrt in results.items():
        print(projection(name, xrt))


if __name__ == "__main__":
    main()
