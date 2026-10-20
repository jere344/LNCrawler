import type { TtsDocument } from './textSegments';

/** Chunk index of the first chunk of the paragraph after `current`, or -1 when there is none. */
export function nextBlockChunk(doc: TtsDocument, current: number): number {
  const block = doc.chunks[current]?.block ?? -1;
  return doc.chunks.findIndex((c, k) => k > current && c.block !== block);
}

/** Chunk index to go back to from `current`: the start of its paragraph, or the
 *  previous paragraph when already at the start. */
export function previousBlockChunk(doc: TtsDocument, current: number): number {
  const block = doc.chunks[current]?.block ?? -1;
  const first = doc.chunks.findIndex(c => c.block === block);
  if (first !== -1 && first < current) return first;
  const prevBlock = doc.chunks[current - 1]?.block;
  if (prevBlock === undefined) return 0;
  return doc.chunks.findIndex(c => c.block === prevBlock);
}
