import { useEffect, useState } from 'react';

// Smaller differences are browser chrome sliding in and out, not a keyboard
const KEYBOARD_MIN_HEIGHT = 120;

// The part of the screen left to a panel while the on-screen keyboard is up
export interface KeyboardFrame {
  top: number;
  height: number;
}

interface VirtualKeyboardLike extends EventTarget {
  overlaysContent: boolean;
  boundingRect: { height: number };
}

const getVirtualKeyboard = () => (navigator as Navigator & { virtualKeyboard?: VirtualKeyboardLike }).virtualKeyboard;

// Measures the screen above the on-screen keyboard, or null when there is none. In fullscreen the keyboard covers the page
// without resizing it, and elsewhere the browser scrolls the visual viewport: both are read from the real viewports,
// and the browser is kept from moving the page itself so a panel can stay where it is.
export function useKeyboardAvoidance(active: boolean): KeyboardFrame | null {
  const [frame, setFrame] = useState<KeyboardFrame | null>(null);

  useEffect(() => {
    if (!active) return;
    const virtualKeyboard = getVirtualKeyboard();
    const viewport = window.visualViewport;
    const previousOverlay = virtualKeyboard?.overlaysContent ?? false;
    if (virtualKeyboard) virtualKeyboard.overlaysContent = true;

    const measure = () => {
      const top = viewport?.offsetTop ?? 0;
      let bottom = top + (viewport?.height ?? window.innerHeight);
      if (virtualKeyboard?.overlaysContent) bottom = Math.min(bottom, window.innerHeight - virtualKeyboard.boundingRect.height);
      const covered = window.innerHeight - bottom;
      setFrame((previous) => {
        if (covered < KEYBOARD_MIN_HEIGHT) return previous === null ? previous : null;
        if (previous && previous.top === top && previous.height === bottom - top) return previous;
        return { top, height: bottom - top };
      });
    };

    measure();
    viewport?.addEventListener('resize', measure);
    viewport?.addEventListener('scroll', measure);
    virtualKeyboard?.addEventListener('geometrychange', measure);
    window.addEventListener('resize', measure);
    return () => {
      viewport?.removeEventListener('resize', measure);
      viewport?.removeEventListener('scroll', measure);
      virtualKeyboard?.removeEventListener('geometrychange', measure);
      window.removeEventListener('resize', measure);
      if (virtualKeyboard) virtualKeyboard.overlaysContent = previousOverlay;
      setFrame(null);
    };
  }, [active]);

  return frame;
}
