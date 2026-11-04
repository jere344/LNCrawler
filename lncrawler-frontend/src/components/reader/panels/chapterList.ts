import type { NovelChaptersResponse } from '@models/novels_types';
import { novelService } from '@services/novel.service';
import { createChapterListCache } from './chapterListCache';

// Every request uses this size: a row's index gives its page and its place in it.
// The backend caps page_size at 500 (parse_page_size(request, 100, 500) in sources_views.py).
export const CHAPTER_PAGE_SIZE = 100;

// Shared by every reader visit: a chapter list reopened within its TTL makes no request
export const chapterListCache = createChapterListCache((request) =>
  novelService.getNovelChapters(request.novelSlug, request.sourceSlug, request.page, CHAPTER_PAGE_SIZE, request.search, request.around),
);

// Index of a chapter in the unfiltered list, from the page that holds it; null when it is not in that page
export function chapterIndex(page: NovelChaptersResponse, chapterId: number): number | null {
  const offset = page.chapters.findIndex((chapter) => chapter.chapter_id === chapterId);
  return offset === -1 ? null : (page.current_page - 1) * CHAPTER_PAGE_SIZE + offset;
}

// The pages (1-based, inclusive) covering rows [start, end) clamped to [0, count); [1, 0] when there is nothing to load
export function pageRange(start: number, end: number, count: number): [first: number, last: number] {
  const from = Math.max(0, start);
  const to = Math.min(end, count);
  if (count === 0 || from >= to) return [1, 0];
  return [Math.floor(from / CHAPTER_PAGE_SIZE) + 1, Math.floor((to - 1) / CHAPTER_PAGE_SIZE) + 1];
}
