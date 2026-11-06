import { describe, expect, it } from 'vitest';
import type { ChapterContent } from '@models/novels_types';
import { ttsNextStep } from './ttsChapter';

const makeChapter = (n: number, overrides: Partial<ChapterContent> = {}): ChapterContent => ({
  id: `id-${n}`,
  chapter_id: n,
  title: `Chapter ${n}`,
  novel_title: 'Novel',
  novel_id: 'novel-1',
  novel_slug: 'novel',
  source_id: 'source-1',
  source_name: 'Source',
  source_slug: 'source',
  body: '',
  prev_chapter: n - 1,
  next_chapter: n + 1,
  prev_chapter_id: n - 1,
  next_chapter_id: n + 1,
  ...overrides,
});

describe('ttsNextStep', () => {
  it('opens the unavailable chapter in a gap', () => {
    const current = makeChapter(3, { next_chapter: 5, next_chapter_id: 4 });
    expect(ttsNextStep(current, [current, makeChapter(5)])).toEqual({ kind: 'open', chapter: 4 });
  });

  it('pins the next chapter when it is on the page', () => {
    const current = makeChapter(3);
    const next = makeChapter(4);
    expect(ttsNextStep(current, [makeChapter(2), current, next])).toEqual({ kind: 'pin', chapter: next });
  });

  it('loads the next chapter when it is not on the page', () => {
    const current = makeChapter(3);
    expect(ttsNextStep(current, [current])).toEqual({ kind: 'load', chapter: 4 });
  });

  it('ignores a chapter of another novel with the same number', () => {
    const current = makeChapter(3);
    const other = makeChapter(4, { novel_slug: 'other' });
    expect(ttsNextStep(current, [current, other])).toEqual({ kind: 'load', chapter: 4 });
  });

  it('does nothing without a next chapter', () => {
    expect(ttsNextStep(makeChapter(9, { next_chapter: null, next_chapter_id: null }), [])).toBeNull();
    expect(ttsNextStep(null, [])).toBeNull();
  });
});
