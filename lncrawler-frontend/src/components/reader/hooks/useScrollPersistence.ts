import { useRef, useEffect } from 'react';
import { chapterRange, progressIn, scrollYFor } from './chapterRange';

// Interface for scroll position storage
interface ScrollPositions {
  [key: string]: number; // Value is percentage of total scrollable height
}

const MAX_STORED_POSITIONS = 20; // Maximum number of scroll positions to store
const SCROLL_POSITION_STORAGE_KEY = 'lncrawler_scroll_positions';
export const SCROLL_SAVE_THROTTLE = 1000; // Save scroll position at most every 1000ms
const MAX_SCROLL_RESTORE_RETRIES = 20; // ~2s of retries before giving up on scroll restore

export function useScrollPersistence({
  currentChapterKey,
  savePosition,
}: {
  currentChapterKey: string;
  savePosition: boolean;
}) {
  // Mirror of scroll positions for use inside callbacks/cleanups
  const scrollPositionsRef = useRef<ScrollPositions>({});

  // Pending scroll-restore retry timer, cleared on chapter change/unmount
  const scrollRestoreTimeoutRef = useRef<number | null>(null);

  // Animation frame of the restore still queued, cancelled with the retry timer
  const restoreFrameRef = useRef<number | null>(null);

  // Load saved scroll positions from localStorage
  useEffect(() => {
    try {
      const savedPositions = localStorage.getItem(SCROLL_POSITION_STORAGE_KEY);
      if (savedPositions) {
        const parsed = JSON.parse(savedPositions);
        scrollPositionsRef.current = parsed;
      }
    } catch (error) {
      console.error('Error loading saved scroll positions:', error);
    }
  }, []);

  // Add a ref to track the last time we saved the scroll position
  const lastScrollSaveRef = useRef<number>(0);
  
  // Scroll position as a percentage of the chapter's scrollable height (its section in infinite mode)
  const calculateScrollPercentage = (sectionKey: string | null): number => {
    const range = chapterRange(sectionKey);
    if (!range) return 0;
    return progressIn(range, window.scrollY) * 100;
  };

  // Save current reading position (percentage of the chapter) with throttling.
  // Both page mode and text mode store the same metric, so switching between
  // them or rotating the device restores the same place in the text.
  // sectionKey is the section the chapter's text is on screen as, null for the whole document
  const saveScrollPosition = (sectionKey: string | null, force = false) => {
    if (!currentChapterKey || !savePosition) return;
    
    const now = Date.now();
    // Throttle saves to avoid excessive writes (page turns and unmounts force)
    if (!force && now - lastScrollSaveRef.current < SCROLL_SAVE_THROTTLE) {
      return;
    }
    lastScrollSaveRef.current = now;

    const percentage = calculateScrollPercentage(sectionKey);

    // Re-insert the current key last so it is the most recently used; pruning
    // below then evicts the genuinely least-recently-read chapter, not merely
    // the one inserted earliest.
    const updatedPositions: ScrollPositions = { ...scrollPositionsRef.current };
    delete updatedPositions[currentChapterKey];
    updatedPositions[currentChapterKey] = percentage;
    
    // Prune old entries if we have too many
    const keys = Object.keys(updatedPositions);
    if (keys.length > MAX_STORED_POSITIONS) {
      // Remove the oldest entries
      const keysToRemove = keys.slice(0, keys.length - MAX_STORED_POSITIONS);
      keysToRemove.forEach(key => {
        delete updatedPositions[key];
      });
    }
    
    // Save to the ref and localStorage
    scrollPositionsRef.current = updatedPositions;
    try {
      // Use requestAnimationFrame to batch DOM reads/writes
      requestAnimationFrame(() => {
        localStorage.setItem(SCROLL_POSITION_STORAGE_KEY, JSON.stringify(updatedPositions));
      });
    } catch (error) {
      console.error('Error saving scroll position to localStorage:', error);
    }
  };

  // Stops a restore that is still queued: its retry timer and its frame
  const cancelRestore = () => {
    if (scrollRestoreTimeoutRef.current !== null) {
      clearTimeout(scrollRestoreTimeoutRef.current);
      scrollRestoreTimeoutRef.current = null;
    }
    if (restoreFrameRef.current !== null) {
      cancelAnimationFrame(restoreFrameRef.current);
      restoreFrameRef.current = null;
    }
  };

  // Restore the text-mode window scroll from the saved percentage, in the section of the chapter being restored (null for the whole document).
  const restoreScrollPosition = (sectionKey: string | null, attempt = 0) => {
    if (!currentChapterKey || !savePosition) return;
    
    const savedPercentage = scrollPositionsRef.current[currentChapterKey];
    if (savedPercentage === undefined) return;

    // Use requestAnimationFrame to avoid layout thrashing
    restoreFrameRef.current = requestAnimationFrame(() => {
      restoreFrameRef.current = null;
      // Read the chapter's range (its section in infinite mode)
      const range = chapterRange(sectionKey);

      if (!range || range.length <= 0) {
        // Try again later if content hasn't fully rendered, but stop after a
        // bounded number of attempts so this can't loop forever.
        if (attempt >= MAX_SCROLL_RESTORE_RETRIES) return;
        scrollRestoreTimeoutRef.current = window.setTimeout(
          () => restoreScrollPosition(sectionKey, attempt + 1),
          100,
        );
        return;
      }

      const scrollTop = scrollYFor(range, savedPercentage / 100);
      
      // Write to scroll position in next frame
      restoreFrameRef.current = requestAnimationFrame(() => {
        restoreFrameRef.current = null;
        window.scrollTo({
          top: scrollTop,
          behavior: 'auto' // Use 'auto' instead of 'smooth' to avoid animation issues
        });
      });
    });
  };

  return { saveScrollPosition, restoreScrollPosition, cancelRestore };
}
