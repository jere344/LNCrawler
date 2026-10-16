import type { NeuralOptions } from './voiceCatalog';

export type WorkerRequest =
  | { id: number; type: 'prepare'; voiceId: string; options: NeuralOptions }
  | { id: number; type: 'synth'; voiceId: string; options: NeuralOptions; text: string };

export type WorkerResponse =
  | { id: number; type: 'progress'; loaded: number; total: number }
  | { id: number; type: 'ready' }
  | { id: number; type: 'audio'; wav: ArrayBuffer; duration: number }
  | { id: number; type: 'error'; message: string };
