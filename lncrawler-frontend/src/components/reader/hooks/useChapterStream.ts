import { useCallback, useEffect, useReducer, useRef } from 'react';
import type { ChapterContent } from '@models/novels_types';
import { handleChapterFailure } from './chapterErrors';
import { sectionKeyOf } from './chapterRange';
import { chapterStreamReducer, initialStreamState, nextStep, type ChapterStreamAction } from './chapterStream';

interface ChapterStreamOptions {
  // readingMode === 'infinite'
  enabled: boolean;
  // The chapter from the route
  anchor: ChapterContent | null;
  // Bumped by the loader on each real load; an in-place switch to a chapter on the page keeps it
  loadId: number;
  fetchChapterContent: (novel: string, source: string, n: number) => Promise<ChapterContent>;
}

export type ChapterStream = ReturnType<typeof useChapterStream>;

// The chapters after the route's one, loaded one at a time while the reader scrolls
export function useChapterStream({ enabled, anchor, loadId, fetchChapterContent }: ChapterStreamOptions) {
  const [state, dispatch] = useReducer(chapterStreamReducer, initialStreamState);
  // Kept in step with every dispatch, so a second call before a render sees the first one
  const stateRef = useRef(initialStreamState);
  // Bumped on every reset, so results of an older stream are dropped
  const generationRef = useRef(0);

  const dispatchAction = useCallback((action: ChapterStreamAction) => {
    stateRef.current = chapterStreamReducer(stateRef.current, action);
    dispatch(action);
  }, []);

  const anchorId = anchor ? sectionKeyOf(anchor) : null;
  useEffect(() => {
    // Turned off: a fetch still in flight must not append later
    if (!enabled) {
      generationRef.current++;
      dispatchAction({ type: 'cancel' });
      return;
    }
    if (!anchor) return;
    const sameLoad = stateRef.current.loadId === loadId;
    if (sameLoad && stateRef.current.chapters.some((chapter) => sectionKeyOf(chapter) === sectionKeyOf(anchor))) return;
    generationRef.current++;
    dispatchAction({ type: 'reset', anchor, loadId });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed by anchorId and loadId, so an in-place switch keeps the stream
  }, [enabled, anchorId, loadId, dispatchAction]);

  const loadMore = useCallback(async () => {
    if (!enabled) return;
    const step = nextStep(stateRef.current);
    if (!step) return;
    if (step.kind === 'last') {
      dispatchAction({ type: 'end', reason: 'last' });
      return;
    }
    if (step.kind === 'gap') {
      dispatchAction({ type: 'end', reason: 'gap', chapter: step.chapter });
      return;
    }

    const generation = generationRef.current;
    const chapters = stateRef.current.chapters;
    const last = chapters[chapters.length - 1];
    dispatchAction({ type: 'loadStart' });
    try {
      const chapter = await fetchChapterContent(last.novel_slug, last.source_slug, step.chapter);
      if (generation !== generationRef.current) return;
      // A payload for another chapter would be dropped by the reducer and stall the stream
      if (chapter.chapter_id !== step.chapter) {
        dispatchAction({ type: 'end', reason: 'error', chapter: step.chapter });
        return;
      }
      dispatchAction({ type: 'append', chapter });
      if (chapter.next_chapter) {
        fetchChapterContent(chapter.novel_slug, chapter.source_slug, chapter.next_chapter).catch((err) => {
          console.error(`Error preloading chapter ${chapter.next_chapter}:`, err);
        });
      }
    } catch (err) {
      if (generation !== generationRef.current) return;
      console.error('Error fetching chapter content:', err);
      handleChapterFailure(err, {
        dmca: () => dispatchAction({ type: 'end', reason: 'dmca', chapter: step.chapter }),
        unavailable: () => dispatchAction({ type: 'end', reason: 'unavailable', chapter: step.chapter }),
        other: () => dispatchAction({ type: 'end', reason: 'error', chapter: step.chapter }),
      });
    }
  }, [enabled, fetchChapterContent, dispatchAction]);

  const retry = useCallback(() => {
    dispatchAction({ type: 'retry' });
    return loadMore();
  }, [dispatchAction, loadMore]);

  // Drops the sections at the top of the page, so the list stays within its cap
  // Returns whether any chapter was dropped
  const trimTop = useCallback((count: number) => {
    const before = stateRef.current;
    dispatchAction({ type: 'trimTop', count });
    return stateRef.current !== before;
  }, [dispatchAction]);

  // A comment posted to a chapter of this novel: the sections on the page count it
  const bumpCommentCount = useCallback((novelSlug: string, chapterNumber: number) => {
    dispatchAction({ type: 'bumpComment', chapterNumber, novelSlug });
  }, [dispatchAction]);

  // Off, or before the reset to a new route chapter has run, the stream shows only the route's chapter
  const current = enabled && anchor != null && state.loadId === loadId
    && state.chapters.some((chapter) => sectionKeyOf(chapter) === sectionKeyOf(anchor));
  const view = current ? state : initialStreamState;
  return {
    chapters: current ? state.chapters : (anchor ? [anchor] : []),
    loading: view.loading,
    end: view.end,
    endChapter: view.endChapter,
    loadMore,
    retry,
    trimTop,
    bumpCommentCount,
  };
}
