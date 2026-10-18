/// <reference lib="webworker" />
/**
 * Runs the neural TTS models off the main thread so scrolling and the UI stay
 * smooth while audio is generated. One engine's model is kept in memory at a
 * time (loading another engine releases the previous one).
 *
 * Heavy runtime files (ONNX Runtime wasm, the espeak phonemizer and the voice
 * models) are fetched from public CDNs / Hugging Face, never from our server.
 */
import type * as Ort from 'onnxruntime-web';
import type { KokoroTTS } from 'kokoro-js';
import {
  KOKORO_MODEL_ID,
  SUPERTONIC_BASE,
  SUPERTONIC_MODELS,
  SUPERTONIC_SIZE_MB,
  TTS_CACHE_NAME,
  piperModelUrls,
  supertonicStyleUrl,
  type KokoroDevice,
  type NeuralOptions,
  type SupertonicDevice,
  type TtsThrottle,
} from './voiceCatalog';
import type { WorkerRequest, WorkerResponse } from './workerProtocol';

declare const self: DedicatedWorkerGlobalScope;

// Keep in sync with the exact onnxruntime-web version pinned in package.json.
const ORT_WASM_BASE = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/';
// espeak-ng phonemizer compiled to wasm (MIT), as used by piper-tts-web.
const PHONEMIZE_JS = 'https://cdn.jsdelivr.net/npm/@mintplex-labs/piper-tts-web@1.0.5/dist/piper-o91UDS6e.js';
const PHONEMIZE_WASM = 'https://cdn.jsdelivr.net/npm/@diffusionstudio/piper-wasm@1.0.0/build/piper_phonemize.wasm';
const PHONEMIZE_DATA = 'https://cdn.jsdelivr.net/npm/@diffusionstudio/piper-wasm@1.0.0/build/piper_phonemize.data';

const post = (msg: WorkerResponse, transfer: Transferable[] = []) => self.postMessage(msg, transfer);

// Threads need cross-origin isolation (COOP/COEP headers, see nginx-proxy);
// Safari doesn't support it, so it falls back to one thread there.
// Phones share their cores with the UI: fewer threads there.
const isMobileWorker = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);
const wasmThreads = () => (self.crossOriginIsolated
  ? Math.min(isMobileWorker ? 2 : 4, navigator.hardwareConcurrency || 1)
  : 1);

// Back-to-back inferences keep a phone's GPU busy and starve the compositor,
// which lags the whole UI. After each run the worker rests for a share of the
// time it took: a duty cycle of 0.5 rests as long as it worked. Audio is
// generated well ahead of playback, so the rest costs latency, not gaps.
const THROTTLE_DUTY: Record<Exclude<TtsThrottle, 'auto'>, number> = { off: 1, balanced: 0.5, saver: 0.33 };
const MAX_REST_MS = 1500;

async function throttled<T>(throttle: TtsThrottle | undefined, work: () => Promise<T>): Promise<T> {
  const mode = !throttle || throttle === 'auto' ? (isMobileWorker ? 'balanced' : 'off') : throttle;
  const duty = THROTTLE_DUTY[mode];
  const start = performance.now();
  const out = await work();
  if (duty < 1) {
    const rest = Math.min(MAX_REST_MS, (performance.now() - start) * (1 - duty) / duty);
    await new Promise(resolve => setTimeout(resolve, rest));
  }
  return out;
}

async function hasWebGpu(): Promise<boolean> {
  const gpu = (navigator as Navigator & { gpu?: { requestAdapter: () => Promise<unknown> } }).gpu;
  try {
    return !!gpu && !!(await gpu.requestAdapter());
  } catch {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Downloads (Cache API, shared with the main thread for listing/deleting)
// ---------------------------------------------------------------------------

type Progress = (loaded: number, total: number) => void;

async function fetchCached(url: string, onProgress?: Progress): Promise<ArrayBuffer> {
  const cache = await caches.open(TTS_CACHE_NAME);
  const hit = await cache.match(url);
  if (hit) return hit.arrayBuffer();

  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`Download failed (${res.status})`);
  const total = Number(res.headers.get('content-length')) || 0;
  const reader = res.body.getReader();
  const parts: Uint8Array[] = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    loaded += value.length;
    onProgress?.(loaded, total || loaded);
  }
  const blob = new Blob(parts as BlobPart[]);
  await cache.put(url, new Response(blob, {
    headers: { 'content-type': 'application/octet-stream', 'content-length': String(blob.size) },
  }));
  return blob.arrayBuffer();
}

// ---------------------------------------------------------------------------
// Piper
// ---------------------------------------------------------------------------

interface PiperConfig {
  audio: { sample_rate: number };
  espeak: { voice: string };
  inference: { noise_scale: number; length_scale: number; noise_w: number };
  num_speakers?: number;
}

interface PhonemizeModule {
  callMain: (args: string[]) => void;
}

let ortPromise: Promise<typeof Ort> | null = null;
const getOrt = () => {
  ortPromise ??= import('onnxruntime-web/wasm').then(mod => {
    const ort = ((mod as unknown as { default?: typeof Ort }).default ?? mod) as typeof Ort;
    ort.env.wasm.wasmPaths = ORT_WASM_BASE;
    ort.env.wasm.numThreads = wasmThreads();
    return ort;
  });
  return ortPromise;
};

// The phonemizer's data file is ~18 MB, so the module is created once and its
// `main` is re-run for every sentence. Output arrives through `print`.
let phonemizer: Promise<PhonemizeModule> | null = null;
let onPhonemes: ((line: string) => void) | null = null;

const getPhonemizer = () => {
  phonemizer ??= (async () => {
    const { createPiperPhonemize } = await import(/* @vite-ignore */ PHONEMIZE_JS);
    return createPiperPhonemize({
      noInitialRun: true,
      noExitRuntime: true,
      print: (line: string) => onPhonemes?.(line),
      printErr: (message: string) => console.warn('[tts] phonemizer:', message),
      locateFile: (file: string) => {
        if (file.endsWith('.wasm')) return PHONEMIZE_WASM;
        if (file.endsWith('.data')) return PHONEMIZE_DATA;
        return file;
      },
    }) as Promise<PhonemizeModule>;
  })();
  phonemizer.catch(() => { phonemizer = null; });
  return phonemizer;
};

async function phonemize(text: string, espeakVoice: string): Promise<number[]> {
  const mod = await getPhonemizer();
  return new Promise<number[]>((resolve, reject) => {
    onPhonemes = line => {
      try {
        resolve(JSON.parse(line).phoneme_ids);
      } catch (err) {
        reject(err);
      }
    };
    try {
      mod.callMain(['-l', espeakVoice, '--input', JSON.stringify([{ text }]), '--espeak_data', '/espeak-ng-data']);
    } catch (err) {
      // A crashed runtime can't be reused: start fresh next time.
      phonemizer = null;
      reject(err);
    }
  }).finally(() => { onPhonemes = null; });
}

interface PiperState {
  id: string;
  session: Ort.InferenceSession;
  config: PiperConfig;
}
let piper: PiperState | null = null;

async function loadPiper(piperId: string, onProgress?: Progress): Promise<PiperState> {
  if (piper?.id === piperId) return piper;
  await releaseOthers('piper');
  const urls = piperModelUrls(piperId);
  const [ort, configBuf, modelBuf] = await Promise.all([
    getOrt(),
    fetchCached(urls.config),
    fetchCached(urls.model, onProgress),
    getPhonemizer(),
  ]);
  const config = JSON.parse(new TextDecoder().decode(configBuf)) as PiperConfig;
  await piper?.session.release();
  piper = null;
  const session = await ort.InferenceSession.create(new Uint8Array(modelBuf), {
    executionProviders: ['wasm'],
  });
  piper = { id: piperId, session, config };
  return piper;
}

async function synthPiper(piperId: string, text: string) {
  const state = await loadPiper(piperId);
  const ort = await getOrt();
  const ids = await phonemize(text, state.config.espeak.voice);
  const { noise_scale, length_scale, noise_w } = state.config.inference;
  const feeds: Record<string, Ort.Tensor> = {
    input: new ort.Tensor('int64', BigInt64Array.from(ids.map(BigInt)), [1, ids.length]),
    input_lengths: new ort.Tensor('int64', BigInt64Array.from([BigInt(ids.length)]), [1]),
    scales: new ort.Tensor('float32', Float32Array.from([noise_scale, length_scale, noise_w]), [3]),
  };
  if ((state.config.num_speakers ?? 1) > 1) {
    feeds.sid = new ort.Tensor('int64', BigInt64Array.from([0n]), [1]);
  }
  const { output } = await state.session.run(feeds);
  return { pcm: output.data as Float32Array, sampleRate: state.config.audio.sample_rate };
}

// ---------------------------------------------------------------------------
// Kokoro
// ---------------------------------------------------------------------------

let kokoro: { device: KokoroDevice; tts: Promise<KokoroTTS> } | null = null;

async function loadKokoro(requested: KokoroDevice, onProgress?: Progress): Promise<KokoroTTS> {
  const device: KokoroDevice = requested === 'webgpu' && (await hasWebGpu()) ? 'webgpu' : 'wasm';
  if (kokoro?.device === device) return kokoro.tts;
  await releaseOthers('kokoro');
  if (kokoro) {
    // Switching device: free the model loaded for the other one.
    const old = kokoro;
    kokoro = null;
    await disposeKokoro(old.tts);
  }

  const files = new Map<string, { loaded: number; total: number }>();
  const tts = import('kokoro-js').then(({ KokoroTTS }) =>
    KokoroTTS.from_pretrained(KOKORO_MODEL_ID, {
      dtype: device === 'webgpu' ? 'fp32' : 'q8',
      device,
      progress_callback: (info: { status: string; file?: string; loaded?: number; total?: number }) => {
        if (info.status !== 'progress' || !info.file) return;
        files.set(info.file, { loaded: info.loaded ?? 0, total: info.total ?? 0 });
        let loaded = 0;
        let total = 0;
        files.forEach(f => { loaded += f.loaded; total += f.total; });
        onProgress?.(loaded, total);
      },
    }),
  );
  kokoro = { device, tts };
  tts.catch(() => { if (kokoro?.tts === tts) kokoro = null; });
  return tts;
}

async function synthKokoro(voice: string, text: string, device: KokoroDevice) {
  const tts = await loadKokoro(device);
  const audio = await tts.generate(text, { voice: voice as never, speed: 1 });
  return { pcm: audio.audio as Float32Array, sampleRate: audio.sampling_rate as number };
}

// ---------------------------------------------------------------------------
// Supertonic 3 (port of the official web example, with typed arrays)
// ---------------------------------------------------------------------------

interface SupertonicCfg {
  ae: { sample_rate: number; base_chunk_size: number };
  ttl: { chunk_compress_factor: number; latent_dim: number };
}

interface SupertonicState {
  device: 'wasm' | 'webgpu';
  ort: typeof Ort;
  cfg: SupertonicCfg;
  indexer: number[];
  dp: Ort.InferenceSession;
  enc: Ort.InferenceSession;
  vec: Ort.InferenceSession;
  voc: Ort.InferenceSession;
  styles: Map<string, { ttl: Ort.Tensor; dp: Ort.Tensor }>;
}

let supertonic: Promise<SupertonicState> | null = null;
let supertonicRequested: SupertonicDevice | null = null;

// The WebGPU build of ONNX Runtime also runs the wasm backend.
let ortGpuPromise: Promise<typeof Ort> | null = null;
const getOrtGpu = () => {
  ortGpuPromise ??= import('onnxruntime-web/webgpu').then(mod => {
    const ort = ((mod as unknown as { default?: typeof Ort }).default ?? mod) as typeof Ort;
    ort.env.wasm.wasmPaths = ORT_WASM_BASE;
    ort.env.wasm.numThreads = wasmThreads();
    return ort;
  });
  return ortGpuPromise;
};

async function createSupertonic(requested: SupertonicDevice, onProgress?: Progress): Promise<SupertonicState> {
  const decode = (buf: ArrayBuffer) => JSON.parse(new TextDecoder().decode(buf));
  const cfg = decode(await fetchCached(`${SUPERTONIC_BASE}/onnx/tts.json`)) as SupertonicCfg;
  const indexer = decode(await fetchCached(`${SUPERTONIC_BASE}/onnx/unicode_indexer.json`)) as number[];
  // The four files download one after another; report one overall progress.
  const total = SUPERTONIC_SIZE_MB * 1e6;
  let done = 0;
  const buffers: ArrayBuffer[] = [];
  for (const name of SUPERTONIC_MODELS) {
    const buf = await fetchCached(`${SUPERTONIC_BASE}/onnx/${name}.onnx`, loaded => onProgress?.(done + loaded, total));
    done += buf.byteLength;
    buffers.push(buf);
  }
  const ort = await getOrtGpu();
  const tryDevice = async (device: 'wasm' | 'webgpu') => {
    const opts: Ort.InferenceSession.SessionOptions = { executionProviders: [device], graphOptimizationLevel: 'all' };
    const sessions: Ort.InferenceSession[] = [];
    try {
      for (const buf of buffers) sessions.push(await ort.InferenceSession.create(new Uint8Array(buf), opts));
    } catch (err) {
      await Promise.all(sessions.map(s => s.release()));
      throw err;
    }
    return sessions;
  };
  let device: 'wasm' | 'webgpu' = requested !== 'wasm' && (await hasWebGpu()) ? 'webgpu' : 'wasm';
  let sessions: Ort.InferenceSession[];
  try {
    sessions = await tryDevice(device);
  } catch (err) {
    if (device !== 'webgpu') throw err;
    console.warn('[tts] Supertonic WebGPU failed, using the CPU:', err);
    device = 'wasm';
    sessions = await tryDevice(device);
  }
  const [dp, enc, vec, voc] = sessions;
  return { device, ort, cfg, indexer, dp, enc, vec, voc, styles: new Map() };
}

async function loadSupertonic(requested: SupertonicDevice, onProgress?: Progress): Promise<SupertonicState> {
  if (supertonic && supertonicRequested === requested) return supertonic;
  await releaseOthers('supertonic');
  if (supertonic) {
    const old = supertonic;
    supertonic = null;
    await old.then(releaseSupertonic, () => undefined);
  }
  supertonicRequested = requested;
  const pending = createSupertonic(requested, onProgress);
  supertonic = pending;
  pending.catch(() => { if (supertonic === pending) supertonic = null; });
  return pending;
}

async function releaseSupertonic(state: SupertonicState) {
  await Promise.all([state.dp, state.enc, state.vec, state.voc].map(s => s.release()));
}

async function supertonicStyle(state: SupertonicState, style: string) {
  const cached = state.styles.get(style);
  if (cached) return cached;
  const json = JSON.parse(new TextDecoder().decode(await fetchCached(supertonicStyleUrl(style))));
  const toTensor = (t: { dims: number[]; data: unknown[] }) =>
    new state.ort.Tensor('float32', Float32Array.from(t.data.flat(Infinity) as number[]), t.dims);
  const tensors = { ttl: toTensor(json.style_ttl), dp: toTensor(json.style_dp) };
  state.styles.set(style, tensors);
  return tensors;
}

// Same normalisation as the official helper.
function supertonicText(text: string, lang: string): string {
  let out = text.normalize('NFKD')
    .replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{1F1E6}-\u{1F1FF}]+/gu, '');
  const replacements: Record<string, string> = {
    '–': '-', '‑': '-', '—': '-', '_': ' ', '\u201C': '"', '\u201D': '"', '\u2018': "'", '\u2019': "'",
    '´': "'", '`': "'", '[': ' ', ']': ' ', '|': ' ', '/': ' ', '#': ' ', '→': ' ', '←': ' ',
  };
  for (const [from, to] of Object.entries(replacements)) out = out.split(from).join(to);
  out = out.replace(/[♥☆♡©\\]/g, '')
    .replace(/ ([,.!?;:'])/g, '$1')
    .replace(/""+/g, '"').replace(/''+/g, "'")
    .replace(/\s+/g, ' ').trim();
  if (!/[.!?;:,'"')\]}…。」』】〉》›»]$/.test(out)) out += '.';
  return `<${lang}>${out}</${lang}>`;
}

// Speed the model was tuned for; the player's speed is applied on playback.
const SUPERTONIC_SPEED = 1.05;

async function synthSupertonic(voice: string, text: string, opts: NeuralOptions) {
  const [lang, styleName] = voice.split(':');
  const state = await loadSupertonic(opts.supertonicDevice);
  const { ort, cfg, indexer } = state;
  const style = await supertonicStyle(state, styleName);

  // One token per code point, as in the reference Python implementation.
  const chars = Array.from(supertonicText(text, lang));
  const ids = new BigInt64Array(chars.length);
  chars.forEach((ch, j) => {
    const cp = ch.codePointAt(0)!;
    ids[j] = BigInt(cp < indexer.length ? indexer[cp] : -1);
  });
  const textIds = new ort.Tensor('int64', ids, [1, ids.length]);
  const textMask = new ort.Tensor('float32', new Float32Array(ids.length).fill(1), [1, 1, ids.length]);

  const { duration } = await state.dp.run({ text_ids: textIds, style_dp: style.dp, text_mask: textMask });
  const seconds = (duration.data as Float32Array)[0] / SUPERTONIC_SPEED;
  const { text_emb } = await state.enc.run({ text_ids: textIds, style_ttl: style.ttl, text_mask: textMask });

  const sampleRate = cfg.ae.sample_rate;
  const chunk = cfg.ae.base_chunk_size * cfg.ttl.chunk_compress_factor;
  const latentLen = Math.max(1, Math.ceil(Math.floor(seconds * sampleRate) / chunk));
  const latentDim = cfg.ttl.latent_dim * cfg.ttl.chunk_compress_factor;
  // Start from Gaussian noise (Box-Muller) and denoise it step by step.
  let latent = new Float32Array(latentDim * latentLen);
  for (let i = 0; i < latent.length; i++) {
    latent[i] = Math.sqrt(-2 * Math.log(Math.max(1e-4, Math.random()))) * Math.cos(2 * Math.PI * Math.random());
  }
  const latentMask = new ort.Tensor('float32', new Float32Array(latentLen).fill(1), [1, 1, latentLen]);
  const steps = Math.round(opts.supertonicSteps);
  const totalStep = new ort.Tensor('float32', Float32Array.of(steps), [1]);
  for (let step = 0; step < steps; step++) {
    const { denoised_latent } = await throttled(opts.throttle, () => state.vec.run({
      noisy_latent: new ort.Tensor('float32', latent, [1, latentDim, latentLen]),
      text_emb,
      style_ttl: style.ttl,
      latent_mask: latentMask,
      text_mask: textMask,
      current_step: new ort.Tensor('float32', Float32Array.of(step), [1]),
      total_step: totalStep,
    }));
    latent = new Float32Array(denoised_latent.data as Float32Array);
  }
  const { wav_tts } = await throttled(opts.throttle, () => state.voc.run({ latent: new ort.Tensor('float32', latent, [1, latentDim, latentLen]) }));
  const pcm = (wav_tts.data as Float32Array).slice(0, Math.floor(seconds * sampleRate));
  return { pcm, sampleRate };
}

/** Free the models of every engine except `keep`. */
async function releaseOthers(keep: 'piper' | 'kokoro' | 'supertonic') {
  if (keep !== 'piper' && piper) {
    const old = piper;
    piper = null;
    await old.session.release();
  }
  if (keep !== 'supertonic' && supertonic) {
    const old = supertonic;
    supertonic = null;
    supertonicRequested = null;
    await old.then(releaseSupertonic, () => undefined);
  }
  if (keep !== 'kokoro' && kokoro) {
    const old = kokoro;
    kokoro = null;
    await disposeKokoro(old.tts);
  }
}

async function disposeKokoro(tts: Promise<KokoroTTS>) {
  await tts.then(t => (t as unknown as { model?: { dispose?: () => Promise<unknown> } }).model?.dispose?.(), () => undefined);
}

// ---------------------------------------------------------------------------
// WAV encoding + message loop
// ---------------------------------------------------------------------------

function encodeWav(pcm: Float32Array, sampleRate: number): ArrayBuffer {
  const buffer = new ArrayBuffer(44 + pcm.length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + pcm.length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, pcm.length * 2, true);
  for (let i = 0; i < pcm.length; i++) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

const splitVoiceId = (voiceId: string) => {
  const sep = voiceId.indexOf(':');
  return { engine: voiceId.slice(0, sep), id: voiceId.slice(sep + 1) };
};

async function handle(req: WorkerRequest) {
  const { engine, id } = splitVoiceId(req.voiceId);
  const onProgress: Progress = (loaded, total) => post({ id: req.id, type: 'progress', loaded, total });

  if (req.type === 'prepare') {
    if (engine === 'supertonic') {
      const state = await loadSupertonic(req.options.supertonicDevice, onProgress);
      await supertonicStyle(state, id.split(':')[1]);
    } else if (engine === 'kokoro') {
      await loadKokoro(req.options.kokoroDevice, onProgress);
    } else {
      await loadPiper(id, onProgress);
    }
    post({ id: req.id, type: 'ready' });
    return;
  }

  const { pcm, sampleRate } = engine === 'supertonic'
    ? await synthSupertonic(id, req.text, req.options)
    : engine === 'kokoro'
      ? await throttled(req.options.throttle, () => synthKokoro(id, req.text, req.options.kokoroDevice))
      : await throttled(req.options.throttle, () => synthPiper(id, req.text));
  const wav = encodeWav(pcm, sampleRate);
  post({ id: req.id, type: 'audio', wav, duration: pcm.length / sampleRate }, [wav]);
}

// Requests run one at a time: the models are not re-entrant and running them
// in parallel would only slow each one down.
let queue: Promise<void> = Promise.resolve();
const cancelled = new Set<number>();

self.onmessage = (event: MessageEvent<WorkerRequest | { type: 'cancel'; ids: number[] }>) => {
  const req = event.data;
  if (req.type === 'cancel') {
    req.ids.forEach(id => cancelled.add(id));
    return;
  }
  queue = queue.then(async () => {
    if (cancelled.delete(req.id)) {
      post({ id: req.id, type: 'error', message: 'cancelled' });
      return;
    }
    try {
      await handle(req);
    } catch (err) {
      post({ id: req.id, type: 'error', message: err instanceof Error ? err.message : String(err) });
    }
  });
};
