#!/bin/sh
# Export HaujetZhao/Qwen3-TTS-GGUF models from the HF cache. Usage: hz_export.sh <base|base_small>
set -e
which=$1
mq=/root/.cache/modelscope/hub/models/Qwen
mkdir -p $mq
for name in Qwen3-TTS-12Hz-1.7B-Base Qwen3-TTS-12Hz-0.6B-Base; do
  snap=$(ls -d /models/hf/hub/models--Qwen--$name/snapshots/* | head -1)
  ln -sfn "$snap" "$mq/$name"
done
cd /hz
sed -i "s/^model = Models\.[a-z_]*/model = Models.$which/" export_config.py
grep -n "^model = " export_config.py
for s in 11-Export-Codec-Encoder 12-Export-Speaker-Encoder 13-Export-Decoder 14-Export-Embeddings 15-Copy-Tokenizer \
         16-Quantize-ONNX-Models 21-Extract-Talker-Weights 22-Prepare-Talker-Tokenizer 23-Convert-Talker-GGUF \
         24-Quantize-Talker-GGUF 31-Extract-Predictor-Weights 32-Prepare-Predictor-Tokenizer \
         33-Convert-Predictor-GGUF 34-Quantize-Predictor-GGUF; do
  echo "== $s"
  # The step's output goes to a log: a pipe into tail would hide the step's exit status.
  if ! /opt/hzx/bin/python $s.py > /tmp/hz-$s.log 2>&1; then
    tail -n 40 /tmp/hz-$s.log
    echo "step $s failed" >&2
    exit 1
  fi
  tail -n 3 /tmp/hz-$s.log
done
ls -la /hz/model-*
