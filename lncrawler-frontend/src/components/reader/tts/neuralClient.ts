/**
 * Main-thread side of the neural TTS worker, plus helpers to inspect and
 * delete the downloaded voice models.
 */
import {
  KOKORO_MODEL_ID,
  SUPERTONIC_BASE,
  TTS_CACHE_NAME,
  getNeuralVoice,
  kokoroModelUrl,
  piperModelUrls,
  supertonicFileUrls,
  type NeuralOptions,
} from './voiceCatalog';
import type { WorkerRequest, WorkerResponse } from './workerProtocol';

const TRANSFORMERS_CACHE = 'transformers-cache';
const KOKORO_VOICES_CACHE = 'kokoro-voices';

type Pending = {
  resolve: (msg: WorkerResponse) => void;
  reject: (err: Error) => void;
  onProgress?: (loaded: number, total: number) => void;
};

let worker: Worker | null = null;
let nextId = 1;
const pending = new Map<number, Pending>();

export const isNeuralSupported = (): boolean =>
  typeof Worker !== 'undefined' && typeof WebAssembly !== 'undefined' && typeof caches !== 'undefined';

function getWorker(): Worker {
  if (worker) return worker;
  worker = new Worker(new URL('./tts.worker.ts', import.meta.url), { type: 'module' });
  worker.onmessage = (event: MessageEvent<WorkerResponse>) => {
    const msg = event.data;
    const entry = pending.get(msg.id);
    if (!entry) return;
    if (msg.type === 'progress') {
      entry.onProgress?.(msg.loaded, msg.total);
      return;
    }
    pending.delete(msg.id);
    if (msg.type === 'error') entry.reject(new Error(msg.message));
    else entry.resolve(msg);
  };
  worker.onerror = event => {
    const err = new Error(event.message || 'TTS worker crashed');
    pending.forEach(p => p.reject(err));
    pending.clear();
    worker?.terminate();
    worker = null;
  };
  return worker;
}

type RequestBody = WorkerRequest extends infer R ? R extends WorkerRequest ? Omit<R, 'id'> : never : never;

function request(
  req: RequestBody,
  onProgress?: (loaded: number, total: number) => void,
): { id: number; promise: Promise<WorkerResponse> } {
  const id = nextId++;
  const promise = new Promise<WorkerResponse>((resolve, reject) => {
    pending.set(id, { resolve, reject, onProgress });
  });
  getWorker().postMessage({ ...req, id } as WorkerRequest);
  return { id, promise };
}

/** Download (if needed) and load a voice model, reporting download progress. */
export async function prepareVoice(
  voiceId: string,
  options: NeuralOptions,
  onProgress?: (loaded: number, total: number) => void,
): Promise<void> {
  // Ask the browser not to evict the models under storage pressure.
  navigator.storage?.persist?.().catch(() => undefined);
  await request({ type: 'prepare', voiceId, options }, onProgress).promise;
}

export interface SynthJob {
  id: number;
  promise: Promise<{ wav: ArrayBuffer; duration: number }>;
}

/**
 * Object URL for a 16-bit mono WAV, with `volume` applied to the samples.
 * iOS ignores `HTMLMediaElement.volume`, so volume has to be baked in.
 */
export function wavToUrl(wav: ArrayBuffer, volume: number): string {
  let data = wav;
  if (volume < 0.999) {
    data = wav.slice(0);
    const samples = new Int16Array(data, 44);
    for (let i = 0; i < samples.length; i++) samples[i] = Math.round(samples[i] * volume);
  }
  return URL.createObjectURL(new Blob([data], { type: 'audio/wav' }));
}

/** Queue synthesis of `text`; resolves to a WAV file. */
export function synthesize(voiceId: string, options: NeuralOptions, text: string): SynthJob {
  const { id, promise } = request({ type: 'synth', voiceId, options, text });
  return {
    id,
    promise: promise.then(msg => {
      if (msg.type !== 'audio') throw new Error('Unexpected worker response');
      return { wav: msg.wav, duration: msg.duration };
    }),
  };
}

/** Drop queued synthesis jobs that haven't started yet. */
export function cancelJobs(ids: number[]): void {
  if (worker && ids.length) worker.postMessage({ type: 'cancel', ids });
}

// ---------------------------------------------------------------------------
// Storage management
// ---------------------------------------------------------------------------

const cacheHas = async (cacheName: string, url: string) => {
  try {
    const cache = await caches.open(cacheName);
    return !!(await cache.match(url));
  } catch {
    return false;
  }
};

/** Whether the model behind `voiceId` is already stored on this device. */
export async function isVoiceDownloaded(voiceId: string, options: NeuralOptions): Promise<boolean> {
  if (typeof caches === 'undefined') return false;
  const voice = getNeuralVoice(voiceId);
  if (!voice) return false;
  if (voice.engine === 'kokoro') return cacheHas(TRANSFORMERS_CACHE, kokoroModelUrl(options.kokoroDevice));
  if (voice.engine === 'supertonic') {
    const present = await Promise.all(supertonicFileUrls().map(url => cacheHas(TTS_CACHE_NAME, url)));
    return present.every(Boolean);
  }
  return cacheHas(TTS_CACHE_NAME, piperModelUrls(voiceId.slice('piper:'.length)).model);
}

/** Delete a voice model. Kokoro and Supertonic share one model between all
 *  their voices, so this removes every voice of that engine. */
export async function deleteVoice(voiceId: string): Promise<void> {
  const voice = getNeuralVoice(voiceId);
  if (!voice) return;
  if (voice.engine === 'supertonic') {
    const cache = await caches.open(TTS_CACHE_NAME);
    const keys = await cache.keys();
    await Promise.all(keys.filter(k => k.url.startsWith(SUPERTONIC_BASE)).map(k => cache.delete(k)));
    return;
  }
  if (voice.engine === 'kokoro') {
    const cache = await caches.open(TRANSFORMERS_CACHE);
    const keys = await cache.keys();
    await Promise.all(keys.filter(k => k.url.includes(KOKORO_MODEL_ID)).map(k => cache.delete(k)));
    await caches.delete(KOKORO_VOICES_CACHE);
    return;
  }
  const urls = piperModelUrls(voiceId.slice('piper:'.length));
  const cache = await caches.open(TTS_CACHE_NAME);
  await Promise.all([cache.delete(urls.model), cache.delete(urls.config)]);
}

/** Delete every downloaded voice model. */
export async function deleteAllVoices(): Promise<void> {
  await caches.delete(TTS_CACHE_NAME);
  await caches.delete(KOKORO_VOICES_CACHE);
  const cache = await caches.open(TRANSFORMERS_CACHE);
  const keys = await cache.keys();
  await Promise.all(keys.filter(k => k.url.includes(KOKORO_MODEL_ID)).map(k => cache.delete(k)));
  // The worker may still hold a model in memory; restart it to release it.
  worker?.terminate();
  worker = null;
  pending.forEach(p => p.reject(new Error('cancelled')));
  pending.clear();
}

/** Total bytes used by downloaded voice models (approximate). */
export async function getVoicesStorageBytes(): Promise<number> {
  if (typeof caches === 'undefined') return 0;
  let total = 0;
  const sumCache = async (name: string, filter?: (url: string) => boolean) => {
    if (!(await caches.has(name))) return;
    const cache = await caches.open(name);
    for (const req of await cache.keys()) {
      if (filter && !filter(req.url)) continue;
      const res = await cache.match(req);
      const len = Number(res?.headers.get('content-length'));
      total += Number.isFinite(len) && len > 0 ? len : (await res?.blob())?.size ?? 0;
    }
  };
  await sumCache(TTS_CACHE_NAME);
  await sumCache(TRANSFORMERS_CACHE, url => url.includes(KOKORO_MODEL_ID));
  return total;
}
