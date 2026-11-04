import { useEffect, useLayoutEffect, useRef, type RefObject, type UIEvent } from 'react';
import { commentsTop, readScroll, writeScroll } from './commentScroll';

interface ThreadNavigationOptions {
  // The element the comments scroll in; the page scrolls when there is none
  scrollRef?: RefObject<HTMLDivElement | null>;
  // The comments' root: where a level starts on the page
  rootRef: RefObject<HTMLDivElement | null>;
  threadBackRef: RefObject<HTMLButtonElement | null>;
}

// Thread levels of the comments: each level keeps its scroll, and focus moves when the level changes
export function useThreadNavigation(threads: string[], { scrollRef, rootRef, threadBackRef }: ThreadNavigationOptions) {
  // Scroll position when each thread level was left, by the number of threads open at the time
  const scrollByLevel = useRef<number[]>([]);
  // The scroll position at its last change: the list has changed by the time a thread opens
  const lastScroll = useRef(0);
  const levelRef = useRef(threads.length);
  const threadsRef = useRef(threads);
  // Where focus goes after the level changed: the level now, and the thread closed when going back
  const pendingFocus = useRef<{ level: number; closed: string | null } | null>(null);

  // On the page, the window's scroll is followed, as a list's scroll event would be
  useEffect(() => {
    if (scrollRef) return;
    lastScroll.current = window.scrollY;
    const onScroll = () => {
      lastScroll.current = window.scrollY;
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [scrollRef]);

  // A level opened starts at the top, and going back returns to where it was left
  useLayoutEffect(() => {
    const scroller = scrollRef?.current ?? null;
    const previous = levelRef.current;
    const level = threads.length;
    levelRef.current = level;
    if (level === previous) {
      threadsRef.current = threads;
      return;
    }
    if (level > previous) {
      // The level left keeps the scroll; the levels saved above the new depth are no longer there
      scrollByLevel.current.length = level;
      scrollByLevel.current[previous] = lastScroll.current;
      writeScroll(scroller, commentsTop(scroller, rootRef.current));
    } else {
      writeScroll(scroller, scrollByLevel.current[level] ?? 0);
    }
    lastScroll.current = readScroll(scroller);
    // Read by the focus effect below, once the composer has settled its own focus
    pendingFocus.current = { level, closed: threadsRef.current[previous - 1] ?? null };
    threadsRef.current = threads;
  }, [threads, scrollRef, rootRef]);

  // Focus follows the level: the thread's back button, or on closing a thread its "Continue" button in the list
  useEffect(() => {
    const pending = pendingFocus.current;
    const scope = rootRef.current;
    if (!pending || !scope) return;
    pendingFocus.current = null;
    if (pending.level > 0) {
      threadBackRef.current?.focus({ preventScroll: true });
      return;
    }
    const continueButton = pending.closed
      ? scope.querySelector<HTMLElement>(`[data-thread-id="${CSS.escape(pending.closed)}"]`)
      : null;
    (continueButton ?? scrollRef?.current ?? scope).focus({ preventScroll: true });
  }, [threads, scrollRef, rootRef, threadBackRef]);

  const trackScroll = (event: UIEvent<HTMLDivElement>) => {
    lastScroll.current = event.currentTarget.scrollTop;
  };

  // The comments start again at the top
  const scrollToTop = () => {
    const scroller = scrollRef?.current ?? null;
    const top = commentsTop(scroller, rootRef.current);
    writeScroll(scroller, top);
    lastScroll.current = top;
  };

  return { trackScroll, scrollToTop };
}
