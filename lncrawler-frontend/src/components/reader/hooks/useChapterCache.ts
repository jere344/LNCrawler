import { useCallback, useRef } from 'react';
import { novelService } from '../../../services/api';
import { ChapterContent as IChapterContent } from '@models/novels_types';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

// Whether a payload is chapter `chapterNumber` of the novel: every source of it shares the chapter's comments
export const isChapterOfNovel = (chapter: IChapterContent, novelSlug: string, chapterNumber: number): boolean =>
  chapter.novel_slug === novelSlug && chapter.chapter_id === chapterNumber;

export function useChapterCache(novelSlug: string | undefined, sourceSlug: string | undefined) {
  // Create a ref to store our chapter cache that persists through renders
  const chapterCacheRef = useRef<ChapterCache>({});

  // Helper function to generate a cache key
  const getCacheKey = (novel: string, source: string, chapter: number): string => {
    return `${novel}|${source}|${chapter}`;
  };

  // Function to fetch chapter content
  const fetchChapterContent = async (novel: string, source: string, chapterNum: number): Promise<IChapterContent> => {
    const cacheKey = getCacheKey(novel, source, chapterNum);

    // Check if chapter exists in cache
    if (chapterCacheRef.current[cacheKey]) {
      return chapterCacheRef.current[cacheKey];
    }

    // If not in cache, fetch from API
    const response = await novelService.getChapterContent(novel, source, chapterNum);

    // Store in cache
    chapterCacheRef.current[cacheKey] = response;
    return response;
  };

  // Function to preload next chapter
  const preloadNextChapter = async (nextChapterNum: number) => {
    if (!novelSlug || !sourceSlug || !nextChapterNum) return;

    try {
      await fetchChapterContent(novelSlug, sourceSlug, nextChapterNum);
    } catch (err) {
      console.error(`Error preloading chapter ${nextChapterNum}:`, err);
    }
  };

  // Counts one more comment on every cached payload of this chapter number, in every source
  const bumpCommentCount = useCallback((novel: string, chapterNum: number) => {
    for (const [cacheKey, cached] of Object.entries(chapterCacheRef.current)) {
      if (!isChapterOfNovel(cached, novel, chapterNum)) continue;
      chapterCacheRef.current[cacheKey] = { ...cached, comment_count: (cached.comment_count ?? 0) + 1 };
    }
  }, []);

  return { fetchChapterContent, preloadNextChapter, bumpCommentCount };
}
