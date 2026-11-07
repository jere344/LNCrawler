import { useCallback, useRef } from 'react';
import { novelService } from '../../../services/api';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { isChapterOfNovel, withCommentAdded } from './chapterComments';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

// Helper function to generate a cache key
const getCacheKey = (novel: string, source: string, chapter: number): string => {
  return `${novel}|${source}|${chapter}`;
};

export function useChapterCache(novelSlug: string | undefined, sourceSlug: string | undefined) {
  // Create a ref to store our chapter cache that persists through renders
  const chapterCacheRef = useRef<ChapterCache>({});
  // Requests still in flight, so a preload and a load of the same chapter share one fetch
  const pendingRef = useRef<Record<string, Promise<IChapterContent>>>({});

  // Function to fetch chapter content
  const fetchChapterContent = useCallback(async (novel: string, source: string, chapterNum: number): Promise<IChapterContent> => {
    const cacheKey = getCacheKey(novel, source, chapterNum);

    // Check if chapter exists in cache
    if (chapterCacheRef.current[cacheKey]) {
      return chapterCacheRef.current[cacheKey];
    }

    // If not in cache, fetch from API, once
    pendingRef.current[cacheKey] ??= novelService.getChapterContent(novel, source, chapterNum)
      .then((response) => {
        chapterCacheRef.current[cacheKey] = response;
        return response;
      })
      .finally(() => {
        delete pendingRef.current[cacheKey];
      });
    return pendingRef.current[cacheKey];
  }, []);

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
      chapterCacheRef.current[cacheKey] = withCommentAdded(cached);
    }
  }, []);

  return { fetchChapterContent, preloadNextChapter, bumpCommentCount };
}
