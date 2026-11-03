#!/bin/sh
# One native analysis benchmark: the worker's own analysis (analyse_part) on an EPUB, straight on llama-server.
# No Castwright: the LLM is called directly. (Re)start llama-server with the 9B model, free the TTS sidecar's VRAM,
# then run bench_native.py on the EPUB.
#
#   sh bench/run_native.sh <label> <epub>
#
# Needs: the Castwright stack up (tools/castwright), images lncrawler-llama:sm61 and
# lncrawler-audiobook-worker:dev, the llm-models volume. Run from audiobook-worker/.
# LLM_GGUF picks another GGUF in the llm-models volume.
set -eu
LABEL=$1
EPUB=$2
GGUF=${LLM_GGUF:-Qwen3.5-9B-MTP-Q4_K_M.gguf}
NET=lncrawler-cwbench_default
CW=http://127.0.0.1:18080
export MSYS_NO_PATHCONV=1

for e in qwen kokoro; do
  curl -s -X POST -H "Content-Type: application/json" -d "{\"engine\":\"$e\"}" $CW/api/sidecar/unload >/dev/null
done

docker rm -f llama >/dev/null 2>&1 || true
# shellcheck disable=SC2086
docker run -d --name llama --gpus all --network $NET -v llm-models:/models:ro lncrawler-llama:sm61 \
  -m "/models/$GGUF" --alias local -ngl 99 -c 32768 -np 1 -fa auto --jinja \
  --spec-type draft-mtp --reasoning-budget 0 --host 0.0.0.0 --port 8080 >/dev/null

i=0
until docker logs llama 2>&1 | grep -q "listening on http"; do
  i=$((i + 1)); [ $i -gt 90 ] && { docker logs --tail 30 llama; exit 1; }; sleep 2
done
echo "llama up: $(nvidia-smi --query-gpu=memory.used --format=csv,noheader) used"

# llama-server has hung mid-generation (GPU busy, no tokens for an hour). Restart it when a busy slot
# makes no progress for 3 minutes; the worker's LLM client retries the failed call. The slots are read from a
# worker-image container on the llama network.
watchdog() {
  last=""; same=0
  while docker inspect llama >/dev/null 2>&1; do
    sleep 30
    cur=$(docker run --rm --network $NET lncrawler-audiobook-worker:dev python -c "import json,urllib.request as u; s=json.load(u.urlopen('http://llama:8080/slots',timeout=10)); print(';'.join(f\"{x['id']}:{x['is_processing']}:{x.get('next_token',[{}])[0].get('n_decoded')}\" for x in s))" 2>/dev/null) || continue
    case $cur in *True*) ;; *) last=""; same=0; continue ;; esac
    if [ "$cur" = "$last" ]; then same=$((same + 1)); else same=0; last=$cur; fi
    if [ $same -ge 6 ]; then
      echo "watchdog: llama stalled ($cur), restarting $(date +%H:%M:%S)"
      docker restart llama >/dev/null; same=0; last=""
    fi
  done
}
watchdog &
WD=$!
trap 'kill $WD 2>/dev/null' EXIT

docker run --rm --network $NET -v "$(pwd):/src" -w /src lncrawler-audiobook-worker:dev \
  python bench/bench_native.py run --epub "$EPUB" --label "$LABEL" --llm-url http://llama:8080/v1
