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

// The chapters marked as read in this session, for the novel and source they belong to
interface MarkedChapters {
  scope: string;
  chapters: Set<number>;
}

// Shared empty set, for a novel or source with no chapter marked yet
const NO_CHAPTERS: Set<number> = new Set();

// Manual and automatic "mark as read" for the chapters of the reader
export function useChapterReadTracking({
  novelSlug,
  sourceSlug,
  chapterNumber,
  currentChapterKey,
  chapter,
  loading,
  isAuthenticated,
  isNarrow,
  markReadBehavior,
  endOfChapterRef,
  loadedChapterKeyRef,
  ttsOpenRef,
}: ChapterReadTrackingOptions) {
  const { t } = useTranslation();
  const { notify } = useNotification();

  // The novel and source of the reader now; the marked chapters of another one do not count
  const scope = `${novelSlug}|${sourceSlug}`;
  const scopeRef = useRef(scope);
  scopeRef.current = scope;

  // Marked chapters, with a mirror for the callbacks, which read them after an await
  const [marked, setMarked] = useState<MarkedChapters>({ scope, chapters: new Set() });
  const markedRef = useRef(marked);
  const markedChapters = marked.scope === scope ? marked.chapters : NO_CHAPTERS;

  // Chapters with a "mark as read" request in flight, by hand or automatically, with a mirror for the same reason
  const [inFlight, setInFlight] = useState<MarkedChapters>({ scope, chapters: new Set() });
  const inFlightRef = useRef(inFlight);
  const markingChapters = inFlight.scope === scope ? inFlight.chapters : NO_CHAPTERS;

  // Whether a chapter of the reader's novel and source was marked in this session
  const isMarked = (n: number): boolean =>
    markedRef.current.scope === scope && markedRef.current.chapters.has(n);

  // Whether a chapter is marked, or its request is already on its way
  const isBusy = (n: number): boolean =>
    isMarked(n) || (inFlightRef.current.scope === scope && inFlightRef.current.chapters.has(n));

  // Records a request as in flight before it is sent, so the same chapter is not sent twice
  const startMarking = (n: number, forScope: string) => {
    const base = inFlightRef.current.scope === forScope ? inFlightRef.current.chapters : new Set<number>();
    const next: MarkedChapters = { scope: forScope, chapters: new Set(base).add(n) };
    inFlightRef.current = next;
    setInFlight(next);
  };

  // Drops a request from the in-flight chapters once it has settled; nothing to do once the reader has left its novel or source
  const finishMarking = (n: number, forScope: string) => {
    if (inFlightRef.current.scope !== forScope || !inFlightRef.current.chapters.has(n)) return;
    const chapters = new Set(inFlightRef.current.chapters);
    chapters.delete(n);
    const next: MarkedChapters = { scope: forScope, chapters };
    inFlightRef.current = next;
    setInFlight(next);
  };

  // Records a chapter as read, unless the reader has left that novel or source meanwhile
  const addMarked = (n: number, forScope: string) => {
    if (scopeRef.current !== forScope) return;
    const base = markedRef.current.scope === forScope ? markedRef.current.chapters : new Set<number>();
    const next: MarkedChapters = { scope: forScope, chapters: new Set(base).add(n) };
    markedRef.current = next;
    setMarked(next);
  };

  // Automatic marking runs for signed-in users when the setting says so
  const isAutoMarkEnabled = isAuthenticated &&
    (markReadBehavior === 'automatic' || markReadBehavior === 'buttonAutomatic');

  // The "mark as read" button shows for signed-in users when the setting says so
  const showMarkReadButton = isAuthenticated &&
    (markReadBehavior === 'button' || markReadBehavior === 'buttonAutomatic');

  // Mark the chapter as read once the reader reaches its end, so the last
  // chapter (which has no "next" to navigate to) is recorded too
  useEffect(() => {
    if (!isAutoMarkEnabled || loading || !chapter ||
        !novelSlug || !sourceSlug || !chapterNumber ||
        isMarked(parseInt(chapterNumber))) return;
    const endElement = endOfChapterRef.current;
    if (!endElement) return;

    const key = currentChapterKey;
    const number = parseInt(chapterNumber);
    const stop = () => {
      observer.disconnect();
      window.removeEventListener('scroll', checkEndReached);
    };
    // Checked on both visibility changes and scrolls: the end can already be on
    // screen while the scroll guard below still holds, and the observer would
    // not fire again until it leaves and re-enters the viewport
    const checkEndReached = () => {
      // Right after a route change the previous chapter is still on screen
      if (loadedChapterKeyRef.current !== key || isBusy(number)) return;
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
      startMarking(number, scope);
      userService.markChapterAsRead(novelSlug, sourceSlug, number)
        .then(() => {
          addMarked(number, scope);
          stop();
        })
        .catch((error) => {
          console.error('Error automatically marking chapter as read:', error);
        })
        .finally(() => {
          finishMarking(number, scope);
        });
    };
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) checkEndReached();
    });
    observer.observe(endElement);
    window.addEventListener('scroll', checkEndReached, { passive: true });
    return stop;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- novelSlug, sourceSlug and chapterNumber are encoded in currentChapterKey
  }, [isAutoMarkEnabled, loading, chapter, currentChapterKey]);

  // Automatic marking when leaving the chapter before its end was reached
  const markBeforeLeaving = async () => {
    if (isAutoMarkEnabled &&
        chapterNumber &&
        novelSlug &&
        sourceSlug &&
        !isBusy(parseInt(chapterNumber))) {
      const number = parseInt(chapterNumber);
      startMarking(number, scope);
      try {
        await userService.markChapterAsRead(novelSlug, sourceSlug, number);
        addMarked(number, scope);
      } catch (error) {
        console.error('Error automatically marking chapter as read:', error);
      } finally {
        finishMarking(number, scope);
      }
    }
  };

  // Marks a chapter of the reader's novel as read, by hand
  const markChapter = async (n: number) => {
    if (!novelSlug || !sourceSlug || !isAuthenticated || isBusy(n)) return;

    startMarking(n, scope);
    try {
      await userService.markChapterAsRead(novelSlug, sourceSlug, n);
      addMarked(n, scope);
      notify({ message: t('reader.markedRead'), severity: 'success', duration: 3000 });
    } catch (error) {
      console.error('Error marking chapter as read:', error);
    } finally {
      finishMarking(n, scope);
    }
  };

  // Function to mark the current chapter as read
  const handleMarkAsRead = () => {
    if (!novelSlug || !sourceSlug || !chapterNumber || !isAuthenticated) return;
    void markChapter(parseInt(chapterNumber));
  };

  const currentNumber = parseInt(chapterNumber ?? '');

  return {
    markingAsRead: markingChapters.has(currentNumber),
    markReadSuccess: markedChapters.has(currentNumber),
    showMarkReadButton,
    handleMarkAsRead,
    markBeforeLeaving,
    markedChapters,
    markingChapters,
    markChapter,
  };
}

