import { useEffect, useRef, useState, type MutableRefObject, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { userService } from '../../../services/api';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { useNotification } from '@context/NotificationContext';
import { TTS_BAR_HEIGHT } from '../tts/ttsTypes';
import type { MarkReadBehavior } from '../readerSettingsSchema';

interface ChapterReadTrackingOptions {
  novelSlug?: string;
  sourceSlug?: string;
  chapterNumber?: string;
  currentChapterKey: string;
  chapter: IChapterContent | null;
  loading: boolean;
  activeTab: number;
  isAuthenticated: boolean;
  isNarrow: boolean;
  markReadBehavior: MarkReadBehavior;
  // Sentinel after the chapter text, watched to detect the reader reaching its end
  endOfChapterRef: RefObject<HTMLDivElement | null>;
  // Key of the chapter whose text is currently on screen (null while loading), owned by the reader
  loadedChapterKeyRef: MutableRefObject<string | null>;
  // Whether the TTS bar covers the bottom of the viewport, owned by the reader
  ttsOpenRef: MutableRefObject<boolean>;
}

// Manual and automatic "mark as read" for the current chapter
export function useChapterReadTracking({
  novelSlug,
  sourceSlug,
  chapterNumber,
  currentChapterKey,
  chapter,
  loading,
  activeTab,
  isAuthenticated,
  isNarrow,
  markReadBehavior,
  endOfChapterRef,
  loadedChapterKeyRef,
  ttsOpenRef,
}: ChapterReadTrackingOptions) {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const [markingAsRead, setMarkingAsRead] = useState(false);
  const [markReadSuccess, setMarkReadSuccess] = useState(false);

  // Key of the chapter already marked as read automatically (null if none)
  const autoMarkedKeyRef = useRef<string | null>(null);

  // Automatic marking runs for signed-in users when the setting says so
  const isAutoMarkEnabled = isAuthenticated &&
    (markReadBehavior === 'automatic' || markReadBehavior === 'buttonAutomatic');

  // The "mark as read" button shows for signed-in users when the setting says so
  const showMarkReadButton = isAuthenticated &&
    (markReadBehavior === 'button' || markReadBehavior === 'buttonAutomatic');

  // A previous chapter's "mark as read" success must not bleed into the next.
  useEffect(() => {
    setMarkReadSuccess(false);
  }, [novelSlug, sourceSlug, chapterNumber]);

  // Key of the chapter currently shown, so a late response can tell it is stale
  const latestChapterKeyRef = useRef(currentChapterKey);

  // Mark the chapter as read once the reader reaches its end, so the last
  // chapter (which has no "next" to navigate to) is recorded too
  useEffect(() => {
    latestChapterKeyRef.current = currentChapterKey;
    if (!isAutoMarkEnabled || loading || !chapter || activeTab !== 0 ||
        !novelSlug || !sourceSlug || !chapterNumber ||
        autoMarkedKeyRef.current === currentChapterKey) return;
    const endElement = endOfChapterRef.current;
    if (!endElement) return;

    const key = currentChapterKey;
    let pending = false;
    const stop = () => {
      observer.disconnect();
      window.removeEventListener('scroll', checkEndReached);
    };
    // Checked on both visibility changes and scrolls: the end can already be on
    // screen while the scroll guard below still holds, and the observer would
    // not fire again until it leaves and re-enters the viewport
    const checkEndReached = () => {
      // Right after a route change the previous chapter is still on screen
      if (pending || loadedChapterKeyRef.current !== key) return;
      const bottomOverlay = ttsOpenRef.current
        ? (isNarrow ? TTS_BAR_HEIGHT.mobile : TTS_BAR_HEIGHT.desktop)
        : 0;
      if (endElement.getBoundingClientRect().top > window.innerHeight - bottomOverlay) return;
      // A short chapter can look finished while its content is still laying out,
      // so wait for a scroll before marking when the page can scroll
      const doc = document.documentElement;
      if (doc.scrollHeight > doc.clientHeight && window.scrollY <= 0) return;

      // Stay subscribed until the request succeeds, so a failure retries on the
      // next scroll
      pending = true;
      userService.markChapterAsRead(novelSlug, sourceSlug, parseInt(chapterNumber))
        .then(() => {
          autoMarkedKeyRef.current = key;
          stop();
          if (latestChapterKeyRef.current === key) setMarkReadSuccess(true);
        })
        .catch((error) => {
          console.error('Error automatically marking chapter as read:', error);
        })
        .finally(() => {
          pending = false;
        });
    };
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) checkEndReached();
    });
    observer.observe(endElement);
    window.addEventListener('scroll', checkEndReached, { passive: true });
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- novelSlug, sourceSlug and chapterNumber are encoded in currentChapterKey
  }, [isAutoMarkEnabled, loading, chapter, activeTab, currentChapterKey]);

  // Automatic marking when leaving the chapter before its end was reached
  const markBeforeLeaving = async () => {
    if (isAutoMarkEnabled &&
        chapterNumber &&
        novelSlug &&
        sourceSlug &&
        autoMarkedKeyRef.current !== currentChapterKey) {
      try {
        await userService.markChapterAsRead(
          novelSlug,
          sourceSlug,
          parseInt(chapterNumber)
        );
      } catch (error) {
        console.error('Error automatically marking chapter as read:', error);
      }
    }
  };

  // Function to mark the current chapter as read
  const handleMarkAsRead = async () => {
    if (!novelSlug || !sourceSlug || !chapterNumber || !isAuthenticated) return;

    try {
      setMarkingAsRead(true);
      await userService.markChapterAsRead(
        novelSlug,
        sourceSlug,
        parseInt(chapterNumber)
      );
      setMarkReadSuccess(true);
      notify({ message: t('reader.markedRead'), severity: 'success', duration: 3000 });
    } catch (error) {
      console.error('Error marking chapter as read:', error);
    } finally {
      setMarkingAsRead(false);
    }
  };

  return {
    markingAsRead,
    markReadSuccess,
    showMarkReadButton,
    handleMarkAsRead,
    markBeforeLeaving,
  };
}
