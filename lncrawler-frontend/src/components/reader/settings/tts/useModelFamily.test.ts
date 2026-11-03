import { describe, it, expect } from 'vitest';
import type { NeuralVoice } from '../../tts/voiceCatalog';
import { groupByFamily } from './useModelFamily';

const voice = (id: string, engine: NeuralVoice['engine']) => ({ id, engine }) as NeuralVoice;

describe('groupByFamily', () => {
  it('splits the voices by family and lists only the families that have voices', () => {
    const { familyVoices, families } = groupByFamily([
      voice('piper:a', 'piper'),
      voice('supertonic:F1', 'supertonic'),
      voice('supertonic:M1', 'supertonic'),
    ]);
    expect(families).toEqual(['supertonic', 'piper']);
    expect(familyVoices.supertonic.map((v) => v.id)).toEqual(['supertonic:F1', 'supertonic:M1']);
    expect(familyVoices.kokoro).toEqual([]);
  });

  it('returns no families for no voices', () => {
    expect(groupByFamily([]).families).toEqual([]);
  });
});
