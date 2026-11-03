import { useEffect, useState } from 'react';
import { resolveNeuralVoice, type NeuralEngine, type NeuralVoice } from '../../tts/voiceCatalog';

const FAMILY_ORDER: NeuralEngine[] = ['supertonic', 'kokoro', 'piper'];

// The voices of each model family, and the families that have at least one voice
export const groupByFamily = (voices: NeuralVoice[]) => {
  const familyVoices: Record<NeuralEngine, NeuralVoice[]> = { supertonic: [], kokoro: [], piper: [] };
  voices.forEach((voice) => familyVoices[voice.engine].push(voice));
  return { familyVoices, families: FAMILY_ORDER.filter((family) => familyVoices[family].length > 0) };
};

// Which model family the HD voices list shows. It opens on the selected voice's family and follows the language.
export const useModelFamily = (lang: string, voices: NeuralVoice[], selectedVoices: Record<string, string>) => {
  const { familyVoices, families } = groupByFamily(voices);
  const [modelFamily, setModelFamily] = useState<NeuralEngine>(
    resolveNeuralVoice(lang, selectedVoices)?.engine ?? 'supertonic',
  );
  useEffect(() => {
    setModelFamily(resolveNeuralVoice(lang, selectedVoices)?.engine ?? 'supertonic');
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-sync only when the language changes
  }, [lang]);

  const visibleFamily: NeuralEngine = families.includes(modelFamily) ? modelFamily : families[0] ?? 'piper';
  return { familyVoices, families, visibleFamily, setModelFamily };
};
