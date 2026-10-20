import { useRef, useEffect } from 'react';

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
  
  // Calculate scroll position as a percentage of total scrollable height
  const calculateScrollPercentage = (): number => {
    const scrollTop = window.scrollY;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;
    
    // If there's nothing to scroll, return 0
    if (scrollHeight <= clientHeight) return 0;
    
    // Calculate how far we've scrolled as a percentage
    const scrollableHeight = scrollHeight - clientHeight;
    return (scrollTop / scrollableHeight) * 100;
  };

  // Save current reading position (percentage of the chapter) with throttling.
  // Both page mode and text mode store the same metric, so switching between
  // them or rotating the device restores the same place in the text.
  const saveScrollPosition = (force = false) => {
    if (!currentChapterKey || !savePosition) return;
    
    const now = Date.now();
    // Throttle saves to avoid excessive writes (page turns and unmounts force)
    if (!force && now - lastScrollSaveRef.current < SCROLL_SAVE_THROTTLE) {
      return;
    }
    lastScrollSaveRef.current = now;

    const percentage = calculateScrollPercentage();

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

  // Restore the text-mode window scroll from the saved percentage.
  const restoreScrollPosition = (attempt = 0) => {
    if (!currentChapterKey || !savePosition) return;
    
    const savedPercentage = scrollPositionsRef.current[currentChapterKey];
    if (savedPercentage === undefined) return;

    // Use requestAnimationFrame to avoid layout thrashing
    requestAnimationFrame(() => {
      // Read scroll dimensions
      const scrollHeight = document.documentElement.scrollHeight;
      const clientHeight = document.documentElement.clientHeight;
      const scrollableHeight = scrollHeight - clientHeight;
      
      if (scrollableHeight <= 0) {
        // Try again later if content hasn't fully rendered, but stop after a
        // bounded number of attempts so this can't loop forever.
        if (attempt >= MAX_SCROLL_RESTORE_RETRIES) return;
        scrollRestoreTimeoutRef.current = window.setTimeout(
          () => restoreScrollPosition(attempt + 1),
          100,
        );
        return;
      }
      
      const scrollTop = (savedPercentage / 100) * scrollableHeight;
      
      // Write to scroll position in next frame
      requestAnimationFrame(() => {
        window.scrollTo({
          top: scrollTop,
          behavior: 'auto' // Use 'auto' instead of 'smooth' to avoid animation issues
        });
      });
    });
  };

  return { saveScrollPosition, restoreScrollPosition, scrollRestoreTimeoutRef };
}
