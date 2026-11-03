#!/bin/sh
# Make <model dir>/q8: same files, but the talker quantized to q8_0 under the q5_k name the engine hardcodes.
set -e
for dir in /hz/model-base /hz/model-base-small; do
  [ -f $dir/qwen3_tts_talker.q8_0.gguf ] || \
    /hz/qwen3_tts_gguf/inference/bin/llama-quantize $dir/qwen3_tts_talker.f16.gguf $dir/qwen3_tts_talker.q8_0.gguf q8_0 2>&1 | tail -2
  mkdir -p $dir/q8
  for f in $dir/*; do
    [ -e "$f" ] && [ "$(basename $f)" != q8 ] && ln -sfn "$f" "$dir/q8/$(basename $f)"
  done
  ln -sfn $dir/qwen3_tts_talker.q8_0.gguf $dir/q8/qwen3_tts_talker.q5_k.gguf
  ls -la $dir/q8 | grep talker
done
