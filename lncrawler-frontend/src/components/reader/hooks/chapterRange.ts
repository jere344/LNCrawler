// The window scroll positions a chapter spans: scrollY at its start, and how far the window scrolls across it
export interface ScrollRange { start: number; length: number; height: number }

// How far the window is through the range, 0..1; 0 when there is nothing to scroll
export const progressIn = (range: ScrollRange, scrollY: number): number => {
  if (range.length <= 0) return 0;
  return Math.min(1, Math.max(0, (scrollY - range.start) / range.length));
};

// The window scroll at a progress through the range
export const scrollYFor = (range: ScrollRange, progress: number): number =>
  range.start + progress * Math.max(0, range.length);

// How far the window is through the range, as a percentage 0..100
export const percentIn = (range: ScrollRange, scrollY: number): number => progressIn(range, scrollY) * 100;

// The screen of the range the window is on, and how many screens it takes
export const pagesIn = (range: ScrollRange, viewport: number, scrollY: number): { page: number; pages: number } => {
  // Guarded so a document not laid out yet (no viewport) does not divide by zero
  const screen = Math.max(1, viewport);
  const pages = Math.max(1, Math.ceil(range.height / screen));
  const page = Math.min(pages, Math.max(1, Math.floor((scrollY - range.start) / screen) + 1));
  return { page, pages };
};

// The whole document, as chapter mode reads it
export const documentRange = (): ScrollRange => {
  const doc = document.documentElement;
  return { start: 0, length: doc.scrollHeight - doc.clientHeight, height: doc.scrollHeight };
};

// The section of the infinite-scroll page with that data-chapter-key; null when it is not on the page
export const sectionElement = (key: string): HTMLElement | null =>
  document.querySelector<HTMLElement>(`[data-chapter-key="${CSS.escape(key)}"]`);

// One section of the infinite-scroll page, by its data-chapter-key; null when it is not on the page
export const sectionRange = (key: string): ScrollRange | null => {
  const el = sectionElement(key);
  if (!el) return null;
  const rect = el.getBoundingClientRect();
  const top = rect.top + window.scrollY;
  return { start: top, length: rect.height - document.documentElement.clientHeight, height: rect.height };
};

// The range read for the chapter: its section in infinite mode, the whole document otherwise
export const chapterRange = (sectionKey: string | null): ScrollRange | null =>
  (sectionKey ? sectionRange(sectionKey) : documentRange());

// The key of a chapter's section on the infinite-scroll page, as its data-chapter-key carries it
export const sectionKeyOf = (chapter: { novel_slug: string; source_slug: string; chapter_id: number }): string =>
  `${chapter.novel_slug}|${chapter.source_slug}|${chapter.chapter_id}`;
