import { useEffect } from 'react';

// Stops the page behind a panel from scrolling while the panel is open
export function useDocumentScrollLock(active: boolean): void {
  useEffect(() => {
    if (!active) return;
    const previous = document.documentElement.style.overflow;
    document.documentElement.style.overflow = 'hidden';
    return () => {
      document.documentElement.style.overflow = previous;
    };
  }, [active]);
}
