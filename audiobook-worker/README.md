# Audiobook worker

The worker side of [docs/audiobook-worker-contract.md](../docs/audiobook-worker-contract.md) (contract v1). It polls
lncrawler for parts. For each part it analyses the EPUB on a local LLM (llama-server, Qwen3.5 9B), has Castwright design
the voices and render the audio, encodes each chapter to Ogg/Opus, checks it and uploads it. How the analysis works:
[docs/analysis.md](docs/analysis.md).

## How it runs in prod

The prod server does not run this stack. Each GPU machine runs its own worker, llama and Castwright, and connects out to
prod over HTTPS. It needs no open port or VPN: prod never connects back, and Castwright stays on loopback because it has
no auth. Images are built on each machine, there is no registry.

On the prod server, once:

1. Set `AUDIOBOOK_ENABLED=True`.
2. Create one token per machine, so each can be revoked alone: `manage.py create_audiobook_worker <username>`.

Then on each GPU machine, clone this repository and follow sections 1 to 5, with `LNCRAWLER_URL` set to the prod API host (`SITE_API_URL`, over HTTPS), not the site host.

Things to know when running several machines:

- **Prod pins each audiobook to the worker that claimed its first part**, because the series memory and voices live on
  that machine. A pin is never released on its own: an admin unpins the audiobook (`unpin_worker` action), which also
  puts its claimed part back in the queue.
- **Keep `WORKER_ID` stable and unique.** An id belongs to the token that first used it. A new id is a new worker, which
  no longer gets its pinned audiobooks.
- **`WORKER_LANGUAGES` defaults to `en`.** Set it to `en,fr` to claim French parts too.
- **To retire a machine**, revoke its token on prod and unpin its audiobooks in the admin, so another worker can take them.

## 1. Prerequisites

- Docker with Compose v2, and an NVIDIA GPU with the NVIDIA container runtime. Check that containers see it:

  ```bash
  docker run --rm --gpus all nvidia/cuda:12.6.3-base-ubuntu24.04 nvidia-smi
  ```

- **GPU build notes.** `llama/Dockerfile` builds llama.cpp for compute capability 6.1 only (`-DCMAKE_CUDA_ARCHITECTURES=61`,
  the GTX 10xx cards, sm_61). A card with a newer capability needs that value changed to its own, and the image tag
  (`lncrawler-llama:sm61`) renamed to match. The Castwright Qwen image is built for Pascal in the same way (see
  [tools/castwright/README.md](../tools/castwright/README.md)).
- A lncrawler stack that this machine can reach, and a worker token: `manage.py create_audiobook_worker <user>` on
  lncrawler.

## 2. One-time model setup

The worker needs two model stores before the first start. Both are outside this project.

1. **The Qwen 1.7B hz export** (Castwright's TTS, the `cwbench-lab-hz-base` volume). Build it once as described in
   [tools/castwright/README.md](../tools/castwright/README.md#one-time-hz-export-qwen-17b). The Castwright Qwen compose
   file mounts it, and `up` fails without it.
2. **The 9B GGUF for the analysis**, into the `llm-models` volume (read only for llama):

   ```bash
   docker volume create llm-models
   docker run --rm -u 0 -v llm-models:/models curlimages/curl -L -o /models/Qwen3.5-9B-MTP-Q4_K_M.gguf \
     https://huggingface.co/unsloth/Qwen3.5-9B-MTP-GGUF/resolve/main/Qwen3.5-9B-MTP-Q4_K_M.gguf
   docker run --rm -v llm-models:/models --entrypoint ls curlimages/curl -la /models
   ```

   To serve another file from the volume, set `LLM_GGUF` in `.env`.

## 3. Configure

```bash
cd audiobook-worker
cp .env.example .env
```

Fill in `LNCRAWLER_URL`, `WORKER_TOKEN` and `WORKER_ID`. The worker starts with these three alone. `.env.example`
lists every other variable with its default and what it does. `.env` is gitignored and holds the token: keep it out of
the repository.

Two settings must agree with what is running. `LLM_IDLE_S` is passed to llama as `--sleep-idle-seconds`, and both read
the same `.env`, so change it there only. `LLM_RESTART_FLAG` is the file the worker writes to restart a stalled llama
server (section 6). Leave it at `/control/restart` unless you change the volume path.

## 4. Start, in order

Castwright first. Its stack creates the network `lncrawler-cwbench_default` and the volume
`lncrawler-cwbench_workspace` that the worker joins:

```bash
cd tools/castwright
docker compose -f docker-compose.yml -f docker-compose.gpu.yml -f docker-compose.qwen.yml up -d
```

Then the worker stack, which also starts llama:

```bash
cd audiobook-worker
docker compose up -d --build
```

The worker is in a different compose project from Castwright, so compose cannot order the two. The worker instead waits
at runtime: it does not claim a part until Castwright and the LLM both answer (section 5).

## 5. Check that it works

- `docker compose ps`: `worker` and `llama` are running, and `llama` turns `healthy` once it has served `/health`. That
  takes up to two minutes after the first start, while the model loads.
- `docker compose logs -f worker`. At start it logs the version, the worker id and the profile. While Castwright or the LLM
  is down it logs `not claiming: ...` every half minute. Once both answer, it logs `part=<id> claimed` for each part.
- Castwright: `curl http://127.0.0.1:18080/api/info` (the host port is `CW_PORT`, loopback only).
- The LLM: `docker compose exec llama curl -fsS http://localhost:8080/health`.
- The worker pings lncrawler every `PING_INTERVAL_S` with its availability. A worker that is not ready says so there.
- Usage per part and kind (prompt and completion tokens, from `DATA_DIR/llm-usage.jsonl`):

  ```bash
  docker compose run --rm worker python -m worker.llm_usage --since 2026-11-01T00:00:00Z
  ```

## 6. Failures, restarts and resuming

- **State.** A part's work is kept in `DATA_DIR/parts/<part_id>/`: `state.json`, `part.epub`, the analysis checkpoint,
  and the encoded chapters until they are uploaded. A part's profile is stored at its first run and reused on resume.
  `state.prune()` deletes the state of parts older than seven days when the worker starts.
- **Stop.** `docker compose stop worker` stops the worker within 10 s and keeps the state, saved per chapter. The part stays claimed by this worker
  on lncrawler, and the next claim returns it. The next start resumes the part at the stage it stopped in. Analysis resumes at the next chapter, and
  generation resumes at the chapters still missing.
- **A failed part.** A retryable failure is reported as such and the worker waits `IDLE_RETRY_S` before it claims
  again. A failure that is not retryable is reported too, and its state is kept: an admin retry on lncrawler reuses
  the analysis and the renders already done.
- **A stalled LLM.** If one call gets no reply within `LLM_TIMEOUT_S` (600 s), llama-server is taken to be stalled. The
  worker writes `/control/restart` (the shared `llm-control` volume). The llama entrypoint sees the file within five
  seconds, stops llama-server (TERM, then KILL after 10 s) and exits. Docker restarts the container
  (`restart: unless-stopped`). The worker waits 16 s for the old server to stop, then up to 180 s for `GET /health` to answer, and sends the same call
  again.
  A second timeout fails the part as retryable. Without a restart flag (`LLM_RESTART_FLAG=`) a timeout fails at once.
- **A looping attribution reply.** A `sentence_attribution` reply that hits its token budget (4096) means the model
  looped. The chunk is split at its middle paragraph and each half is sent again; a single paragraph that still loops
  is left as narration, with a warning. The part goes on.
- **Series file damaged.** A series file that is not valid JSON is moved aside as `*.corrupt-<time>`, and the series
  starts empty for that audiobook.

## 7. What lives where, and what to back up

| Where | What | Back up |
|---|---|---|
| `worker-data` volume, `/data` in the worker (`lncrawler-audiobook-worker_worker-data`) | `series/<audiobook_id>.json`: the series memory, with each character's record and designed voice. `parts/`: per-part state, EPUB, checkpoints and encoded chapters. `llm-usage.jsonl`: the usage log | **Yes, `series/`.** It holds the voice mapping of each series. Losing it means the next parts design voices again, or re-seed from the previous part's Castwright book |
| `lncrawler-cwbench_workspace`, `/workspace` in the worker and Castwright | Castwright's books, rendered audio and voice files | **Yes.** The voices and books. A re-seed reads the previous part's book from here |
| `llm-models` | the GGUF weights | no. Downloadable again |
| `llm-control` | the restart flag, empty between restarts | no |
| `cwbench-lab-hz-base` | the hz export | no. Rebuildable, but slow |

Back up the series memory:

```bash
docker run --rm -v lncrawler-audiobook-worker_worker-data:/data -v "$PWD:/backup" alpine \
  tar czf /backup/worker-series.tgz -C /data series
```

## 8. Upgrades

- Pull the code, then rebuild and restart the worker stack: `docker compose up -d --build`. Rebuild Castwright too if its
  Dockerfile changed. A part in progress resumes after the restart.
- Changes to llama's command, `LLM_GGUF` or `LLM_IDLE_S`: `docker compose up -d llama`.
- The llama image needs a rebuild after its entrypoint changes: `docker compose build llama`.
- This version removes the `llm-proxy` service and the analyzer settings. Run `docker compose up -d --remove-orphans`
  once to remove the old proxy container. Delete the `ANALYZER_*`, `LLM_CLOUDFLARE_*`, `LLM_PROXY_*`, `ANALYSIS_MODE`,
  `ANALYSIS_CHUNK_CHARS`, `SERIES_*` and `LLM_MODEL`/`LLM_API_KEY`/`LLM_OVERRIDES` lines from `.env`: they are ignored now.
- Series files written before this version have no `analysedParts` list. They load as they are.

## Profiles

Prod does not pick the engine. The worker picks it with `WORKER_PROFILE`, stores it in the part state at the first run,
and reuses it on resume, so one part never mixes profiles.

| Profile | Castwright run | What the worker does |
|---|---|---|
| `kokoro` | `kokoro-v1` | no design; characters keep `ttsEngine` unset |
| `qwen-mixed` | `qwen3-tts-1.7b` | the narrator and characters with `lines >= QWEN_MAIN_MIN_LINES` are "main". Unvoiced mains are designed (capped at `QWEN_MAX_DESIGNED`, highest line counts first). A minor with a reusable Qwen voice from an earlier part keeps it. Only unvoiced minors, and mains past the cap, are set to `ttsEngine: kokoro`. A main whose design fails falls back to Kokoro and is listed in the QA. |

Non-English books: Castwright puts every character on Qwen. The worker designs characters with 3+ lines (cap twice
`QWEN_MAX_DESIGNED`). A character whose design is refused is retried once after qwen is unloaded. If a speaking character
still has no voice, its lines go to another character's voice (a warning in the part state). The part fails (not
retryable) only when there is no voice to lend.

Defaults: `QWEN_MAIN_MIN_LINES=8`, `QWEN_MAX_DESIGNED=14`. Kokoro voices only 1–2% of the lines of a part, and a design
costs about 67 s, so only the smallest roles stay on Kokoro.

A male or female character whose voice persona (`voiceStyle`) names no gender gets "A {age} {gender} voice." in front, because the designer otherwise drifts (a soft-spoken male lead came out sounding female). A persona that says
androgynous, gender-neutral, genderless or unisex is kept as written, and so are neutral characters and the narrator.

The narrator's persona is chosen once per series, by one LLM call on the title, synopsis, tags and opening narration of the
first part analysed (`worker/analysis/narrator.py`). A first-person book takes the protagonist's gender; a third-person book
takes a fixed draw from the audiobook id (55% opposite the protagonist, 25% the same, 20% androgynous). If the call fails,
the narrator gets the drawn gender with a plain delivery. A series whose narrator already has a voice keeps it. The persona
is kept for the whole series; to redo it, clear the narrator's `voiceStyle` and `voice` in
`DATA_DIR/series/<audiobook_id>.json`.

## Accuracy

How the attribution is measured, the gold sets and the baselines: [docs/accuracy-benchmark.md](docs/accuracy-benchmark.md).
The bench scripts are in `bench/`.

## Tests

Run in the worker image (ffmpeg and pytest are needed):

```bash
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/src" -w /src lncrawler-audiobook-worker:dev \
  sh -c "pip install -q pytest && python -m pytest -q tests"
```

`tests/fake_prod.py` is an in-memory prod that serves one part from a lncrawler JSON folder:

```bash
python tests/fake_prod.py --chapters-dir <novel-source> --count 3 --port 8765 --token t --profile qwen-mixed
```

It prints state changes and, on complete, writes the received QA to `fake_prod_out/complete.json`.

## Layout

```
worker/
  __main__.py     python -m worker
  main.py         claim loop, heartbeat and ping threads, signals
  pipeline.py     one part, end to end, with resume state
  prod.py         contract client
  castwright.py   Castwright client (REST and SSE)
  casting.py      profile -> cast decisions, contract cast
  audio.py        ffmpeg encode and validate
  qa.py           contract qa report
  state.py        per-part state in DATA_DIR/parts
  config.py       env -> Config
  segment.py      splits a passage into sentence and quote pieces
  epub.py         EPUB chapters (stdlib only)
  llm.py          client for llama-server, with usage records and the restart request
  series.py       series memory in DATA_DIR/series
  llm_usage.py    usage log summary
  analysis/       the analysis: protocol, cast, attribution, one part (run)
llama/            llama-server image and its entrypoint (restart on request)
bench/            analysis benchmark (docs/accuracy-benchmark.md)
docs/             analysis.md, accuracy-benchmark.md
tests/            fake_prod.py and the unit tests
```
