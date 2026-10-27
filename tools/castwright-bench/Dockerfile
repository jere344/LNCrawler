# Castwright, Kokoro-only, headless. Phase 0 bench image: NOT part of the prod stack.
# No torch / Qwen / speechbrain: Kokoro runs on onnxruntime, which avoids the
# torch cu128 wheels that dropped Maxwell (GTX 970, sm_52).

ARG CASTWRIGHT_REF=3a52b281fabf1624a6fb39dad3a3d9d03b23d484

# --- build: frontend + server bundles ---------------------------------------
FROM node:22-trixie-slim AS build
ARG CASTWRIGHT_REF
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN git init -q . \
 && git remote add origin https://github.com/dudarenok-maker/Castwright.git \
 && git fetch -q --depth 1 origin "$CASTWRIGHT_REF" \
 && git checkout -q FETCH_HEAD \
 && rm -rf .git
ENV HUSKY=0 NODE_OPTIONS=--max-old-space-size=3072
RUN npm ci --no-audit --no-fund && npm --prefix server ci --no-audit --no-fund
RUN npm run build
RUN npm prune --omit=dev --no-audit --no-fund && npm --prefix server prune --omit=dev --no-audit --no-fund

# --- runtime ------------------------------------------------------------------
# trixie: ffmpeg 7.x (Castwright needs >= 6). Python 3.12 is what the sidecar pins.
FROM python:3.12-slim-trixie
# nvidia: swap onnxruntime for onnxruntime-gpu (+ cuDNN/cuBLAS pip wheels, ~2.5 GB).
# cpu: keep plain onnxruntime (smaller image, CPU-only fallback).
ARG ACCEL=nvidia
# QWEN=1 adds Qwen3-TTS for Pascal cards (GTX 1080): torch from the cu126 index
# (cu128 dropped sm_50/sm_61) and an fp32 load (Pascal has no bf16). ~5 GB more.
ARG QWEN=0
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
 && if [ "$QWEN" = "1" ]; then apt-get install -y --no-install-recommends sox; fi \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /app /app

ENV SIDECAR_VENV_DIR=/opt/venv
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir \
      "fastapi>=0.140,<0.141" "uvicorn[standard]>=0.51,<0.52" "numpy>=1.26,<3.0" "psutil>=5.9" \
      "huggingface_hub==0.36.2" "kokoro-onnx>=0.5.0,<0.6.0" "nvidia-ml-py>=12.0,<13.0" \
      "faster-whisper>=1.0,<2.0"
# Before the ORT swap: qwen-tts depends on plain onnxruntime and would clobber onnxruntime-gpu.
RUN if [ "$QWEN" = "1" ]; then \
      /opt/venv/bin/pip install --no-cache-dir torch==2.11.0 torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cu126 \
      && /opt/venv/bin/pip install --no-cache-dir qwen-tts==0.1.1 \
      && sed -i 's/common = {"dtype": torch.bfloat16, "low_cpu_mem_usage": False}/common = {"dtype": getattr(torch, os.environ.get("QWEN_DTYPE", "bfloat16")), "low_cpu_mem_usage": False}/' \
           /app/server/tts-sidecar/main.py \
      && grep -q 'QWEN_DTYPE' /app/server/tts-sidecar/main.py; \
    fi
# FASTQWEN=1 adds faster-qwen3-tts (CUDA graphs + static KV cache) in its own
# venv: it needs transformers 5 / huggingface-hub 1.x, which clash with Castwright's pins.
ARG FASTQWEN=0
RUN if [ "$FASTQWEN" = "1" ]; then \
      python -m venv /opt/fq \
      && /opt/fq/bin/pip install --no-cache-dir torch==2.11.0 torchaudio==2.11.0 \
        --index-url https://download.pytorch.org/whl/cu126 \
      && /opt/fq/bin/pip install --no-cache-dir "faster-qwen3-tts==0.5.4"; \
    fi
# Castwright's own ORT swap (writes the marker its server checks at boot). It
# only pulls cuDNN/cuBLAS: on Windows the rest ships with torch, which we don't
# install, so the CUDA provider also needs cuRAND here.
RUN if [ "$ACCEL" = "nvidia" ]; then \
      CASTWRIGHT_ACCELERATOR_PROFILE=nvidia node /app/server/tts-sidecar/scripts/install-ort.mjs /opt/venv/bin/python \
      && /opt/venv/bin/pip install --no-cache-dir "nvidia-curand-cu12>=10.3,<10.4"; \
    fi \
 && /opt/venv/bin/pip cache purge >/dev/null 2>&1 || true
# The CUDA libs live in pip wheels: put them on the loader path for ORT.
ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cufft/lib:/opt/venv/lib/python3.12/site-packages/nvidia/curand/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib:/opt/venv/lib/python3.12/site-packages/nvidia/nvjitlink/lib
RUN bash /app/server/tts-sidecar/scripts/install-kokoro.sh
# Settings come from the environment below; an empty .env silences the boot warning.
RUN touch /app/server/.env

ENV NODE_ENV=production \
    PORT=8080 \
    BIND_HOST=0.0.0.0 \
    LAN_HTTPS=0 \
    WORKSPACE_DIR=/workspace \
    ACCELERATOR=${ACCEL} \
    KOKORO_DEVICE=auto \
    GPU_VRAM_BUDGET=1 \
    GEN_WORKERS=1
WORKDIR /app/server
EXPOSE 8080
CMD ["node", "dist/index.js"]
