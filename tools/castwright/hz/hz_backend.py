"""
hz_backend.py - Qwen3-TTS 1.7B through HaujetZhao/Qwen3-TTS-GGUF (hz-gguf).

Used by the TTS sidecar's QwenEngine when QWEN_17B_BACKEND=hz. Lazy: nothing
is loaded until the first call. One TTSEngine (talker/predictor GGUF on CUDA,
fp32 ONNX decoder in-process), one stream for voice encoding, one BatchRunner
for mixed-voice batches, and a lazily created retry BatchRunner for items that
were cut short. Voice anchors are encoded once and saved as JSON content under
a `.hzvoice` name, so the sidecar's voice listing (which scans *.json) ignores them.
"""
import gc
import logging
import os
import sys
import tempfile
import threading
import types
from typing import Callable, Optional

import numpy as np

SAMPLE_RATE = 24000
log = logging.getLogger("sidecar.hz")

# Language names hz accepts (keys of schema/constants.py LANGUAGE_MAP). Anything
# else goes as "auto": hz's map_language() returns None for it, which means no
# language token in the prompt.
HZ_LANGUAGES = {
    "chinese", "english", "japanese", "korean", "german", "spanish", "french",
    "russian", "italian", "portuguese", "beijing_dialect", "sichuan_dialect",
}

_hz_api = None


def _hz_language(lang: Optional[str]) -> str:
    key = (lang or "").strip().lower().replace(" ", "_")
    return key if key in HZ_LANGUAGES else "auto"


def _import_hz():
    """Import hz's API once. Deferred so importing this module costs nothing."""
    global _hz_api
    if _hz_api is None:
        if "/hz" not in sys.path:
            sys.path.insert(0, "/hz")
        from qwen3_tts_gguf.inference import TTSConfig, TTSEngine, TTSResult
        from qwen3_tts_gguf.inference.batch import BatchRunner
        from qwen3_tts_gguf.inference.schema.constants import map_language
        _hz_api = types.SimpleNamespace(
            TTSConfig=TTSConfig, TTSEngine=TTSEngine, TTSResult=TTSResult,
            BatchRunner=BatchRunner, map_language=map_language,
        )
    return _hz_api


class HzBackend:
    def __init__(self) -> None:
        self.model_dir = os.environ.get("QWEN_HZ_MODEL_DIR", "/hz/model-base/q8")
        self.n_ctx = int(os.environ.get("QWEN_HZ_N_CTX", "768"))
        self.max_steps = int(os.environ.get("QWEN_HZ_MAX_STEPS", "400"))
        # Frames per decoder call. 48 is ~15 s per chapter faster than hz's 12, same WER, no audible difference.
        self.decoder_chunk = int(os.environ.get("QWEN_HZ_DECODER_CHUNK", "48"))
        # Retry settings for items cut short by the first pass (see synth_batch).
        self.retry_n_ctx = int(os.environ.get("QWEN_HZ_RETRY_N_CTX", "2048"))
        self.retry_max_steps = int(os.environ.get("QWEN_HZ_RETRY_MAX_STEPS", "1200"))
        # Re-entrant: get_voice() calls ensure_loaded() and make_ref() may call
        # decode_codes_to_wav(), both of which take the lock again.
        self._lock = threading.RLock()
        self._engine = None
        self._stream = None
        self._runner = None
        self._retry_runner = None
        self._voices: dict = {}

    @property
    def loaded(self) -> bool:
        return self._runner is not None

    def ensure_loaded(self) -> None:
        with self._lock:
            if self.loaded:
                return
            api = _import_hz()
            engine = api.TTSEngine(model_dir=self.model_dir, onnx_provider="CUDA",
                                   chunk_size=self.decoder_chunk,
                                   verbose=False, subprocess_decoder=False)
            if not engine.ready:
                engine.shutdown()
                raise RuntimeError(f"hz-gguf engine not ready (model dir {self.model_dir})")
            stream = engine.create_stream(n_ctx=1024)
            runner = api.BatchRunner(engine, n_ctx_per_seq=self.n_ctx)
            self._engine, self._stream, self._runner = engine, stream, runner

    def unload(self) -> None:
        with self._lock:
            if self._engine is None:
                return
            self._runner = None
            self._retry_runner = None
            self._stream = None
            self._engine.shutdown()
            self._engine = None
            # Engine/stream/context reference cycles hold the llama contexts.
            gc.collect()

    def get_voice(self, key: str, json_path: str,
                  make_ref: Callable[[], tuple]):
        """Return the hz voice anchor (TTSResult) for `key`.

        Order: memory cache, then `json_path` (TTSResult.from_json), then
        make_ref() -> (wav_path, ref_text) encoded with stream.set_voice and
        saved to `json_path` atomically (temp file in the same dir + os.replace).
        """
        with self._lock:
            cached = self._voices.get(key)
            if cached is not None:
                return cached
            self.ensure_loaded()
            if os.path.isfile(json_path):
                res = self._load_json(json_path)
                # The anchor file has no decoder final_state; set_voice pre-decodes
                # the ref codes to rebuild it. Without it every line starts cold (glitches).
                res = self._stream.set_voice(res) if res is not None else None
                if isinstance(res, _import_hz().TTSResult):
                    self._voices[key] = res
                    return res
            wav_path, ref_text = make_ref()
            res = self._stream.set_voice(wav_path, ref_text)
            if not isinstance(res, _import_hz().TTSResult):
                raise RuntimeError(f"hz could not encode voice {key!r} from {wav_path}")
            self._save_json(res, json_path)
            self._voices[key] = res
            return res

    def evict(self, key: str) -> None:
        """Drop the memory entry. The caller deletes the anchor file."""
        with self._lock:
            self._voices.pop(key, None)

    def synth_batch(self, items: list) -> tuple:
        """items: [(text, voice TTSResult, language name)]. Returns
        ([float32 array per item, in order], SAMPLE_RATE). Mixed voices are fine.

        An item is truncated when it hits max_steps or runs out of its per-seq
        context (prompt + frames >= n_ctx - 1). Each truncated item is re-rendered
        alone with the retry runner and the larger retry limits. Still truncated
        after that raises, naming the item."""
        if not items:
            raise RuntimeError("hz synth_batch called with no items.")
        with self._lock:
            self.ensure_loaded()
            api = _import_hz()
            cfg = api.TTSConfig(max_steps=self.max_steps, streaming=False)
            tasks = [(text, voice, _hz_language(lang), False, cfg)
                     for text, voice, lang in items]
            results = self._runner.clone_batch(tasks)
            wavs = []
            for i, (r, (text, voice, lang)) in enumerate(zip(results, items)):
                if r is None:
                    raise RuntimeError(f"hz produced no result for batch item {i}")
                prompt_len = self._prompt_len(self._runner, text, voice, lang)
                if self._is_truncated(r, prompt_len, self.max_steps, self.n_ctx):
                    log.warning(
                        "hz batch item %d truncated (%d frames, prompt %d tokens); "
                        "re-rendering alone with max_steps=%d n_ctx=%d",
                        i, len(r.codes), prompt_len, self.retry_max_steps, self.retry_n_ctx,
                    )
                    r = self._render_retry(text, voice, lang, prompt_len, i)
                audio = r.audio
                if audio is None or len(audio) == 0:
                    raise RuntimeError(f"hz produced no audio for batch item {i}")
                wavs.append(np.asarray(audio, dtype=np.float32))
        return wavs, SAMPLE_RATE

    def _prompt_len(self, runner, text, voice, lang) -> int:
        """Prompt token count hz will use for this item (same prompt clone_batch builds)."""
        api = _import_hz()
        pd = runner.prompt_builder.build_clone_prompt(
            text, voice, api.map_language(_hz_language(lang)), False)
        return int(pd.embd.shape[1])

    def _is_truncated(self, r, prompt_len: int, max_steps: int, n_ctx: int) -> bool:
        frames = len(r.codes)
        return frames >= max_steps or prompt_len + frames >= n_ctx - 1

    def _render_retry(self, text, voice, lang, prompt_len: int, index: int):
        api = _import_hz()
        if self._retry_runner is None:
            self._retry_runner = api.BatchRunner(self._engine, n_ctx_per_seq=self.retry_n_ctx)
        cfg = api.TTSConfig(max_steps=self.retry_max_steps, streaming=False)
        res = self._retry_runner.clone_batch([(text, voice, _hz_language(lang), False, cfg)])[0]
        if res is None or self._is_truncated(res, prompt_len, self.retry_max_steps, self.retry_n_ctx):
            frames = 0 if res is None else len(res.codes)
            raise RuntimeError(
                f"hz batch item {index} still truncated after retry "
                f"({frames} frames, max_steps={self.retry_max_steps}, n_ctx={self.retry_n_ctx})"
            )
        return res

    def decode_codes_to_wav(self, codes, wav_path: str) -> None:
        """Decode a (T, 16) codec array with hz's own ONNX decoder
        (engine.decoder, in-process) and write a 24 kHz wav. Fallback reference
        source for voices that have no master wav."""
        import soundfile as sf
        arr = np.asarray(codes, dtype=np.int64).reshape(-1, 16)
        with self._lock:
            self.ensure_loaded()
            res = self._engine.decoder.decode(arr, task_id="hz_ref", is_final=True, stream=False)
        audio = res.audio
        if audio is None or len(audio) == 0:
            raise RuntimeError("hz decoder returned no audio for reference codes")
        sf.write(wav_path, np.asarray(audio, dtype=np.float32), SAMPLE_RATE)

    @staticmethod
    def _load_json(path: str):
        """Read a saved anchor. Any failure (unreadable, corrupt, bad encoding) is
        logged and returns None, so the caller re-encodes the voice."""
        try:
            res = _import_hz().TTSResult.from_json(path)
        except Exception as e:  # noqa: BLE001 - re-encode instead of failing the render
            log.warning("hz voice anchor unreadable, re-encoding: %s (%s)", path, e)
            return None
        return res if res.is_valid_anchor else None

    @staticmethod
    def _save_json(res, json_path: str) -> None:
        directory = os.path.dirname(os.path.abspath(json_path))
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        os.close(fd)
        try:
            res.save_json(tmp)
            if os.path.getsize(tmp) == 0:
                raise RuntimeError(f"hz voice anchor is not valid, not saved: {json_path}")
            os.replace(tmp, json_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
