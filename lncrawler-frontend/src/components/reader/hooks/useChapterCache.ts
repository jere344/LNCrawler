import { useRef } from 'react';
import { novelService } from '../../../services/api';
import { ChapterContent as IChapterContent } from '@models/novels_types';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

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

  return { fetchChapterContent, preloadNextChapter };
}
