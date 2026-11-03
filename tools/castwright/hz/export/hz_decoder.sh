#!/bin/sh
# Re-exports the fp32 ONNX decoder (fp16 convs have no cuDNN plan on Pascal) for each model dir that lacks it,
# e.g. when the quantize step removed its external data. Run in the cwbench-lab:hz image with the model volumes.
set -e
mq=/root/.cache/modelscope/hub/models/Qwen
mkdir -p $mq
for name in Qwen3-TTS-12Hz-1.7B-Base Qwen3-TTS-12Hz-0.6B-Base; do
  ln -sfn "$(ls -d /models/hf/hub/models--Qwen--$name/snapshots/* | head -1)" "$mq/$name"
done
cd /hz
for pair in "base:/hz/model-base" "base_small:/hz/model-base-small"; do
  which=${pair%%:*}; dir=${pair#*:}
  if [ ! -f "$dir/qwen3_tts_decoder.fp32.onnx.data" ]; then
    sed -i "s/^model = Models\.[a-z_]*/model = Models.$which/" export_config.py
    /opt/hzx/bin/python 13-Export-Decoder.py 2>&1 | tail -1
  fi
done
