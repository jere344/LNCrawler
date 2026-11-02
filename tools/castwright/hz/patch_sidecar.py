"""
patch_sidecar.py - wire hz_backend (hz-gguf, Qwen 1.7B) into the Castwright TTS sidecar.

Run at image build time against the pinned Castwright sources, next to hz_backend.py:

    python patch_sidecar.py [in] [out]

Defaults: in = out = /app/server/tts-sidecar/main.py (in-place).
Every anchor must match exactly once. Any other count (0 = drifted or already
patched, 2+ = ambiguous) exits 1 so the image build fails loudly.
"""
import sys

DEFAULT_PATH = "/app/server/tts-sidecar/main.py"

# (label, anchor, replacement). Anchors are copied verbatim from main.py at 3a52b28.
PATCHES = []


def patch(label, anchor, replacement):
    PATCHES.append((label, anchor, replacement))


# 1. QwenEngine.__init__: create the hz backend when selected.
patch(
    "init: self._hz",
    "        self._base17: Any = None  # resident 1.7B-Base model (fs-55 variant workflow)\n",
    "        self._base17: Any = None  # resident 1.7B-Base model (fs-55 variant workflow)\n"
    "        # hz-gguf 1.7B backend (QWEN_17B_BACKEND=hz). None = torch 1.7B path.\n"
    "        # _hz_swap_lock orders hz loads/unloads against torch Qwen loads.\n"
    "        self._hz_swap_lock = threading.Lock()\n"
    "        self._hz: Any = None\n"
    "        if os.environ.get(\"QWEN_17B_BACKEND\", \"torch\") == \"hz\":\n"
    "            from hz_backend import HzBackend\n"
    "\n"
    "            self._hz = HzBackend()\n",
)

# 2. hz helpers, placed just before _evict_17b_prompt.
patch(
    "methods: _hz_release_for_torch, _hz_prepare, _hz_anchor_path, _hz_voice",
    "    def _evict_17b_prompt(self, voice_id: str) -> None:\n",
    "    def _hz_release_for_torch(self) -> None:\n"
    "        \"\"\"Unload hz before a torch Qwen model loads, so the two never share the\n"
    "        card. No-op unless hz is loaded, so the re-ensure calls that run inside\n"
    "        `_synth_lock` never touch `_hz_swap_lock` while hz is idle.\"\"\"\n"
    "        if self._hz is None or not self._hz.loaded:\n"
    "            return\n"
    "        with self._hz_swap_lock:\n"
    "            self._hz.unload()\n"
    "\n"
    "    def _hz_prepare(self) -> None:\n"
    "        \"\"\"Make the hz engine resident, freeing torch Qwen first. Holds\n"
    "        `_hz_swap_lock` from the free to the load, so no torch load can start\n"
    "        in between. Torch is freed before hz loads, and hz is never unloaded\n"
    "        here. Do not call with `_synth_lock` or `_hz_swap_lock` held. This must\n"
    "        not re-enter `_hz_swap_lock`: unload_base17(release_hz=False) and\n"
    "        unload() only reach hz through hz's own lock.\"\"\"\n"
    "        with self._hz_swap_lock:\n"
    "            if self._hz.loaded:\n"
    "                return\n"
    "            self.unload_base17(release_hz=False)\n"
    "            if self._base is not None:\n"
    "                self.unload()\n"
    "            self._hz.ensure_loaded()\n"
    "\n"
    "    def _hz_anchor_path(self, voice: str) -> str:\n"
    "        \"\"\"Saved hz anchor for a designed voice: `<safe>__hz.hzvoice`, beside the\n"
    "        torch `.pt`. Not `.json`: the voice listing treats every *.json as a voice.\"\"\"\n"
    "        pt_path, _json_path = self._voice_paths(f\"{voice}__hz\")\n"
    "        return os.path.splitext(pt_path)[0] + \".hzvoice\"\n"
    "\n"
    "    def _hz_voice(self, voice: str) -> tuple[Any, str]:\n"
    "        \"\"\"Return (hz voice anchor, manifest language) for a designed voice.\n"
    "\n"
    "        Fails fast like `_load_voice_prompt` (VoiceNotDesignedError) before any\n"
    "        hz load. The anchor is encoded once and saved as `<safe>__hz.hzvoice`.\n"
    "        Its reference clip is the retained master wav when there is one, else the\n"
    "        0.6B prompt's codes decoded by hz's own decoder. ref_text comes from the\n"
    "        0.6B prompt either way.\"\"\"\n"
    "        prompt, _lang, _hit = self._load_voice_prompt(voice)\n"
    "        item = prompt[0] if isinstance(prompt, list) else prompt\n"
    "        ref_text = getattr(item, \"ref_text\", None)\n"
    "        if not ref_text:\n"
    "            raise RuntimeError(f\"voice '{voice}' has no ref_text in its 0.6B prompt; re-design it\")\n"
    "        key = f\"{voice}__hz\"\n"
    "        anchor_path = self._hz_anchor_path(voice)\n"
    "        master = self._voice_master_wav_path(voice)\n"
    "        self._hz_prepare()\n"
    "        made: list[str] = []\n"
    "\n"
    "        def make_ref() -> tuple[str, str]:\n"
    "            if os.path.isfile(master):\n"
    "                return master, ref_text\n"
    "            if item.ref_code is None:\n"
    "                raise RuntimeError(f\"voice '{voice}' has no reference codes to re-encode\")\n"
    "            fd, tmp = tempfile.mkstemp(suffix=\".wav\")\n"
    "            os.close(fd)\n"
    "            made.append(tmp)\n"
    "            self._hz.decode_codes_to_wav(item.ref_code.detach().cpu().numpy(), tmp)\n"
    "            return tmp, ref_text\n"
    "\n"
    "        try:\n"
    "            res = self._hz.get_voice(key, anchor_path, make_ref)\n"
    "        finally:\n"
    "            for path in made:\n"
    "                try:\n"
    "                    os.remove(path)\n"
    "                except OSError:\n"
    "                    pass\n"
    "        return res, self._read_voice_language(voice)\n"
    "\n"
    "    def _evict_17b_prompt(self, voice_id: str) -> None:\n",
)

# 3. _evict_17b_prompt: also drop the hz anchor (memory + file).
patch(
    "evict: hz voice",
    "            log.warning(\"Failed to evict stale 1.7B prompt file %s: %s\", pt_path, e)\n",
    "            log.warning(\"Failed to evict stale 1.7B prompt file %s: %s\", pt_path, e)\n"
    "        if self._hz is not None:\n"
    "            self._hz.evict(f\"{voice_id}__hz\")\n"
    "            _hz_anchor = self._hz_anchor_path(voice_id)\n"
    "            try:\n"
    "                os.remove(_hz_anchor)\n"
    "            except FileNotFoundError:\n"
    "                pass\n"
    "            except OSError as e:\n"
    "                log.warning(\"Failed to evict stale hz voice file %s: %s\", _hz_anchor, e)\n",
)

# 4. unload(): release the hz engine too. Takes only hz's own lock, not
#    _hz_swap_lock, because _hz_prepare calls unload() while holding that lock.
patch(
    "unload: hz",
    "        with self._synth_lock:\n"
    "            had = self._base is not None or self._design is not None\n",
    "        if self._hz is not None:\n"
    "            self._hz.unload()\n"
    "        with self._synth_lock:\n"
    "            had = self._base is not None or self._design is not None\n",
)

# 5. synthesize(): single 1.7B line through hz as a 1-item batch.
patch(
    "synthesize: hz branch",
    "        if model == \"1.7b\":\n"
    "            # ── 1.7B-Base path (fs-55",
    "        if model == \"1.7b\" and self._hz is not None:\n"
    "            # ── 1.7B hz-gguf path (QWEN_17B_BACKEND=hz) ─────────────────────────\n"
    "            voice_res, lang_hz = self._hz_voice(voice)\n"
    "            lang = language or lang_hz\n"
    "            self._hz_prepare()\n"
    "            gen_start = time.perf_counter()\n"
    "            with self._synth_lock:\n"
    "                wavs, sr = self._hz.synth_batch([(text, voice_res, lang)])\n"
    "            gen_ms = (time.perf_counter() - gen_start) * 1000.0\n"
    "            audio = wavs[0]\n"
    "            audio_ms = _audio_duration_ms(audio, sr)\n"
    "            log.info(\n"
    "                \"qwen synth (1.7b hz): voice=%s text_len=%d gen_ms=%.0f audio_ms=%.0f rtf=%.2f\",\n"
    "                voice, len(text), gen_ms, audio_ms,\n"
    "                (gen_ms / audio_ms if audio_ms > 0 else 0.0),\n"
    "            )\n"
    "            return SynthResult(\n"
    "                pcm=_float_audio_to_int16_le(_apply_emotion_gain(audio, voice)), sample_rate=int(sr)\n"
    "            )\n"
    "        if model == \"1.7b\":\n"
    "            # ── 1.7B-Base path (fs-55",
)

# 6. synthesize_batch(): 1.7B tier through hz. Castwright's generation sets live_instruct on EVERY 1.7B batch
#    (synthesise-chapter.ts: `liveInstruct: is17b`), so routing live-instruct to torch sent every real render to the
#    fp32 torch model, which does not fit the 8 GB card next to anything else (CUDA OOM, recycle storm). hz has no
#    instruct input: by default it takes those batches too and drops the per-line instruct phrase (prosody comes
#    from the cloned voice alone, as in the approved hz benchmarks). QWEN_HZ_INSTRUCT=torch restores the old routing.
patch(
    "synthesize_batch: hz branch",
    "        if model == \"1.7b\":\n"
    "            # ── 1.7B-Base batch path (fs-56",
    "        if model == \"1.7b\" and self._hz is not None and (\n"
    "            not live_instruct or os.environ.get(\"QWEN_HZ_INSTRUCT\", \"ignore\").strip().lower() != \"torch\"\n"
    "        ):\n"
    "            if live_instruct and any(item.get(\"instruct\") for item in items):\n"
    "                log.info(\"qwen 1.7b hz: dropping per-line instruct for %d item(s)\", len(items))\n"
    "            # ── 1.7B hz-gguf batch path (QWEN_17B_BACKEND=hz) ───────────────────\n"
    "            # Per-item validation and error text match the torch loops below.\n"
    "            voice_results: list[Any] = []\n"
    "            for i, item in enumerate(items):\n"
    "                voice = item.get(\"voice\")\n"
    "                text = item.get(\"text\")\n"
    "                if not isinstance(voice, str) or not voice:\n"
    "                    raise RuntimeError(f\"batch item {i}: `voice` is required.\")\n"
    "                if not isinstance(text, str) or not text.strip():\n"
    "                    raise RuntimeError(f\"batch item {i}: `text` is required.\")\n"
    "                try:\n"
    "                    voice_res, lang = self._hz_voice(voice)\n"
    "                except RuntimeError as e:\n"
    "                    raise RuntimeError(f\"batch item {i} (voice={voice!r}): {e}\") from e\n"
    "                texts.append(text)\n"
    "                # Per-item language override wins, as on the torch path (#1951).\n"
    "                langs.append(item.get(\"language\") or lang)\n"
    "                voice_results.append(voice_res)\n"
    "            load_ms = (time.perf_counter() - load_start) * 1000.0\n"
    "\n"
    "            # Ensure BEFORE the lock (same rationale as the torch branch).\n"
    "            self._hz_prepare()\n"
    "            gen_start = time.perf_counter()\n"
    "            with self._synth_lock:\n"
    "                wavs, sr = self._hz.synth_batch(list(zip(texts, voice_results, langs)))\n"
    "            gen_ms = (time.perf_counter() - gen_start) * 1000.0\n"
    "        elif model == \"1.7b\":\n"
    "            if self._hz is not None:\n"
    "                log.warning(\n"
    "                    \"qwen 1.7b hz backend has no live-instruct path; this batch runs on torch\"\n"
    "                )\n"
    "            # ── 1.7B-Base batch path (fs-56",
)

# 7. /health: which 1.7B backend is wired (additive key, no protocol bump).
patch(
    "health: qwen17bBackend",
    "        \"qwen_base17_loaded\": qwen_base17_loaded,\n",
    "        \"qwen_base17_loaded\": qwen_base17_loaded,\n"
    "        \"qwen17bBackend\": \"hz\" if isinstance(qwen, QwenEngine) and qwen._hz is not None else \"torch\",\n",
)

# 8-11. Torch Qwen loads release hz first (no co-residency on the card). Each
#        ensure takes only `_cold_load_lock`, never `_synth_lock`, so the release
#        runs before it and outside any synth lock.
patch(
    "ensure: _ensure_base_loaded releases hz",
    "    def _ensure_base_loaded(self, device: Optional[str] = None) -> None:\n",
    "    def _ensure_base_loaded(self, device: Optional[str] = None) -> None:\n"
    "        self._hz_release_for_torch()\n",
)
patch(
    "ensure: _ensure_base17_loaded releases hz",
    "        inside to avoid a second copy.\"\"\"\n"
    "        if self._base17 is not None:\n",
    "        inside to avoid a second copy.\"\"\"\n"
    "        self._hz_release_for_torch()\n"
    "        if self._base17 is not None:\n",
)
patch(
    "ensure: _ensure_base17_for_mint releases hz",
    "        if not _qwen_base17_weights_present():\n",
    "        self._hz_release_for_torch()\n"
    "        if not _qwen_base17_weights_present():\n",
)
patch(
    "ensure: _ensure_design_loaded releases hz",
    "    def _ensure_design_loaded(self, device: Optional[str] = None) -> None:\n",
    "    def _ensure_design_loaded(self, device: Optional[str] = None) -> None:\n"
    "        self._hz_release_for_torch()\n",
)

# 12. unload_base17() (the /unload 1.7b route, Stop) also releases hz. Its
#     `release_hz=False` escape is for _hz_prepare, which already holds the lock.
patch(
    "unload_base17: signature release_hz",
    "        poll_seconds: float = _BASE17_CONTENTION_POLL_S_DEFAULT,\n"
    "    ) -> None:\n",
    "        poll_seconds: float = _BASE17_CONTENTION_POLL_S_DEFAULT,\n"
    "        release_hz: bool = True,\n"
    "    ) -> None:\n",
)
patch(
    "unload_base17: release hz at top",
    "        wedged-looking-but-still-loading base17 rather than race it.\"\"\"\n",
    "        wedged-looking-but-still-loading base17 rather than race it.\"\"\"\n"
    "        if release_hz:\n"
    "            self._hz_release_for_torch()\n",
)

# 13-16. QWEN_DESIGN_SEQUENTIAL: design_voice frees VoiceDesign before it loads
#        the 1.7B-Base. On an 8 GB card at fp32 the two do not fit together. The
#        base is loaded inside `_synth_lock`, so only the lock-free loaders are
#        used there (`_ensure_base_loaded` takes `_cold_load_lock` only). The
#        free is inline: `unload_design()` would take `_synth_lock` again and wait
#        on the design-in-flight flag, which this call holds.

# 13. module flag, computed once: on by default when the hz backend is selected.
patch(
    "module: _QWEN_DESIGN_SEQUENTIAL flag",
    "class QwenEngine(Engine):\n",
    "# Qwen design on a small card: free VoiceDesign before the 1.7B-Base load.\n"
    "# Default on when QWEN_17B_BACKEND=hz (the 8 GB GTX 1080 setup). Set\n"
    "# QWEN_DESIGN_SEQUENTIAL=0 to keep both models resident.\n"
    "_QWEN_DESIGN_SEQUENTIAL = os.environ.get(\n"
    "    \"QWEN_DESIGN_SEQUENTIAL\",\n"
    "    \"1\" if os.environ.get(\"QWEN_17B_BACKEND\", \"torch\") == \"hz\" else \"0\",\n"
    ") == \"1\"\n"
    "\n"
    "\n"
    "class QwenEngine(Engine):\n",
)

# 14. design_voice load block: skip the Base load when sequential.
patch(
    "design_voice: skip base load when sequential",
    "                            self._ensure_design_loaded(device=device)\n"
    "                            self._ensure_base_loaded(device=device)\n",
    "                            self._ensure_design_loaded(device=device)\n"
    "                            if not _QWEN_DESIGN_SEQUENTIAL:\n"
    "                                self._ensure_base_loaded(device=device)\n",
)

# 15. design_voice: the base snapshot and None check wait until the Base is loaded.
patch(
    "design_voice: base snapshot after design when sequential",
    "                            base = self._base\n"
    "                            if base is None:\n"
    "                                raise RuntimeError(\n"
    "                                    \"Qwen Base model was unloaded before this \"\n"
    "                                    \"design could render — reload it and retry.\"\n"
    "                                )\n"
    "                            # 1. design a reference clip from the persona instruction.\n",
    "                            if not _QWEN_DESIGN_SEQUENTIAL:\n"
    "                                base = self._base\n"
    "                                if base is None:\n"
    "                                    raise RuntimeError(\n"
    "                                        \"Qwen Base model was unloaded before this \"\n"
    "                                        \"design could render — reload it and retry.\"\n"
    "                                    )\n"
    "                            # 1. design a reference clip from the persona instruction.\n",
)

# 16. design_voice: after the reference clip, free VoiceDesign and load the Base.
patch(
    "design_voice: free design, load base before distil when sequential",
    "                            ref_audio = ref_wavs[0]\n"
    "\n"
    "                            # 2. distil into a reusable clone prompt on the Base model.\n",
    "                            ref_audio = ref_wavs[0]\n"
    "\n"
    "                            if _QWEN_DESIGN_SEQUENTIAL:\n"
    "                                # The design forward is done. Drop VoiceDesign inline:\n"
    "                                # unload_design() would take _synth_lock, which this block holds.\n"
    "                                design = None\n"
    "                                self._design = None\n"
    "                                gc.collect()\n"
    "                                try:\n"
    "                                    if torch.cuda.is_available():\n"
    "                                        torch.cuda.empty_cache()\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                                _phase(\"loading-base\")\n"
    "                                self._ensure_base_loaded(device=device)\n"
    "                                base = self._base\n"
    "                                if base is None:\n"
    "                                    raise RuntimeError(\"Qwen Base model did not load for this design.\")\n"
    "\n"
    "                            # 2. distil into a reusable clone prompt on the Base model.\n",
)

# 17. design_voice: a resident 0.6B Base (~2.4 GB fp32) cannot sit next to
#     VoiceDesign (~7 GB fp32) on 8 GB. Drop it before the design load. This block
#     runs outside `_synth_lock`, so the drop takes the lock like unload() does
#     (and clears the prompt cache with it). The Base is reloaded after the design
#     forward, before the clone prompt (patch 16).
patch(
    "design_voice: drop resident base before design load when sequential",
    "                        try:\n"
    "                            self._ensure_design_loaded(device=device)\n",
    "                        if _QWEN_DESIGN_SEQUENTIAL:\n"
    "                            with self._synth_lock:\n"
    "                                dropped_base = self._base is not None\n"
    "                                self._base = None\n"
    "                                with self._cache_lock:\n"
    "                                    self._prompt_cache.clear()\n"
    "                            if dropped_base:\n"
    "                                gc.collect()\n"
    "                                try:\n"
    "                                    if torch.cuda.is_available():\n"
    "                                        torch.cuda.empty_cache()\n"
    "                                except Exception:\n"
    "                                    pass\n"
    "                        try:\n"
    "                            self._ensure_design_loaded(device=device)\n",
)

# 18. /qwen/design-voice: the capacity admission (6144 MB for qwen.1.7b.design) runs in the route, BEFORE
#     design_voice() gets to drop the resident Base (patch 17). After the first design of a cast the Base from
#     its clone prompt is resident (~3.7 GB reserved), the evict ladder never evicts the requesting engine, so
#     every later design in the same run failed with noCapacity. When sequential, unload Qwen before admitting.
patch(
    "design route: unload resident qwen before admission when sequential",
    "        # Capacity-aware placement (task 3, vram-aware-placement plan): mirrors\n"
    "        # /qwen/load's admission wrapping (`SEG_CAPACITY_ADMISSION`, default\n"
    "        # ON, opt-out with =0). Held across the (possibly cold) VoiceDesign + Base load AND the\n",
    "        if _QWEN_DESIGN_SEQUENTIAL and (qwen._base is not None or qwen._hz is not None):\n"
    "            await asyncio.to_thread(qwen.unload)\n"
    "        # Capacity-aware placement (task 3, vram-aware-placement plan): mirrors\n"
    "        # /qwen/load's admission wrapping (`SEG_CAPACITY_ADMISSION`, default\n"
    "        # ON, opt-out with =0). Held across the (possibly cold) VoiceDesign + Base load AND the\n",
)

# 19. Kokoro ORT session: cap the CUDA arena. Unpinned, ORT's arena has no limit and grows in powers of two with
#     the variable batch shapes until the card is full; on a 1080 that also drives the Windows desktop, the
#     driver free floor hit 0 MB during a Kokoro-only chapter and the sidecar self-recycled (code 43).
#     KOKORO_ORT_GPU_MEM_MB (default 3072; 0 = no cap; 1536 ran out on a 190-char line) bounds it, and the arena grows by what each request needs.
patch(
    "kokoro: cap the ORT CUDA arena",
    "        if build_providers and hasattr(Kokoro, \"from_session\"):\n"
    "            log.debug(\"Creating ONNX session with providers=%s\", build_providers)\n",
    "        _ort_cap_mb = int(os.environ.get(\"KOKORO_ORT_GPU_MEM_MB\", \"3072\") or 0)\n"
    "        if _ort_cap_mb > 0 and build_providers and \"CUDAExecutionProvider\" in build_providers:\n"
    "            # HEURISTIC + no max workspace: the exhaustive cuDNN conv search asks for workspaces that ran the\n"
    "            # capped arena out of memory on long lines (Conv nodes, bfc_arena).\n"
    "            _cuda_opts = {\"gpu_mem_limit\": str(_ort_cap_mb * 1024 * 1024),\n"
    "                          \"arena_extend_strategy\": \"kSameAsRequested\",\n"
    "                          \"cudnn_conv_algo_search\": \"HEURISTIC\",\n"
    "                          \"cudnn_conv_use_max_workspace\": \"0\"}\n"
    "            provider_options = [\n"
    "                {**(provider_options[i] if provider_options else {}), **_cuda_opts}\n"
    "                if p == \"CUDAExecutionProvider\" else (provider_options[i] if provider_options else {})\n"
    "                for i, p in enumerate(build_providers)\n"
    "            ]\n"
    "        if build_providers and hasattr(Kokoro, \"from_session\"):\n"
    "            log.debug(\"Creating ONNX session with providers=%s\", build_providers)\n",
)


def main(argv):
    src = argv[1] if len(argv) > 1 else DEFAULT_PATH
    dst = argv[2] if len(argv) > 2 else src
    with open(src, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    # Keep the file's own line endings: anchors are written with LF.
    crlf = "\r\n" in text

    def fit(s):
        return s.replace("\n", "\r\n") if crlf else s

    failures = []
    for label, anchor, replacement in PATCHES:
        a, r = fit(anchor), fit(replacement)
        count = text.count(a)
        if count != 1:
            failures.append(f"{label}: anchor matched {count} times (want exactly 1)")
            continue
        text = text.replace(a, r, 1)
        print(f"applied: {label}")
    if failures:
        for f in failures:
            print(f"FAILED: {f}", file=sys.stderr)
        print(f"patch_sidecar: {len(failures)} of {len(PATCHES)} anchor(s) failed; nothing written.",
              file=sys.stderr)
        return 1
    with open(dst, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print(f"patch_sidecar: {len(PATCHES)} patches applied -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
