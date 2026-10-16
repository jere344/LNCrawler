import type { KokoroDevice } from './voiceCatalog';

export type WorkerRequest =
  | { id: number; type: 'prepare'; voiceId: string; kokoroDevice: KokoroDevice }
  | { id: number; type: 'synth'; voiceId: string; kokoroDevice: KokoroDevice; text: string };

export type WorkerResponse =
  | { id: number; type: 'progress'; loaded: number; total: number }
  | { id: number; type: 'ready' }
  | { id: number; type: 'audio'; wav: ArrayBuffer; duration: number }
  | { id: number; type: 'error'; message: string };
