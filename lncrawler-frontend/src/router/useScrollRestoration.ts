import { useLayoutEffect, useRef } from 'react';
import { useLocation, useMatches, useNavigationType } from 'react-router-dom';

// Content of a page that came back (reviews, comments, images) often arrives after the first render, so a single restore is clamped to a shorter page. The retry waits for it, and gives up once the user scrolls.
const RESTORE_TIMEOUT_MS = 3000;
const USER_INPUT_EVENTS = ['wheel', 'touchstart', 'keydown', 'mousedown'] as const;

// The browser's own restore fires before our content exists and lands in the wrong place.
window.history.scrollRestoration = 'manual';

// Scroll position of each history entry, by location.key. Kept in sessionStorage
// across a reload, since manual mode turns off the browser's own restore on F5.
const STORAGE_KEY = 'scroll-positions';
const STORED_POSITIONS = 50;
const scrollPositions = (() => {
  try {
    return new Map<string, number>(JSON.parse(sessionStorage.getItem(STORAGE_KEY) ?? '[]'));
  } catch {
    return new Map<string, number>();
  }
})();

// Scrolls to `target` now, then again on each resize of the page until it is tall enough.
// Returns the cleanup that stops the retry.
const restoreScroll = (target: number): (() => void) => {
  const scrollToTarget = () => window.scrollTo({ top: target, left: 0, behavior: 'instant' });
  const isTallEnough = () => document.documentElement.scrollHeight - window.innerHeight >= target;

  scrollToTarget();
  if (isTallEnough()) return () => {};

  const stop = () => {
    observer.disconnect();
    window.clearTimeout(timer);
    USER_INPUT_EVENTS.forEach((type) => window.removeEventListener(type, stop));
  };
  const observer = new ResizeObserver(() => {
    scrollToTarget();
    if (isTallEnough()) stop();
  });
  const timer = window.setTimeout(stop, RESTORE_TIMEOUT_MS);
  observer.observe(document.body);
  USER_INPUT_EVENTS.forEach((type) => window.addEventListener(type, stop, { passive: true }));
  return stop;
};

export const useScrollRestoration = () => {
  const location = useLocation();
  const navigationType = useNavigationType();
  const previousPath = useRef<string | null>(null);
  // Routes with `handle.ownScroll` (the chapter reader) restore their own position on back/forward.
  const ownsScroll = useMatches().some((match) => (match.handle as { ownScroll?: boolean } | undefined)?.ownScroll);

  // Remembers where the reader left the previous history entry, so back/forward can
  // return to it. Read while rendering the new location: the old page is still on
  // screen until the commit, whose DOM swap would clamp or reset scrollY.
  const shownKey = useRef(location.key);
  if (shownKey.current !== location.key) scrollPositions.set(shownKey.current, window.scrollY);
  useLayoutEffect(() => {
    shownKey.current = location.key;
    const persist = () => {
      scrollPositions.set(location.key, window.scrollY);
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...scrollPositions].slice(-STORED_POSITIONS)));
      } catch {
        // Storage unavailable (private mode, quota): the position just isn't kept across a reload.
      }
    };
    window.addEventListener('pagehide', persist);
    return () => window.removeEventListener('pagehide', persist);
  }, [location.key]);

  useLayoutEffect(() => {
    const path = location.pathname + location.search;
    const pathChanged = previousPath.current !== path;
    previousPath.current = path;

    if (navigationType === 'POP') {
      if (ownsScroll) {
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        return;
      }
      const saved = scrollPositions.get(location.key);
      // An anchor on first load wins over the browser's default position.
      if (saved === undefined && location.hash) return;
      return restoreScroll(saved ?? 0);
    }

    // Filters that keep the reader in place pass `keepScroll` in the navigation state.
    if (!pathChanged || location.hash || (location.state as { keepScroll?: boolean } | null)?.keepScroll) return;
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
  }, [location, navigationType, ownsScroll]);
};
