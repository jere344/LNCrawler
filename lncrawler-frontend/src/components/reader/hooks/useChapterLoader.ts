import { useState, useEffect, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ChapterContent as IChapterContent, UnavailableChapterInfo } from '@models/novels_types';
import { isChapterOfNovel, useChapterCache } from './useChapterCache';

interface ChapterLoaderOptions {
  novelSlug?: string;
  sourceSlug?: string;
  chapterNumber?: string;
  // Called as a new chapter starts loading, before its text is on screen
  onLoadStart: () => void;
}

// Fetches the chapter for the route and preloads the next one
export function useChapterLoader({ novelSlug, sourceSlug, chapterNumber, onLoadStart }: ChapterLoaderOptions) {
  const { t } = useTranslation();
  const [chapter, setChapter] = useState<IChapterContent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [unavailableChapter, setUnavailableChapter] = useState<UnavailableChapterInfo | null>(null);

  // Chapter content cache and preload
  const { fetchChapterContent, preloadNextChapter, bumpCommentCount: bumpCachedCommentCount } = useChapterCache(novelSlug, sourceSlug);

  // Tags each chapter fetch so a slow older request can't overwrite a newer one
  const loadRequestIdRef = useRef(0);

  useEffect(() => {
    const loadCurrentChapter = async () => {
      if (!novelSlug || !sourceSlug || !chapterNumber) return;

      const requestId = ++loadRequestIdRef.current;
      setError(null);
      setUnavailableChapter(null);
      setLoading(true);
      onLoadStart();
      try {
        const chapterData = await fetchChapterContent(
          novelSlug,
          sourceSlug,
          parseInt(chapterNumber)
        );
        // Ignore a stale response if the user navigated to another chapter.
        if (requestId !== loadRequestIdRef.current) return;
        setChapter(chapterData);

        // Preload next chapter if it exists
        if (chapterData.next_chapter) {
          preloadNextChapter(chapterData.next_chapter);
        }
      } catch (err) {
        if (requestId !== loadRequestIdRef.current) return;
        console.error('Error fetching chapter content:', err);
        const response = (err as {
          response?: { status?: number; data?: UnavailableChapterInfo };
        })?.response;
        const unavailable = response?.status === 404 ? response.data : undefined;
        if (response?.status === 451) {
          setError(t('reader.dmcaUnavailable'));
        } else if (unavailable && typeof unavailable.chapter_id === 'number') {
          // The chapter exists but has no content: show the unavailable page
          // instead of a generic error, with working next/prev navigation.
          setChapter(null);
          setUnavailableChapter(unavailable);
        } else {
          setError(t('reader.loadFailed'));
        }
      } finally {
        if (requestId === loadRequestIdRef.current) {
          setLoading(false);
        }
      }
    };

    loadCurrentChapter();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t/loader/onLoadStart intentionally omitted; route params are the inputs
  }, [novelSlug, sourceSlug, chapterNumber]);

  // A comment posted to a chapter of this novel: the cached payloads and the chapter on screen count it
  const bumpCommentCount = useCallback((chapterNumber: number) => {
    if (!novelSlug) return;
    bumpCachedCommentCount(novelSlug, chapterNumber);
    setChapter((current) => (current && isChapterOfNovel(current, novelSlug, chapterNumber)
      ? { ...current, comment_count: (current.comment_count ?? 0) + 1 }
      : current));
  }, [novelSlug, bumpCachedCommentCount]);

  return { chapter, loading, error, unavailableChapter, bumpCommentCount };
}
