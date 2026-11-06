import { describe, expect, it } from 'vitest';
import type { ChapterContent } from '@models/novels_types';
import { chapterStreamReducer, findStreamChapter, initialStreamState, nextStep, trimCount, type ChapterStreamState } from './chapterStream';

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

const withChapters = (...numbers: number[]): ChapterStreamState => ({
  ...initialStreamState,
  chapters: numbers.map((n) => makeChapter(n)),
});

describe('chapterStreamReducer', () => {
  it('starts the stream again from the anchor', () => {
    const state = chapterStreamReducer(withChapters(1, 2, 3), { type: 'reset', anchor: makeChapter(5), loadId: 2 });
    expect(state).toEqual({ chapters: [makeChapter(5)], loading: false, end: null, endChapter: null, unavailable: null, loadId: 2 });
  });

  it('appends the chapter that follows the last one', () => {
    const start = chapterStreamReducer(withChapters(1), { type: 'loadStart' });
    const state = chapterStreamReducer(start, { type: 'append', chapter: makeChapter(2) });
    expect(state.chapters.map((c) => c.chapter_id)).toEqual([1, 2]);
    expect(state.loading).toBe(false);
  });

  it('ignores a stale or duplicate chapter', () => {
    const start = chapterStreamReducer(withChapters(1, 2), { type: 'loadStart' });
    const stale = chapterStreamReducer(start, { type: 'append', chapter: makeChapter(5) });
    expect(stale.chapters.map((c) => c.chapter_id)).toEqual([1, 2]);
    expect(stale.loading).toBe(false);
    const duplicate = chapterStreamReducer(withChapters(1, 2), { type: 'append', chapter: makeChapter(2) });
    expect(duplicate.chapters.map((c) => c.chapter_id)).toEqual([1, 2]);
  });

  it('does not append to an empty stream', () => {
    const state = chapterStreamReducer(initialStreamState, { type: 'append', chapter: makeChapter(1) });
    expect(state.chapters).toEqual([]);
  });

  it('drops the first chapters, keeping at least one', () => {
    expect(chapterStreamReducer(withChapters(1, 2, 3, 4), { type: 'trimTop', count: 2 }).chapters.map((c) => c.chapter_id))
      .toEqual([3, 4]);
    expect(chapterStreamReducer(withChapters(1, 2), { type: 'trimTop', count: 9 }).chapters.map((c) => c.chapter_id))
      .toEqual([2]);
    const single = withChapters(1);
    expect(chapterStreamReducer(single, { type: 'trimTop', count: 1 })).toBe(single);
  });

  it('keeps the same state when nothing changes', () => {
    const state = withChapters(1);
    expect(chapterStreamReducer(state, { type: 'retry' })).toBe(state);
    expect(chapterStreamReducer(state, { type: 'append', chapter: makeChapter(9) })).toBe(state);
  });

  it('stops at an end and records where', () => {
    const unavailable = { chapter_id: 3, title: 'Three', novel_title: 'Novel' };
    const state = chapterStreamReducer(withChapters(1, 2), { type: 'end', reason: 'unavailable', chapter: 3, unavailable });
    expect(state).toMatchObject({ end: 'unavailable', endChapter: 3, unavailable, loading: false });
  });

  it('retries only after an error', () => {
    const failed = chapterStreamReducer(withChapters(1), { type: 'end', reason: 'error', chapter: 2 });
    const retried = chapterStreamReducer(failed, { type: 'retry' });
    expect(retried).toMatchObject({ end: null, endChapter: null, unavailable: null });

    const dmca = chapterStreamReducer(withChapters(1), { type: 'end', reason: 'dmca', chapter: 2 });
    expect(chapterStreamReducer(dmca, { type: 'retry' })).toBe(dmca);
  });

  it('stops loading when cancelled, so a later load can start', () => {
    const loading = chapterStreamReducer(withChapters(1), { type: 'loadStart' });
    const cancelled = chapterStreamReducer(loading, { type: 'cancel' });
    expect(cancelled.loading).toBe(false);
    expect(nextStep(cancelled)).toEqual({ kind: 'fetch', chapter: 2 });
    expect(chapterStreamReducer(cancelled, { type: 'cancel' })).toBe(cancelled);
  });
});

describe('bumpComment', () => {
  it('counts the comment on every section of that chapter of the novel', () => {
    const start = withChapters(1, 2, 3);
    const state = chapterStreamReducer(start, { type: 'bumpComment', chapterNumber: 2, novelSlug: 'novel' });
    expect(state.chapters.map((c) => c.comment_count)).toEqual([undefined, 1, undefined]);
    expect(state.chapters[0]).toBe(start.chapters[0]);
    expect(state.chapters[2]).toBe(start.chapters[2]);
    const again = chapterStreamReducer(state, { type: 'bumpComment', chapterNumber: 2, novelSlug: 'novel' });
    expect(again.chapters[1]?.comment_count).toBe(2);
  });

  it('keeps the same state when no section of that novel matches', () => {
    const state = withChapters(1, 2);
    expect(chapterStreamReducer(state, { type: 'bumpComment', chapterNumber: 5, novelSlug: 'novel' })).toBe(state);
    expect(chapterStreamReducer(state, { type: 'bumpComment', chapterNumber: 2, novelSlug: 'another-novel' })).toBe(state);
  });
});

describe('nextStep', () => {
  it('asks for the next chapter when the last one names it', () => {
    expect(nextStep(withChapters(1, 2))).toEqual({ kind: 'fetch', chapter: 3 });
  });

  it('stops at a gap when the next available chapter is not the next number', () => {
    const state: ChapterStreamState = {
      ...initialStreamState,
      chapters: [makeChapter(1, { next_chapter: 3, next_chapter_id: 2 })],
    };
    expect(nextStep(state)).toEqual({ kind: 'gap', chapter: 2 });
  });

  it('reports the last chapter of the novel', () => {
    const state: ChapterStreamState = {
      ...initialStreamState,
      chapters: [makeChapter(9, { next_chapter: null, next_chapter_id: null })],
    };
    expect(nextStep(state)).toEqual({ kind: 'last' });
  });

  it('ends rather than stopping at a gap when no chapter is available after it', () => {
    const state: ChapterStreamState = {
      ...initialStreamState,
      chapters: [makeChapter(9, { next_chapter: null, next_chapter_id: 10 })],
    };
    expect(nextStep(state)).toEqual({ kind: 'last' });
  });

  it('is null with no chapter, while loading or once ended', () => {
    expect(nextStep(initialStreamState)).toBeNull();
    expect(nextStep({ ...withChapters(1), loading: true })).toBeNull();
    expect(nextStep({ ...withChapters(1), end: 'error', endChapter: 2 })).toBeNull();
  });
});

describe('findStreamChapter', () => {
  const chapters = [makeChapter(1), makeChapter(2), makeChapter(3, { source_slug: 'other' })];

  it('finds the chapter of the same novel and source', () => {
    expect(findStreamChapter(chapters, 'novel', 'source', 2)).toBe(chapters[1]);
  });

  it('ignores the same number in another novel or source', () => {
    expect(findStreamChapter(chapters, 'another-novel', 'source', 2)).toBeNull();
    expect(findStreamChapter(chapters, 'novel', 'source', 3)).toBeNull();
  });
});

describe('trimCount', () => {
  const none = new Set<string>();
  const keyOf = (n: number) => `novel|source|${n}`;

  it('drops nothing under the cap', () => {
    expect(trimCount(withChapters(1, 2, 3).chapters, none, 4)).toBe(0);
    expect(trimCount(withChapters(1, 2, 3, 4).chapters, none, 4)).toBe(0);
  });

  it('drops the excess over the cap', () => {
    expect(trimCount(withChapters(1, 2, 3, 4, 5, 6).chapters, none, 4)).toBe(2);
  });

  it('stops before a protected chapter', () => {
    const chapters = withChapters(1, 2, 3, 4, 5, 6).chapters;
    expect(trimCount(chapters, new Set([keyOf(2)]), 4)).toBe(1);
    expect(trimCount(chapters, new Set([keyOf(2), keyOf(5)]), 4)).toBe(1);
  });

  it('drops nothing when the first chapter is protected', () => {
    expect(trimCount(withChapters(1, 2, 3, 4, 5).chapters, new Set([keyOf(1)]), 4)).toBe(0);
  });
});
