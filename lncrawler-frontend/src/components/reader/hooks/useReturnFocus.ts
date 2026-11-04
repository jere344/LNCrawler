import { useEffect, type RefObject } from 'react';

// Moves focus to the target when the panel opens, and back to the element that had it when the panel closes.
// With nothing focused (a shortcut pressed over the text) focus is left alone.
export function useReturnFocus(targetRef: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const active = document.activeElement;
    const opener = active instanceof HTMLElement && active !== document.body ? active : null;
    if (opener) targetRef.current?.focus({ preventScroll: true });
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, [targetRef]);
}
