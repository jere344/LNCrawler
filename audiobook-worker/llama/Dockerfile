# llama.cpp server for the local analysis, built for the GTX 1080 (sm_61).
# Same pinned llama.cpp as the hz TTS stage in tools/castwright/Dockerfile. The entrypoint restarts the server when
# the worker asks (see entrypoint.sh).
FROM nvidia/cuda:12.6.3-devel-ubuntu24.04 AS build
ARG LLAMA_REF=b10621
RUN apt-get update && apt-get install -y --no-install-recommends git cmake build-essential ca-certificates \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone -q https://github.com/ggml-org/llama.cpp && git -C llama.cpp checkout -q "$LLAMA_REF"
RUN ln -s /usr/local/cuda/lib64/stubs/libcuda.so /usr/local/cuda/lib64/stubs/libcuda.so.1 \
 && cmake -S llama.cpp -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=61 -DGGML_NATIVE=OFF \
      -DBUILD_SHARED_LIBS=OFF -DLLAMA_CURL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
      -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release \
      "-DCMAKE_EXE_LINKER_FLAGS=-L/usr/local/cuda/lib64/stubs -Wl,-rpath-link,/usr/local/cuda/lib64/stubs" \
 && cmake --build build -j 10 --target llama-server

FROM nvidia/cuda:12.6.3-runtime-ubuntu24.04
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /src/build/bin/llama-server /usr/local/bin/llama-server
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod 0755 /usr/local/bin/entrypoint.sh
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
