import type { TFunction } from 'i18next';
import type { AudiobookCard } from '@models/audiobook_types';
import { readLocalStorage } from './storage';

// Audiobook page of a novel. The slug is the public key; `lang` is only added for non-English editions.
export const audiobookPath = (slug: string, lang: string) =>
  `/audiobooks/${encodeURIComponent(slug)}/${lang === 'en' ? '' : `?lang=${encodeURIComponent(lang)}`}`;

// Listening saved in this browser while logged out, one entry per audiobook and language. Persisted: keep the key.
export const PROGRESS_KEY = 'audiobookProgress';

export const progressKey = (slug: string, lang: string) => `${slug}|${lang}`;

// Key of an audiobook in the adult reveal state (AdultContentContext), kept apart from novel ids.
export const audiobookRevealKey = (slug: string, lang: string) => `audiobook:${progressKey(slug, lang)}`;

export interface LocalProgress {
  chapter_id: number;
  position_s: number;
  finished: boolean;
}

// This browser's saved position of an audiobook, null when there is none.
export const readLocalProgress = (slug: string, lang: string): LocalProgress | null =>
  readLocalStorage<Record<string, LocalProgress>>(PROGRESS_KEY, {})[progressKey(slug, lang)] ?? null;

// Chapter-based share of the book the viewer got through (the card has no per-chapter duration).
export const progressRatio = (book: AudiobookCard): number => {
  const progress = book.progress;
  if (!progress) return 0;
  if (progress.finished) return 1;
  const done = Math.max(0, (progress.chapter_number ?? 1) - 1);
  return Math.min(1, done / Math.max(1, book.chapters));
};

// "Chapter 12", "Ch. 12 -", "c12:" or "12." at the start of a crawled title (a bare number needs a separator: "12 Days" stays)
const LEADING_CHAPTER_NUMBER = /^\s*(?:(?:chapter|chapitre|capítulo|chương|ch\.?|c)\s*\d+\s*[-:,.–—]?|\d+\s*[-:,.–—])\s*/i;

// "Chapter 3: The Fool", or just "Chapter 3" when the title is only that number (most crawled titles repeat it).
export const audioChapterLabel = (t: TFunction, number: number, title: string) => {
  const name = (title || '').replace(LEADING_CHAPTER_NUMBER, '').trim();
  return name ? t('audioPlayer.chapterLabel', { number, title: name }) : t('units.chapter', { number });
};
