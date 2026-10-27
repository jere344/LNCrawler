# Castwright Phase 0 bench (Kokoro-only)

Go/no-go test of Castwright with Kokoro on the prod box (GTX 970, 4 GB). It answers three questions:

1. Does Docker Desktop hand the GTX 970 to a container, and does onnxruntime-gpu run Kokoro on it (sm_52)?
2. How fast is it: raw Kokoro, then a full cast chapter through Castwright?
3. Does series memory keep the same voices across 3 volumes of one novel?

Castwright is pinned to commit `3a52b28` (see `Dockerfile`). The image has no torch/Qwen: Kokoro runs on onnxruntime.

## Why it can't disturb prod

| | Prod stack | Bench |
|---|---|---|
| Compose project | `lncrawler` (repo root) | `lncrawler-cwbench` (this folder only) |
| Container / network / volume | `lncrawler-*` | `lncrawler-cwbench-castwright-1`, `lncrawler-cwbench_default`, `lncrawler-cwbench_workspace` |
| Novels folder | read-write | mounted **read-only** at `/novels` |
| Port | 80 | `127.0.0.1:18080` only (Castwright has no auth) |
| CPU / RAM | — | capped at 2 CPUs / 3 GB (`CW_CPUS`, `CW_MEM_LIMIT`) |
| GPU | unused | the only user |
| Env | `.env` at repo root | `tools/castwright-bench/.env` |

Rules:
- Always `cd tools/castwright-bench` before any `docker compose` command. Never run these commands from the repo root.
- Never add `--remove-orphans`, and never run `docker system prune` / `docker volume prune` for this.
- Before starting, check the Docker VM has room for the 3 GB cap: `docker info --format "{{.MemTotal}}"` and `docker stats --no-stream`. If the VM is tight, lower `CW_MEM_LIMIT` (2g is enough for Kokoro) or raise the WSL memory in `%UserProfile%\.wslconfig`.
- Run it at a quiet hour: the CPU fallback test does use the 2 CPUs it's given.

## 0. GPU passthrough check (1 minute, ~150 MB pull)

```powershell
docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
```

You should see the GTX 970. If this fails, Docker Desktop's WSL2 backend can't see the GPU (driver, WSL version or Windows Server support). Fix that first, or run everything else with the CPU fallback (`ACCEL=cpu`) to get the CPU numbers.

## 1. Get the image onto the prod box

Disk: ~5 GB for the `nvidia` image (cuDNN/cuBLAS wheels), ~2 GB for `cpu`.

**Option A, build on the dev machine (recommended, the npm build needs ~3 GB RAM):**

```bash
cd tools/castwright-bench
docker compose build
docker save lncrawler-cwbench:nvidia | gzip > cwbench-nvidia.tar.gz
```

Copy `cwbench-nvidia.tar.gz` to the server, then:

```powershell
docker load -i cwbench-nvidia.tar.gz
```

**Option B, build on the server:** `docker compose build` from this folder, at a quiet hour.

## 2. Configure and start

```powershell
cd tools\castwright-bench
copy .env.example .env
```

In `.env`, set:
- `GEMINI_API_KEY` (free key, analysis only);
- `NOVELS_DIR` to the prod Lightnovels folder, e.g. `NOVELS_DIR=D:/lncrawler/Lightnovels`. Use the same path as `LIGHTNOVELS_PATH` in the prod `.env`.

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
docker compose logs -f castwright
```

Wait for the server to say it's listening on 8080, then press Ctrl+C (the container keeps running).

## 3. Raw Kokoro speed

```powershell
docker compose exec castwright /opt/venv/bin/python /bench/bench_kokoro.py
```

The script prints the GPU (should be `sm_52`), times Kokoro on CUDA and on CPU, and ends with a verdict. Look for:
- `CUDAExecutionProvider: NOT active` or `synthesis failed` means onnxruntime-gpu can't run on the 970. Note the error; CPU is then the only path.
- `xRT` = seconds of audio per second of compute. `per-sentence` is how Castwright calls Kokoro today; `per-paragraph` shows what merging lines would gain.

Then run it on a real chapter of an English novel:

```powershell
docker compose exec castwright /opt/venv/bin/python /bench/bench_kokoro.py --chapter "/novels/<novel>/<source>/json/00001.json"
```

## 4. Full pipeline and series memory

Export 3 volumes of 5 chapters from one English novel, as one series:

```powershell
docker compose exec castwright /opt/venv/bin/python /bench/make_volumes.py "/novels/<novel>/<source>" --volumes 3 --chapters 5
```

The EPUBs land in `tools\castwright-bench\out\`. Open `http://localhost:18080` on the server (RDP), or from your PC with `ssh -L 18080:127.0.0.1:18080 <server>`, then:

1. Go through first-run setup. In **Admin → Model Manager**, set the analyzer to **Gemini API** and the voice engine to **Kokoro**. Don't install Qwen, Coqui or Ollama.
2. Import `part1.epub`. Check the confirm screen shows the series name and position 1. Analyse it, cast it with Kokoro voices, and generate **one chapter**. Note the start/end time.
3. While it generates, watch `docker stats lncrawler-cwbench-castwright-1` and `nvidia-smi -l 2` on the host.
4. Import and analyse `part2`, then `part3`, in order. **Don't change any voice by hand.**
5. Check the main characters got the same voices in parts 2 and 3. Raw view:

   ```powershell
   curl http://127.0.0.1:18080/api/library/series-memory
   ```

Record:

| | Value |
|---|---|
| `nvidia-smi` in a container OK? | |
| Kokoro on CUDA active? | |
| Raw xRT CUDA (sentence / paragraph) | |
| Raw xRT CPU (sentence / paragraph) | |
| Pipeline: chapter audio length / generation wall time | |
| Peak VRAM / container RAM | |
| Series memory: carried characters across 3 parts | |

## Qwen3-TTS variant (GTX 1080 PC)

For the personal PC (GTX 1080, 8 GB VRAM, 32 GB RAM), not the prod box. It's the same kit plus:
- torch 2.11 from the **cu126** index (cu128 builds dropped Pascal sm_61);
- Qwen loaded in **fp32** (`QWEN_DTYPE=float32`). Castwright hardcodes bf16, which Pascal doesn't have, so the Dockerfile patches that one line.

It's a separate image (`lncrawler-cwbench:qwen`, ~10 GB) with a `models` volume for the Qwen weights (~5 GB, downloaded on first use). Limits: 16 GB RAM and 6 CPUs, set with `CW_MEM_LIMIT` / `CW_CPUS`.

```powershell
cd tools\castwright-bench
copy .env.example .env      # NOVELS_DIR: a folder with a few lncrawler sources is enough
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml up -d
```

No lncrawler data on the PC? Copy one English source folder (`<novel>\<source>\` with its `json\` and `meta.json`) into a local folder and point `NOVELS_DIR` at it.

Kokoro vs Qwen on a real chapter:

```powershell
docker compose exec castwright /opt/venv/bin/python /bench/bench_tts.py --chapter "/novels/<novel>/<source>/json/00001.json"
```

What it does:
1. Kokoro, one call per sentence.
2. Designs one Qwen narrator voice (1.7B VoiceDesign model, once per character). The first run also downloads the weights.
3. Qwen 0.6B: one call per sentence on 8 sentences, then batches of 8 and 16. Batches are how Castwright renders Qwen.
4. Prints xRT and chapters per hour / per 8-hour night for each engine. It saves `out\sample-kokoro.wav` and `out\sample-qwen.wav` so you can compare quality by ear.

Options:
- `--qwen-model qwen3-tts-1.7b` tries the bigger synthesis model.
- `--batch 4,8,16,32` sweeps batch sizes.
- `--max-sentences 80` gives a longer, steadier measurement.
- `--skip-kokoro` skips the Kokoro run.

How to read it: if Qwen's best batch xRT is **≥ 0.5** (about 12 chapters per 8-hour night), Qwen for the narrator and main characters is realistic on this PC. Below that, keep Qwen for the main characters only and Kokoro for the narrator.

Watch the voice-design step. The 1.7B design model in fp32 is ~7 GB of weights, which is tight on 8 GB. If it fails with an out-of-memory error, note it: design runs once per character, so it can move to the CPU (32 GB RAM) without hurting nightly throughput.

### faster-qwen3-tts (CUDA graphs)

[faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts) records each decode step as a CUDA graph and keeps a static KV cache, so each step launches as one GPU operation instead of hundreds of small ones. That overhead is what Castwright's notes name as Qwen's speed floor. Its own numbers are 2–10× faster than plain qwen-tts, depending on the GPU. It isn't a drop-in replacement and doesn't batch, so the image installs it in its own venv (`/opt/fq`, needs transformers 5) and the bench runs it on its own.

Run it **after** `bench_tts.py`, which saves the designed voice to `out\qwen-ref.wav`. It clones the same voice, so you hear the same narrator:

```powershell
docker compose stop castwright
docker compose run --rm --no-deps castwright /opt/fq/bin/python /bench/bench_faster.py --chapter "/novels/<novel>/<source>/json/00001.json"
```

`stop` frees the GPU: VRAM contention alone inflates timings 3–5×. The bench times two modes:
- `icl`: reference audio and its text in context, which is Castwright's default.
- `xvec`: speaker embedding only. The prompt is shorter, so it's faster, but a little less faithful.

It saves `out\sample-faster-icl.wav` and `out\sample-faster-xvec.wav`. Options: `--model 1.7b` and `--dtype float16` (expected to be slow on Pascal, but it's one flag to confirm).

Compare its xRT with the best `batch of N` line from `bench_tts.py`. If faster-qwen3-tts clearly wins (≥ 2×), it's worth patching Castwright's sidecar to use it for synthesis.

## Known quirks

- The sidecar's `/health` reports `devices_state: "error"` because torch isn't installed (on purpose). Kokoro's own device detection still works. The Castwright UI may show a warning about it.
- These lines in the bench output are harmless on a machine without a GPU: `Failed to create CUDAExecutionProvider` and `fell back to CPUExecutionProvider`. On the 970 they mean onnxruntime-gpu can't use the card.
- Reference point: on the dev box (no GPU, 2-CPU cap), CPU Kokoro gave xRT ≈ 0.7, which is slower than real time. CPU-only only works if the server has many more cores to give it.

## 5. Pause / clean up

Stop, keep data:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml stop
```

Remove everything the bench created (only `lncrawler-cwbench*` objects):

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down -v
docker image rm lncrawler-cwbench:nvidia
docker image rm nvidia/cuda:12.6.3-base-ubuntu24.04
```

Qwen variant on the PC: add `-f docker-compose.qwen.yml` to `down -v` (this also deletes the `models` volume and its weights), then `docker image rm lncrawler-cwbench:qwen`.

`out\` holds only the exported EPUBs and listening samples. Delete it by hand.
