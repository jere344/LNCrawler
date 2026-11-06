import type { ChapterContent, UnavailableChapterInfo } from '@models/novels_types';
import { sectionKeyOf } from './chapterRange';

// Most chapter sections kept on the page at once in infinite mode
export const MAX_STREAM_CHAPTERS = 4;

export type StreamEnd = 'last' | 'gap' | 'unavailable' | 'dmca' | 'error';

export interface ChapterStreamState {
  chapters: ChapterContent[];
  loading: boolean;
  end: StreamEnd | null;
  // The chapter the stream stopped at: the gap's or the unavailable chapter's number
  endChapter: number | null;
  unavailable: UnavailableChapterInfo | null;
  // The loader's load the list started from: a new load of the route starts a new list
  loadId: number;
}

export type ChapterStreamAction =
  | { type: 'reset'; anchor: ChapterContent; loadId: number }
  | { type: 'loadStart' }
  | { type: 'append'; chapter: ChapterContent }
  | { type: 'end'; reason: StreamEnd; chapter?: number | null; unavailable?: UnavailableChapterInfo | null }
  | { type: 'retry' }
  | { type: 'cancel' }
  | { type: 'trimTop'; count: number }
  | { type: 'bumpComment'; chapterNumber: number; novelSlug: string };

export const initialStreamState: ChapterStreamState = {
  chapters: [],
  loading: false,
  end: null,
  endChapter: null,
  unavailable: null,
  loadId: -1,
};

const isSameChapter = (a: ChapterContent, b: ChapterContent): boolean =>
  a.chapter_id === b.chapter_id && a.source_slug === b.source_slug;

export function chapterStreamReducer(state: ChapterStreamState, action: ChapterStreamAction): ChapterStreamState {
  switch (action.type) {
    case 'reset':
      return { chapters: [action.anchor], loading: false, end: null, endChapter: null, unavailable: null, loadId: action.loadId };
    case 'loadStart':
      return state.loading || state.end ? state : { ...state, loading: true };
    case 'append': {
      const last = state.chapters[state.chapters.length - 1];
      const accepted = last !== undefined
        && action.chapter.chapter_id === last.next_chapter
        && !state.chapters.some((chapter) => isSameChapter(chapter, action.chapter));
      if (!accepted) return state.loading ? { ...state, loading: false } : state;
      return { ...state, chapters: [...state.chapters, action.chapter], loading: false };
    }
    case 'end': {
      const endChapter = action.chapter ?? null;
      const unavailable = action.unavailable ?? null;
      if (!state.loading && state.end === action.reason && state.endChapter === endChapter && state.unavailable === unavailable) {
        return state;
      }
      return { ...state, loading: false, end: action.reason, endChapter, unavailable };
    }
    case 'retry':
      return state.end === 'error' ? { ...state, end: null, endChapter: null, unavailable: null } : state;
    // The stream was turned off mid-fetch: the dropped result must not leave it loading
    case 'cancel':
      return state.loading ? { ...state, loading: false } : state;
    case 'trimTop': {
      const count = Math.min(action.count, state.chapters.length - 1);
      return count > 0 ? { ...state, chapters: state.chapters.slice(count) } : state;
    }
    // A comment posted to a chapter of this novel: every section of it on the page counts it
    case 'bumpComment': {
      const matches = (chapter: ChapterContent): boolean =>
        chapter.novel_slug === action.novelSlug && chapter.chapter_id === action.chapterNumber;
      if (!state.chapters.some(matches)) return state;
      return {
        ...state,
        chapters: state.chapters.map((chapter) => (matches(chapter)
          ? { ...chapter, comment_count: (chapter.comment_count ?? 0) + 1 }
          : chapter)),
      };
    }
  }
}

export type NextStep =
  | { kind: 'fetch'; chapter: number }
  | { kind: 'gap'; chapter: number }
  | { kind: 'last' }
  | null;

// What the stream does after its last chapter: fetch the next one, stop at a gap, or stop at the end of the novel
export function nextStep(state: ChapterStreamState): NextStep {
  const last = state.chapters[state.chapters.length - 1];
  if (!last || state.loading || state.end) return null;
  // Same rule as chapter navigation: no next available chapter is the end, even past an unavailable one
  if (!last.next_chapter) return { kind: 'last' };
  if (last.next_chapter_id != null && last.next_chapter_id !== last.next_chapter) {
    return { kind: 'gap', chapter: last.next_chapter_id };
  }
  return { kind: 'fetch', chapter: last.next_chapter };
}

// The chapter of this novel and source with that number, when it is on the page
export const findStreamChapter = (
  chapters: ChapterContent[],
  novelSlug: string | undefined,
  sourceSlug: string | undefined,
  chapterNumber: number,
): ChapterContent | null =>
  chapters.find((chapter) => chapter.novel_slug === novelSlug
    && chapter.source_slug === sourceSlug
    && chapter.chapter_id === chapterNumber) ?? null;

// How many chapters to drop from the top so at most `max` stay, without dropping a protected one or any after it
export function trimCount(chapters: ChapterContent[], protectedKeys: ReadonlySet<string>, max: number): number {
  const firstProtected = chapters.findIndex((chapter) => protectedKeys.has(sectionKeyOf(chapter)));
  const limit = firstProtected === -1 ? chapters.length : firstProtected;
  return Math.max(0, Math.min(chapters.length - max, limit));
}
