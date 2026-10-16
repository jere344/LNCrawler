/// <reference lib="webworker" />
/**
 * Runs the neural TTS models off the main thread so scrolling and the UI stay
 * smooth while audio is generated. One voice model is kept in memory at a time.
 *
 * Heavy runtime files (ONNX Runtime wasm, the espeak phonemizer and the voice
 * models) are fetched from public CDNs / Hugging Face, never from our server.
 */
import type * as Ort from 'onnxruntime-web';
import type { KokoroTTS } from 'kokoro-js';
import { KOKORO_MODEL_ID, TTS_CACHE_NAME, piperModelUrls, type KokoroDevice } from './voiceCatalog';
import type { WorkerRequest, WorkerResponse } from './workerProtocol';

declare const self: DedicatedWorkerGlobalScope;

// Keep in sync with the exact onnxruntime-web version pinned in package.json.
const ORT_WASM_BASE = 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/';
// espeak-ng phonemizer compiled to wasm (MIT), as used by piper-tts-web.
const PHONEMIZE_JS = 'https://cdn.jsdelivr.net/npm/@mintplex-labs/piper-tts-web@1.0.5/dist/piper-o91UDS6e.js';
const PHONEMIZE_WASM = 'https://cdn.jsdelivr.net/npm/@diffusionstudio/piper-wasm@1.0.0/build/piper_phonemize.wasm';
const PHONEMIZE_DATA = 'https://cdn.jsdelivr.net/npm/@diffusionstudio/piper-wasm@1.0.0/build/piper_phonemize.data';

const post = (msg: WorkerResponse, transfer: Transferable[] = []) => self.postMessage(msg, transfer);

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
    // Threads need cross-origin isolation, which the site doesn't enable.
    ort.env.wasm.numThreads = self.crossOriginIsolated
      ? Math.min(4, navigator.hardwareConcurrency || 1)
      : 1;
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

async function resolveDevice(device: KokoroDevice): Promise<KokoroDevice> {
  if (device !== 'webgpu') return 'wasm';
  const gpu = (navigator as Navigator & { gpu?: { requestAdapter: () => Promise<unknown> } }).gpu;
  try {
    return gpu && (await gpu.requestAdapter()) ? 'webgpu' : 'wasm';
  } catch {
    return 'wasm';
  }
}

async function loadKokoro(requested: KokoroDevice, onProgress?: Progress): Promise<KokoroTTS> {
  const device = await resolveDevice(requested);
  if (kokoro?.device === device) return kokoro.tts;
  // Free the Piper model: only one model lives in memory at a time.
  await piper?.session.release();
  piper = null;

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
    if (engine === 'kokoro') await loadKokoro(req.kokoroDevice, onProgress);
    else await loadPiper(id, onProgress);
    post({ id: req.id, type: 'ready' });
    return;
  }

  const { pcm, sampleRate } = engine === 'kokoro'
    ? await synthKokoro(id, req.text, req.kokoroDevice)
    : await synthPiper(id, req.text);
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
