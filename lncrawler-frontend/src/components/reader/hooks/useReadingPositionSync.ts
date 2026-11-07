import { useEffect, useRef, useState } from 'react';
import { userService } from '../../../services/api';
import type { ChapterContent as IChapterContent } from '@models/novels_types';
import { chapterRange, sectionKeyOf } from './chapterRange';
import {
  createPositionQueue,
  isScrollKey,
  isScrollable,
  isTypingTarget,
  readProgress,
  recordPositionSaved,
  reportSaveError,
  saveStateFor,
  shouldSavePosition,
  type ChapterSaveState,
  type NavigationTarget,
} from './readingPositionSync';

interface ReadingPositionSyncOptions {
  // Signed-in users only: guests send nothing
  enabled: boolean;
  // The chapter on screen; null while it loads
  chapter: IChapterContent | null;
  loading: boolean;
  // Bumped by the loader on each real load; an in-place switch keeps it
  loadId: number;
  // Infinite mode: the position is measured in the chapter's section
  infinite: boolean;
}

// Sends the reading position of a signed-in user. The decisions are in readingPositionSync.ts.
export function useReadingPositionSync({ enabled, chapter, loading, loadId, infinite }: ReadingPositionSyncOptions) {
  // Latest inputs for the listeners and callbacks, which can outlive a render
  const latest = useRef({ enabled, chapter, loading, infinite });
  latest.current = { enabled, chapter, loading, infinite };

  // Whether the user has scrolled the chapter on screen since it was loaded
  const engagedRef = useRef(false);
  // Save pacing of the chapter last saved
  const saveStateRef = useRef<ChapterSaveState | null>(null);
  // Last position measured while the chapter was on screen. Leaving sends it instead of measuring
  // again, since by then the page may be gone and would read as finished.
  const lastMeasureRef = useRef<{ key: string; progress: number } | null>(null);

  // Measures the chapter on screen (its section in infinite mode) and remembers the result
  const [measure] = useState(() => (chapter: IChapterContent, infinite: boolean): number => {
    const key = sectionKeyOf(chapter);
    const progress = readProgress(chapterRange(infinite ? key : null), window.scrollY);
    lastMeasureRef.current = { key, progress };
    return progress;
  });

  const [queue] = useState(() => createPositionQueue(
    (target) => userService.saveReadingPosition(target.novelSlug, target.sourceSlug, target.chapterNumber, target.progress),
    reportSaveError,
  ));

  // The position of the chapter on screen, with keepalive: the request outlives the page or the navigation.
  // It replaces any payload still waiting, which is older.
  const [flushOnLeave] = useState(() => (): void => {
    const { enabled, chapter, loading } = latest.current;
    if (!enabled || loading || !chapter || !engagedRef.current) return;
    const last = lastMeasureRef.current;
    if (!last || last.key !== sectionKeyOf(chapter)) return;
    const progress = last.progress;
    queue.drop();
    userService.saveReadingPosition(chapter.novel_slug, chapter.source_slug, chapter.chapter_id, progress, { keepalive: true })
      .catch(reportSaveError);
  });

  // A save point of the reader's scroll: sent when the chapter is engaged and the pacing allows it
  const [onPositionSaved] = useState(() => (): void => {
    const { enabled, chapter, loading, infinite } = latest.current;
    if (!enabled || loading || !chapter || !engagedRef.current) return;
    const now = Date.now();
    const progress = measure(chapter, infinite);
    const state = saveStateFor(saveStateRef.current, sectionKeyOf(chapter));
    if (!shouldSavePosition(state, progress, now)) {
      saveStateRef.current = state;
      return;
    }
    saveStateRef.current = recordPositionSaved(state, progress, now);
    queue.push({
      novelSlug: chapter.novel_slug,
      sourceSlug: chapter.source_slug,
      chapterNumber: chapter.chapter_id,
      progress,
    });
  });

  // Only the user's own scrolling counts: scroll events also come from restoring the position and from infinite-mode jumps
  useEffect(() => {
    const engage = () => {
      engagedRef.current = true;
    };
    // Keeps the last measure current between save points, for the position sent on leaving
    const onScroll = () => {
      const { enabled, chapter, loading, infinite } = latest.current;
      if (enabled && !loading && chapter && engagedRef.current) measure(chapter, infinite);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    const engageOnScrollKey = (event: KeyboardEvent) => {
      if (isScrollKey(event.key) && !isTypingTarget(event.target)) engage();
    };
    window.addEventListener('wheel', engage, { passive: true });
    window.addEventListener('touchmove', engage, { passive: true });
    window.addEventListener('keydown', engageOnScrollKey);
    return () => {
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('wheel', engage);
      window.removeEventListener('touchmove', engage);
      window.removeEventListener('keydown', engageOnScrollKey);
    };
  }, [measure]);

  // A new load starts unengaged and unmeasured. An infinite-mode switch in place keeps the scroll that caused it.
  useEffect(() => {
    engagedRef.current = false;
    lastMeasureRef.current = null;
  }, [loadId]);

  // A chapter too short to scroll counts as engaged once it is shown, and its position goes out right away
  useEffect(() => {
    if (loading || !chapter || isScrollable(document.documentElement)) return;
    engagedRef.current = true;
    onPositionSaved();
  }, [loading, chapter, onPositionSaved]);

  // Moving to another chapter (Next, Prev, the chapter list, TTS or an unavailable chapter): the destination is recorded at its start, and the chapter left is not
  const onNavigate = ({ novelSlug, sourceSlug, chapterNumber }: NavigationTarget) => {
    if (!latest.current.enabled || !novelSlug || !sourceSlug) return;
    queue.push({ novelSlug, sourceSlug, chapterNumber, progress: 0 });
  };

  // Infinite mode: the reading line moved into another section, which is recorded at its current progress
  const onSectionActive = (section: IChapterContent) => {
    if (!latest.current.enabled || !engagedRef.current) return;
    const key = sectionKeyOf(section);
    const progress = measure(section, true);
    saveStateRef.current = recordPositionSaved(saveStateFor(saveStateRef.current, key), progress, Date.now());
    queue.push({
      novelSlug: section.novel_slug,
      sourceSlug: section.source_slug,
      chapterNumber: section.chapter_id,
      progress,
    });
  };

  // Leaving: on hide, on page exit, and when the reader unmounts (a header link, back). The position goes with keepalive.
  useEffect(() => {
    const onVisibilityChange = () => {
      if (document.visibilityState === 'hidden') flushOnLeave();
    };
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', flushOnLeave);
    return () => {
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', flushOnLeave);
      flushOnLeave();
    };
  }, [flushOnLeave]);

  return { onPositionSaved, onNavigate, onSectionActive, onLeave: flushOnLeave };
}
