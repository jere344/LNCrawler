import type { ChapterContent } from '@models/novels_types';
import { findStreamChapter } from './chapterStream';

// What TTS does once its chapter ends, in infinite mode
export type TtsNextStep =
  | { kind: 'pin'; chapter: ChapterContent }
  | { kind: 'open'; chapter: number }
  | { kind: 'load'; chapter: number }
  | null;

// The chapter after the one TTS reads: a gap opens its page, one on the page is read next, any other is loaded
export function ttsNextStep(current: ChapterContent | null, streamChapters: ChapterContent[]): TtsNextStep {
  if (!current?.next_chapter) return null;
  const next = current.next_chapter;
  // Same rule as chapter navigation: the unavailable chapter in between is opened
  if (current.next_chapter_id != null && current.next_chapter_id !== next) {
    return { kind: 'open', chapter: current.next_chapter_id };
  }
  const onPage = findStreamChapter(streamChapters, current.novel_slug, current.source_slug, next);
  return onPage ? { kind: 'pin', chapter: onPage } : { kind: 'load', chapter: next };
}
