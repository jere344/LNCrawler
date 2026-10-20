import { useCallback, useEffect, useState } from 'react';
import { neuralOptions, type TtsPrefs } from '../tts/ttsTypes';
import type { NeuralVoice } from '../tts/voiceCatalog';
import {
  deleteAllVoices,
  deleteVoice,
  getVoicesStorageBytes,
  isVoiceDownloaded,
  prepareVoice,
} from '../tts/neuralClient';

/** Progress is keyed by voice id, or by engine for shared models. */
export const progressKey = (voice: NeuralVoice) => (voice.engine === 'piper' ? voice.id : voice.engine);

interface UseNeuralModelsArgs {
  ttsEngine: TtsPrefs['ttsEngine'];
  neuralSupported: boolean;
  neuralVoices: NeuralVoice[];
  options: ReturnType<typeof neuralOptions>;
  selectedNeuralId: string | undefined;
}

/**
 * Download state, progress and storage for the HD (neural) voices.
 */
export function useNeuralModels({
  ttsEngine,
  neuralSupported,
  neuralVoices,
  options,
  selectedNeuralId,
}: UseNeuralModelsArgs) {
  const [downloaded, setDownloaded] = useState<Set<string>>(new Set());
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [storageBytes, setStorageBytes] = useState(0);
  const [neuralError, setNeuralError] = useState<string | null>(null);

  const refreshDownloaded = useCallback(async () => {
    if (!neuralSupported) return;
    const results = await Promise.all(
      neuralVoices.map(async v => [v.id, await isVoiceDownloaded(v.id, options)] as const),
    );
    setDownloaded(new Set(results.filter(([, ok]) => ok).map(([id]) => id)));
    setStorageBytes(await getVoicesStorageBytes());
  }, [neuralVoices, options, neuralSupported]);

  useEffect(() => {
    if (ttsEngine === 'neural') refreshDownloaded();
  }, [ttsEngine, refreshDownloaded]);

  // Load the selected HD voice into memory in the background once it is
  // downloaded, so preview and play don't wait for model initialisation.
  const selectedReady = !!selectedNeuralId && downloaded.has(selectedNeuralId);
  useEffect(() => {
    if (ttsEngine !== 'neural' || !selectedNeuralId || !selectedReady) return;
    prepareVoice(selectedNeuralId, options).catch(() => undefined);
  }, [ttsEngine, selectedNeuralId, selectedReady, options]);

  const downloadVoice = async (voice: NeuralVoice) => {
    const key = progressKey(voice);
    setNeuralError(null);
    setProgress(p => ({ ...p, [key]: 0 }));
    try {
      await prepareVoice(voice.id, options, (loaded, total) => {
        setProgress(p => ({ ...p, [key]: total ? (loaded / total) * 100 : 0 }));
      });
    } catch (err) {
      setNeuralError(err instanceof Error ? err.message : String(err));
    } finally {
      setProgress(p => {
        const next = { ...p };
        delete next[key];
        return next;
      });
      refreshDownloaded();
    }
  };

  const removeVoice = async (voice: NeuralVoice) => {
    await deleteVoice(voice.id);
    refreshDownloaded();
  };

  const removeAll = async () => {
    await deleteAllVoices();
    refreshDownloaded();
  };

  return {
    downloaded,
    progress,
    storageBytes,
    neuralError,
    setNeuralError,
    downloadVoice,
    removeVoice,
    removeAll,
  };
}
