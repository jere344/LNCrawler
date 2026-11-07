import { progressIn, type ScrollRange } from './chapterRange';

// Server sync of the reading position: the decisions behind it, with no React or network in them

// How far through a chapter the reader is, 0..1. A chapter with nothing to scroll is read in full once shown.
export const readProgress = (range: ScrollRange | null, scrollY: number): number => {
  if (!range) return 0;
  if (range.length <= 0) return 1;
  return progressIn(range, scrollY);
};

// The history state without the Continue progress, once it has been applied (a refresh then restores from this device)
export const withoutResumeProgress = (state: unknown): Record<string, unknown> => {
  const rest = { ...(state && typeof state === 'object' ? (state as Record<string, unknown>) : {}) };
  delete rest.resumeProgress;
  return rest;
};

// Progress through a chapter from which it counts as finished
export const FINISHED_PROGRESS = 0.95;
// Least time between two saves of the same chapter, the finishing save aside
export const POSITION_SAVE_INTERVAL_MS = 15000;

// A chapter the reader moves to, in the route's novel and source
export interface NavigationTarget {
  novelSlug?: string;
  sourceSlug?: string;
  chapterNumber: number;
}

// Keys pressed in a field are typing, not reading: they do not count as scrolling
export const isTypingTarget = (target: EventTarget | null): boolean => {
  const element = target as { tagName?: string; isContentEditable?: boolean; getAttribute?: (name: string) => string | null } | null;
  if (!element) return false;
  // The attribute covers environments without isContentEditable
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName ?? '')
    || element.isContentEditable === true
    || element.getAttribute?.('contenteditable') === 'true';
};

// The keys that scroll the page
const SCROLL_KEYS = new Set([' ', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End']);

export const isScrollKey = (key: string): boolean => SCROLL_KEYS.has(key);

// A page too short to scroll has nothing to scroll to, so it counts as read once shown
export const isScrollable = (doc: { scrollHeight: number; clientHeight: number }): boolean =>
  doc.scrollHeight > doc.clientHeight;

// What was last saved for one chapter, which paces the saves of that chapter
export interface ChapterSaveState {
  key: string;
  // When the last save went out; null before the first
  lastSavedAt: number | null;
  // Whether a save at the finishing progress went out
  finished: boolean;
}

// The save state of a chapter; a state for another chapter is replaced
export const saveStateFor = (state: ChapterSaveState | null, key: string): ChapterSaveState =>
  state?.key === key ? state : { key, lastSavedAt: null, finished: false };

// Whether a save point goes to the server: the first one, the first at the finish, then one per interval
export const shouldSavePosition = (state: ChapterSaveState, progress: number, now: number): boolean => {
  if (state.lastSavedAt === null) return true;
  if (progress >= FINISHED_PROGRESS && !state.finished) return true;
  return now - state.lastSavedAt >= POSITION_SAVE_INTERVAL_MS;
};

export const recordPositionSaved = (state: ChapterSaveState, progress: number, now: number): ChapterSaveState => ({
  ...state,
  lastSavedAt: now,
  finished: state.finished || progress >= FINISHED_PROGRESS,
});

// A position as it goes to the server: the chapter, and how far through it (0..1)
export interface PositionTarget {
  novelSlug: string;
  sourceSlug: string;
  chapterNumber: number;
  progress: number;
}

// The progress a Continue link passes in the router state; null when there is none
export const resumeProgressFrom = (state: unknown): number | null => {
  const value = state && typeof state === 'object'
    ? (state as { resumeProgress?: unknown }).resumeProgress
    : undefined;
  return typeof value === 'number' && Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : null;
};

// Requests one at a time. While one is in flight, only the latest waiting payload is kept, and sent after it.
export interface PositionQueue {
  push: (target: PositionTarget) => void;
  // Drops the waiting payload, for a newer one that is sent another way
  drop: () => void;
}

export const createPositionQueue = (
  send: (target: PositionTarget) => Promise<unknown>,
  onError: (error: unknown) => void,
): PositionQueue => {
  let inFlight = false;
  let waiting: PositionTarget | null = null;

  const run = async (target: PositionTarget): Promise<void> => {
    inFlight = true;
    try {
      await send(target);
    } catch (error) {
      onError(error);
    } finally {
      inFlight = false;
      const next = waiting;
      waiting = null;
      if (next) void run(next);
    }
  };

  return {
    push: (target) => {
      if (inFlight) waiting = target;
      else void run(target);
    },
    drop: () => {
      waiting = null;
    },
  };
};

// A 409 from the position endpoint means the chapter has no content: expected for a gap, so not logged
export const isUnavailableSave = (error: unknown): boolean =>
  (error as { response?: { status?: number } } | null)?.response?.status === 409;

export const reportSaveError = (error: unknown): void => {
  if (!isUnavailableSave(error)) console.error('Error saving reading position:', error);
};
