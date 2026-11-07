import type { UnavailableChapterInfo } from '@models/novels_types';

export type ChapterLoadFailure =
  | { kind: 'dmca' }
  | { kind: 'unavailable'; info: UnavailableChapterInfo }
  | { kind: 'error' };

// Tells a removed chapter (451), an empty one with its 404 page, and any other failure apart
export const classifyChapterError = (err: unknown): ChapterLoadFailure => {
  const response = (err as {
    response?: { status?: number; data?: UnavailableChapterInfo };
  })?.response;
  if (response?.status === 451) return { kind: 'dmca' };
  const unavailable = response?.status === 404 ? response.data : undefined;
  if (unavailable && typeof unavailable.chapter_id === 'number') return { kind: 'unavailable', info: unavailable };
  return { kind: 'error' };
};

export interface ChapterFailureHandlers<T> {
  dmca: () => T;
  unavailable: (info: UnavailableChapterInfo) => T;
  other: () => T;
}

// Runs the handler for the kind of failure a chapter load raised
export const handleChapterFailure = <T>(err: unknown, handlers: ChapterFailureHandlers<T>): T => {
  const failure = classifyChapterError(err);
  if (failure.kind === 'dmca') return handlers.dmca();
  if (failure.kind === 'unavailable') return handlers.unavailable(failure.info);
  return handlers.other();
};
