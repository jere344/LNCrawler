import type { ChapterContent } from '@models/novels_types';

// Whether a payload is chapter `chapterNumber` of the novel: every source of it shares the chapter's comments
export const isChapterOfNovel = (chapter: ChapterContent, novelSlug: string, chapterNumber: number): boolean =>
  chapter.novel_slug === novelSlug && chapter.chapter_id === chapterNumber;

// The same chapter payload with one more comment counted
export const withCommentAdded = (chapter: ChapterContent): ChapterContent =>
  ({ ...chapter, comment_count: (chapter.comment_count ?? 0) + 1 });
