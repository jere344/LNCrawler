# Castwright, headless, with its TTS sidecar. NOT part of the lncrawler prod stack.
# Default build (no QWEN): Kokoro-only, no torch / speechbrain, so onnxruntime avoids the
# torch cu128 wheels that dropped Maxwell (GTX 970, sm_52).

ARG CASTWRIGHT_REF=3a52b281fabf1624a6fb39dad3a3d9d03b23d484
# HZ=1 renders Qwen 1.7B through HaujetZhao/Qwen3-TTS-GGUF (hz-gguf) instead of torch.
ARG HZ=0
# Pinned to the commit of the cwbench-lab:hz image's /hz checkout (main).
ARG HZ_REF=74feb581bc8cefb835fc608107e857036d7580a1

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
# A sidecar recycle resumes the chapter, but 3 in 10 minutes held TTS down until a server restart. Grep fails the build if the line moves.
RUN grep -q "RESTART43_STREAK_TRIP_COUNT = 3;" server/dist/tts/sidecar-supervisor.js \
 && sed -i "s/RESTART43_STREAK_TRIP_COUNT = 3;/RESTART43_STREAK_TRIP_COUNT = 30;/" server/dist/tts/sidecar-supervisor.js
RUN npm prune --omit=dev --no-audit --no-fund && npm --prefix server prune --omit=dev --no-audit --no-fund

# --- hz-1: llama.cpp (sm_61) + hz-gguf sources, only built with HZ=1 ----------
# Same llama.cpp build as hz/export/Dockerfile.hz, but just the shared libs the
# sidecar loads. Stub libcuda: there is no driver at build time.
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04 AS hz-1
ARG HZ_REF
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone -q https://github.com/ggml-org/llama.cpp && git -C llama.cpp checkout -q b10621
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 \
 && cmake -S llama.cpp -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -DGGML_NATIVE=OFF \
      -DBUILD_SHARED_LIBS=ON -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
      -DLLAMA_BUILD_SERVER=OFF -DLLAMA_BUILD_TOOLS=ON -DCMAKE_BUILD_TYPE=Release \
      "-DCMAKE_EXE_LINKER_FLAGS=-L/usr/local/cuda/lib64/stubs -Wl,-rpath-link,/usr/local/cuda/lib64/stubs" \
 && cmake --build build -j 10 --target llama
RUN git clone -q https://github.com/HaujetZhao/Qwen3-TTS-GGUF /hz \
 && git -C /hz checkout -q "$HZ_REF" \
 && mkdir -p /hz/qwen3_tts_gguf/inference/bin \
 && cp -a build/bin/*.so* /hz/qwen3_tts_gguf/inference/bin/ \
 && ls -la /hz/qwen3_tts_gguf/inference/bin

# --- hz-0: empty stand-in so the final stage can always COPY from hzsel -------
FROM python:3.12-slim-trixie AS hz-0
RUN mkdir -p /hz/qwen3_tts_gguf/inference/bin

# Selects the hz stage for this build. Only the selected stage is built.
FROM hz-${HZ} AS hzsel

# --- runtime ------------------------------------------------------------------
# trixie: ffmpeg 7.x (Castwright needs >= 6). Python 3.12 is what the sidecar pins.
FROM python:3.12-slim-trixie
# nvidia: swap onnxruntime for onnxruntime-gpu (+ cuDNN/cuBLAS pip wheels, ~2.5 GB).
# cpu: keep plain onnxruntime (smaller image, CPU-only fallback).
ARG ACCEL=nvidia
# QWEN=1 adds Qwen3-TTS for Pascal cards (GTX 1080): torch from the cu126 index
# (cu128 dropped sm_50/sm_61) and an fp32 load (Pascal has no bf16). ~5 GB more.
ARG QWEN=0
ARG HZ=0
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl ca-certificates \
 && if [ "$QWEN" = "1" ]; then apt-get install -y --no-install-recommends sox; fi \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/node /usr/local/bin/node
COPY --from=build /app /app
COPY --from=hzsel /hz/qwen3_tts_gguf /hz/qwen3_tts_gguf

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
# Newer cuDNN wheels (9.19 seen) reject SM < 7.5, which breaks Pascal/Maxwell. LD_LIBRARY_PATH
# makes every venv load this copy, so pin the one torch cu126 ships.
# Castwright's own ORT swap (writes the marker its server checks at boot). It
# only pulls cuDNN/cuBLAS: on Windows the rest ships with torch, which we don't
# install, so the CUDA provider also needs cuRAND here.
RUN if [ "$ACCEL" = "nvidia" ]; then \
      CASTWRIGHT_ACCELERATOR_PROFILE=nvidia node /app/server/tts-sidecar/scripts/install-ort.mjs /opt/venv/bin/python \
      && /opt/venv/bin/pip install --no-cache-dir "nvidia-curand-cu12>=10.3,<10.4" \
      && /opt/venv/bin/pip install --no-cache-dir --no-deps "nvidia-cudnn-cu12==9.10.2.21"; \
    fi \
 && { /opt/venv/bin/pip cache purge >/dev/null 2>&1 || true; }
# The CUDA libs live in pip wheels: put them on the loader path for ORT.
ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.12/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cuda_runtime/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cudnn/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cufft/lib:/opt/venv/lib/python3.12/site-packages/nvidia/curand/lib:/opt/venv/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib:/opt/venv/lib/python3.12/site-packages/nvidia/nvjitlink/lib:/hz/qwen3_tts_gguf/inference/bin:/opt/venv/lib/python3.12/site-packages/nvidia/nccl/lib
RUN bash /app/server/tts-sidecar/scripts/install-kokoro.sh
# HZ=1: hz-gguf for the sidecar's 1.7B tier. Needs QWEN=1 (torch still loads the 0.6B
# voice prompts). The model comes from the cwbench-lab-hz-base volume at /hz/model-base.
COPY hz/hz_backend.py hz/patch_sidecar.py /opt/hz-patch/
RUN if [ "$HZ" = "1" ]; then \
      if [ "$QWEN" != "1" ]; then echo "HZ=1 needs QWEN=1" >&2; exit 1; fi \
      && /opt/venv/bin/pip install --no-cache-dir gguf nvidia-nccl-cu12 \
      && sed -i 's/qwen3_tts_decoder\.fp16\.onnx/qwen3_tts_decoder.fp32.onnx/' /hz/qwen3_tts_gguf/inference/engine.py \
      && sed -i 's/subprocess_decoder=True/subprocess_decoder=False/' /hz/qwen3_tts_gguf/inference/engine.py \
      && grep -q 'qwen3_tts_decoder.fp32.onnx' /hz/qwen3_tts_gguf/inference/engine.py \
      && { ! grep -q 'subprocess_decoder=True' /hz/qwen3_tts_gguf/inference/engine.py; } \
      && cp /opt/hz-patch/hz_backend.py /app/server/tts-sidecar/ \
      && python /opt/hz-patch/patch_sidecar.py /app/server/tts-sidecar/main.py \
      && grep -q 'QWEN_17B_BACKEND' /app/server/tts-sidecar/main.py; \
    fi \
 && rm -rf /opt/hz-patch
# Castwright's Qwen install probe (qwen-install-detect.ts) looks for qwen_tts under server/tts-sidecar/.venv and
# ignores SIDECAR_VENV_DIR, so without this link it reports "not-installed" and renders every Qwen voice in Kokoro.
RUN ln -sfn /opt/venv /app/server/tts-sidecar/.venv
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
