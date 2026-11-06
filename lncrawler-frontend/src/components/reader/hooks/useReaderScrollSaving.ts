import { useEffect, useRef, type MutableRefObject } from 'react';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { useScrollPersistence, SCROLL_SAVE_THROTTLE } from './useScrollPersistence';

interface ReaderScrollSavingOptions {
  currentChapterKey: string;
  // Infinite mode: the section of the chapter being read; null for the whole document
  sectionKey: string | null;
  // Bumped by the loader on each real load; an in-place switch keeps it
  loadId: number;
  chapter: IChapterContent | null;
  loading: boolean;
  savePosition: boolean;
  // Key of the chapter whose text is currently on screen (null while loading), owned by the reader
  loadedChapterKeyRef: MutableRefObject<string | null>;
}

// Scroll position save/restore for the current chapter
export function useReaderScrollSaving({
  currentChapterKey,
  sectionKey,
  loadId,
  chapter,
  loading,
  savePosition,
  loadedChapterKeyRef,
}: ReaderScrollSavingOptions) {
  const { saveScrollPosition, restoreScrollPosition, cancelRestore } = useScrollPersistence({
    currentChapterKey,
    savePosition,
  });

  // The load whose position was last restored: a switch in place keeps the window where it is
  const restoredLoadIdRef = useRef<number | null>(null);
  // Section key of the chapter whose text is on screen, committed with loadedChapterKeyRef
  const loadedSectionKeyRef = useRef<string | null>(null);

  // Only save while the current chapter's text is on screen: during a load the
  // DOM is the spinner or the previous chapter, which would overwrite the
  // saved position before it is restored.
  const saveScrollIfReady = (force = false) => {
    if (loadedChapterKeyRef.current !== currentChapterKey) return;
    saveScrollPosition(loadedSectionKeyRef.current, force);
  };

  useEffect(() => {
    if (!loading && chapter) {
      // The chapter's text is now committed, so saves for this key are safe
      loadedChapterKeyRef.current = currentChapterKey;
      loadedSectionKeyRef.current = sectionKey;
      if (restoredLoadIdRef.current !== loadId) {
        restoredLoadIdRef.current = loadId;
        restoreScrollPosition(sectionKey);
      }
    }
    return () => {
      cancelRestore();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only on the listed scroll inputs
  }, [loading, chapter]);

  // Save scroll position when navigating or every minute
  useEffect(() => {
    // Save position periodically while reading
    const saveInterval = setInterval(() => {
      if (chapter && !loading && savePosition) {
        saveScrollIfReady();
      }
    }, 60000); // Save every minute

    // Save on page visibility change (tab switching, etc.)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveScrollIfReady();
      }
    };

    // Use passive scroll listener with throttling
    let scrollTimeout: number | null = null;
    const handleScroll = () => {
      if (scrollTimeout === null) {
        scrollTimeout = window.setTimeout(() => {
          scrollTimeout = null;
          saveScrollIfReady();
        }, SCROLL_SAVE_THROTTLE);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('scroll', handleScroll, { passive: true });

    // Cleanup
    return () => {
      clearInterval(saveInterval);
      if (scrollTimeout) {
        clearTimeout(scrollTimeout);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('scroll', handleScroll);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-subscribe only when the listed save inputs change
  }, [chapter, loading, savePosition, currentChapterKey]);

  return { saveScrollIfReady };
}
