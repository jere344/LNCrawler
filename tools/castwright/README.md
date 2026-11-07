# Castwright deployment (TTS sidecar for the audiobook worker)

Castwright is the headless audiobook server, pinned to commit `3a52b28` (see `Dockerfile`), with its TTS sidecar.
The sidecar renders Kokoro, and Qwen3-TTS when the image is built with `QWEN=1`. The 1.7B Qwen tier can render through
hz-gguf (see [Qwen 1.7B via hz-gguf](#qwen-17b-via-hz-gguf)).

The [audiobook worker](../../audiobook-worker/README.md) drives it over HTTP at `http://castwright:8080` on the compose
network. This stack is not part of the lncrawler prod stack. Castwright has no auth, so the host port is bound to
loopback only.

## Prerequisites

- Docker Desktop with the WSL2 backend and an NVIDIA GPU. Check that containers see the GPU:

  ```powershell
  docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
  ```

- The Qwen build is for Pascal (GTX 1080, 8 GB, sm_61). It needs the external `cwbench-lab-hz-base` volume (the 1.7B
  hz export, see below).
- The Kokoro-only build has no torch, so it avoids the cu128 wheels that dropped Maxwell. Whether onnxruntime-gpu runs
  Kokoro on a GTX 970 (sm_52) is not confirmed. `KOKORO_DEVICE=cpu` is the fallback.
- Disk: about 5 GB for the `nvidia` image (cuDNN/cuBLAS wheels), about 10 GB for `qwen`.

## One-time hz export (Qwen 1.7B)

The `cwbench-lab-hz-base` volume already holds the export on the dev PC. Check with:

```powershell
docker run --rm --entrypoint ls cwbench-lab:hz -la /hz/model-base/q8
```

Otherwise, build the lab image and run the export from `tools\castwright`. The lab image needs `lncrawler-cwbench:qwen`
built first.

```powershell
docker build -f hz/export/Dockerfile.hz -t cwbench-lab:hz hz/export
docker run --rm --gpus all -e HF_HOME=/models/hf -v "${PWD}\hz\export:/exp:ro" -v lncrawler-cwbench_models:/models -v cwbench-lab-hz-base:/hz/model-base -v cwbench-lab-hz-small:/hz/model-base-small --entrypoint sh cwbench-lab:hz /exp/hz_export.sh base
docker run --rm -v "${PWD}\hz\export:/exp:ro" -v cwbench-lab-hz-base:/hz/model-base -v cwbench-lab-hz-small:/hz/model-base-small --entrypoint sh cwbench-lab:hz /exp/hz_q8.sh
```

`hz_q8.sh` loops over the 0.6B dir too, so mount that volume as well. `hz_export.sh` writes the fp32 decoder (`qwen3_tts_decoder.fp32.onnx.data`) in its `13` step. If that file is missing afterwards, run `hz/export/hz_decoder.sh` in the same image with the same volumes.

## Build and run

Configure once:

```powershell
cd tools\castwright
copy .env.example .env
```

No API key is needed: the analysis runs in the audiobook worker, on its local LLM. Set the options below in `.env` only if
you want to change them (never the prod `.env`).

Kokoro only:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Qwen, 1.7B through hz (the GTX 1080 setup):

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml build
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml up -d
```

Check the start with `docker compose logs -f castwright`. Wait for the server to say it's listening on 8080, then press
Ctrl+C. The container keeps running.

To build on another machine and copy the image:

```bash
docker save lncrawler-cwbench:qwen | gzip > castwright-qwen.tar.gz
docker load -i castwright-qwen.tar.gz
```

Run the stack before the audiobook worker, so that its network and workspace volume exist.

## Qwen variant

The Qwen build is a separate image (`lncrawler-cwbench:qwen`, ~10 GB) with a `models` volume for the Qwen weights (~5 GB,
downloaded on first use). Limits: 16 GB RAM and 6 CPUs, set with `CW_MEM_LIMIT` / `CW_CPUS`.

- torch 2.11 comes from the **cu126** index (cu128 builds dropped Pascal sm_61).
- Qwen loads in **fp32** (`QWEN_DTYPE=float32`). Castwright hardcodes bf16, which Pascal doesn't have, so the Dockerfile patches that one line.
- The sidecar's `.venv` is a symlink to `/opt/venv`. Castwright's Qwen install probe looks only there. Without the link, every Qwen voice reports not-installed and renders in Kokoro.

## Qwen 1.7B via hz-gguf

The 1.7B tier can render through [HaujetZhao/Qwen3-TTS-GGUF](https://github.com/HaujetZhao/Qwen3-TTS-GGUF) (llama.cpp talker at Q8_0, ONNX codec) instead of torch. Mixed-voice batches go through one `clone_batch` per sidecar batch. The 0.6B tier and voice design still use torch. `hz/hz_backend.py` and `hz/patch_sidecar.py` are copied into the image at build time (`HZ=1`). The export is described above.

**Build and run:** see [Build and run](#build-and-run). The `external` volume must exist before `up`.

Settings (env, or `.env` for compose):

| Variable | Default | Meaning |
|---|---|---|
| `HZ` (build arg) | `1` in the qwen compose file | `0` builds without hz; then also set `QWEN_17B_BACKEND=torch` |
| `QWEN_17B_BACKEND` | `torch` in the sidecar; the qwen compose file sets `hz` | `hz` or `torch`, read by the sidecar at start (no rebuild) |
| `QWEN_HZ_MODEL_DIR` | `/hz/model-base/q8` | Model dir inside the container |
| `QWEN_HZ_N_CTX` | `768` | Context per sequence in a batch |
| `QWEN_HZ_MAX_STEPS` | `400` | Max talker frames per line |
| `QWEN_HZ_RETRY_N_CTX` | `2048` | Context for re-rendering a line that was cut short |
| `QWEN_HZ_RETRY_MAX_STEPS` | `1200` | Upper frame limit for that re-render; see "Exact lines that never end" |
| `QWEN_HZ_DECODER_CHUNK` | `48` | Frames per decoder call; hz's own default is `12`, ~15 s slower per chapter, same quality by ear and WER |
| `SIDECAR_VRAM_FREE_FLOOR_MB` | `50` | Each dip under the floor kills the sidecar. Long hz batches peak with under 100 MB free next to a desktop |
| `KOKORO_DEVICE` | `cpu` with the Qwen file | hz and the Kokoro arena do not fit on 8 GB together. The Kokoro-only stack stays on `auto` |
| `SIDECAR_VRAM_RECYCLE_SOFT_MB` | `8200` | Soft VRAM threshold. The default 7731 sits just under VoiceDesign's ~7.75 GB fp32 peak, and the flag latches until restart, so the next render waited 210 s and was force-recycled |
| `KOKORO_ORT_GPU_MEM_MB` | `3072` | Cap on Kokoro's ONNX Runtime CUDA arena (patch 19). `0` = no cap |
| `QWEN_HZ_INSTRUCT` | `ignore` | `torch` sends live-instruct batches to torch again (patch 6). Passed through by `docker-compose.qwen.yml`, so it can be set in `.env` |
| `SEG_CAPACITY_ADMISSION` | `0` | Castwright's capacity admission is off (see the patch notes) |
| `OPENBLAS_NUM_THREADS` | `1` | hz's per-frame numpy work. More threads fight over the 6 CPUs: 5.7x -> 8.6x realtime with 1 |
| `KOKORO_ORT_THREADS` | `4` | Kokoro's ONNX Runtime threads (patch 20). `0` = ORT's default, which ran CPU Kokoro at 0.69x realtime instead of 2.05x |

**Switch back to torch:** `QWEN_17B_BACKEND=torch`, then `up -d` again. The same image serves both.

Notes: the first 1.7B render frees the torch Base models before it loads hz, and any torch Qwen load (0.6B, 1.7B, VoiceDesign) unloads hz first, so the two never share the card. `/unload` with `1.7b` also unloads hz. Each voice is encoded once and saved as `<voice>__hz.hzvoice` next to its torch prompt (not `.json`, so it is not listed as a voice).

Patches in `hz/patch_sidecar.py` (numbered there, applied at build):
- **6, live instruct:** Castwright sets `liveInstruct` on every 1.7B batch. Sending those to torch meant fp32 torch on every real render, which does not fit the 8 GB card next to anything else (CUDA OOM, recycle storm). hz has no instruct input, so it takes them and drops the per-line instruct phrase; prosody comes from the cloned voice alone. `QWEN_HZ_INSTRUCT=torch` restores the old routing.
- **18, design admission:** with sequential design (on by default with hz, patch 13), Qwen is unloaded before the design route's capacity check. The check used to run first. After the first design of a cast, the Base from its clone prompt stayed resident, so every later design failed with `noCapacity`.
- **19, Kokoro arena:** the ONNX Runtime CUDA arena is capped at `KOKORO_ORT_GPU_MEM_MB`, and cuDNN uses a heuristic conv search with no max workspace. Unbounded, the arena grew with the variable batch shapes until the card was full, the desktop's free VRAM hit 0 MB and the sidecar recycled (code 43). The exhaustive search asked for workspaces that overran a 1536 MB cap on long lines.
- **20, Kokoro threads:** the Kokoro ONNX session gets `KOKORO_ORT_THREADS` intra-op threads (default 4). ORT's default starts one per host core inside the 6-CPU container, and CPU Kokoro ran 3x slower.
- **`SEG_CAPACITY_ADMISSION=0`:** with one card, the sidecar's capacity admission has nothing to choose between and only refuses. It cannot see hz's memory, and its learned VoiceDesign peak (~7.4 GB) never fits beside the Windows desktop. The hard VRAM ceilings and the sequential design patches guard the card instead.
- **Exact lines that never end (`hz/hz_backend.py`, not a patch):** some lines rarely or never reach end of speech, at any temperature: `Failure to complete challenges may result in death.` ended about 1 render in 3, and `Suppressing his` not at all. The runaway is babble, not silence, and it failed the whole chapter while looking like a VRAM recycle storm. A cut-short line now gets a step limit of about 3x its length and 120 s of tries with other endings, then splits in two (twice) with a third of the budget per piece, and finally keeps the start of the runaway, logged at error as `kept the first`. It no longer fails the chapter, and the worst case stays near 6 minutes, under Castwright's 600 s call timeout.

## Settings

Base settings (`.env`):

| Variable | Default | Meaning |
|---|---|---|
| `ACCEL` | `nvidia` | `nvidia` or `cpu`. Changing it needs a rebuild |
| `KOKORO_DEVICE` | `auto` | `auto` or `cpu` (forces the Kokoro CPU path) |
| `CW_PORT` | `18080` | Host port, bound to `127.0.0.1` |
| `CW_MEM_LIMIT` | `3g` (`16g` with qwen) | Container RAM cap |
| `CW_CPUS` | `2` (`6` with qwen) | Container CPU cap |

Pauses between lines: upstream Castwright joins the sentence clips with no gap, so a chapter plays as one breathless
run. `patch_server.mjs` (applied at image build, fails the build if its anchors drift) adds silence after each clip
except the last. The worker ends the last sentence of each paragraph with `"\n"`, which Castwright trims before TTS.
The analysis cache's inline-emotion pass also trims it, so that pass is patched to keep it.

| Variable | Default | Silence after a clip that |
|---|---|---|
| `CW_PAUSE_PARAGRAPH_S` | `0.6` | ends a paragraph |
| `CW_PAUSE_SENTENCE_S` | `0.3` | ends with `.` `!` `?` `…` (closing quotes ignored) |
| `CW_PAUSE_CLAUSE_S` | `0.12` | ends any other way (`"Hi,"` before `he said.`) |

Set them in the container's `environment:` to override. Segment times exclude the gap.

## Why these choices

Numbers are from the GTX 1080 (8 GB).
- **hz-gguf for the 1.7B tier:** 1.7B Q8_0 mixed-voice batches of 32 gave xRT 6.38 (~153 chapters per 8-hour night, 6.2 GB peak). Torch 1.7B in fp32 gave 0.15–0.6 and spilled past 8 GB. Castwright's old path (plain qwen-tts 0.6B fp32, batch 4) gave 0.83. Every 1.7B voice sounded slightly better than every 0.6B, so speed decided.
- **Big batches are the speed:** hz line by line gave 1.56, so the sidecar batches many lines of mixed voices into one `clone_batch`.
- **Q8_0 over Q5_K:** Q5_K was only about 1% faster (6.44 vs 6.38), so the Q8_0 talker is the pick.
- **Decoder chunk 48 vs hz's 12:** fewer decoder calls per chapter, with the same quality by ear and WER. 96 or 400 saved only ~5% more.
- **Speed pass (2026-11-04), same audio:** on one real chapter (114 Qwen lines, 4 voices) hz went from 108 s to 64.5 s
  (5.7x -> 9.45x realtime): one OpenBLAS thread (the big one), fixed batches of 32, and hz's decoder ONNX session on
  `kSameAsRequested` (Dockerfile; lower peak in a one-chapter run). Fixed batches of 32 (`QWEN_BATCH_TOKEN_BUDGET_17B=0`,
  +7%) were reverted: hz reserves 768 context tokens per line, so 32 long lines hold ~2.8 GB of KV where the token
  budget kept them at 12-18. On long chapters the card hit the free floor every 3-4 batches, and a chapter with two
  recycles fails. Tried and dropped: a
  vectorised top-k sampler (-5%, most of `pred_sample` is the GPU sync) and decoding finished lines on a thread
  during the frame loop (no gain, the GPU is already busy, +0.8 GB peak). Profile per batch: the code predictor is
  ~60% of the loop, the decoder ~30% of a batch, the talker ~10%.
- **fp32 on Pascal:** fp16 runs at 1/64 of the rate and segfaults, and the fp16 ONNX decoder has no cuDNN plan (it falls back to CPU silently). So the Qwen load and the decoder are fp32.
- **Sequential voice design on 8 GB:** the 1.7B VoiceDesign and the 0.6B Base can't sit on the card together (OOM at design). The sidecar unloads Qwen before each design. Design runs once per character, so this costs no nightly throughput.

## Known quirks

- **hz can still fill the 8 GB card.** On the GTX 1080 next to a desktop, memory peaks near 8 GB and the sidecar recycles about once per chapter (exit code 43). The chapter resumes from its finished groups and the part passes QA. Castwright would hold TTS down after 3 of these in 10 minutes, so the Dockerfile raises that limit to 30.
- The sidecar's `/health` reports `devices_state: "error"` because torch isn't installed (on purpose). Kokoro's own device detection still works. The Castwright UI may show a warning about it.
- `Failed to create CUDAExecutionProvider` and `fell back to CPUExecutionProvider` in the logs are harmless on a machine without a GPU. On a GPU box they mean onnxruntime-gpu can't use the card.
- CPU-only Kokoro is slower than real time on a 2-CPU cap (xRT ≈ 0.7 on the dev box, no GPU). CPU-only needs a server with many more cores.
- The image pins nvidia-cudnn-cu12 9.10.2 because newer cuDNN rejects SM < 7.5 (Pascal/Maxwell).

## How the worker connects

- The project name `lncrawler-cwbench` and the names of the network (`lncrawler-cwbench_default`), the volumes (`lncrawler-cwbench_workspace`, `lncrawler-cwbench_models`) and the images keep the old `cwbench` prefix on purpose. Renaming them would orphan the existing network and volumes.
- The audiobook worker's compose file joins `lncrawler-cwbench_default` and mounts `lncrawler-cwbench_workspace` as external volumes. This stack must be up first.
- The worker reaches Castwright at `http://castwright:8080` on that network. The host port is for local checks only.
- Castwright's own analyzer is not used. The worker analyses the books on its local LLM and writes the cast and the sentences into the Castwright book, so no analyzer key or endpoint is set here.
- The service restarts with `unless-stopped` and has a healthcheck on `/api/info` (`docker compose ps` shows it). The worker does not depend on the check: it waits until Castwright answers before it claims a part.

## Stop and clean up

Stop, keep data:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml stop
```

`down -v` deletes the `workspace` volume (and the `models` weights, when run with the qwen file). The external
`cwbench-lab-hz-base` export is not touched. Don't run `docker volume prune` for this stack.

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml down -v
docker image rm lncrawler-cwbench:qwen
```
