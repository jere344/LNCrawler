import { useCallback, useEffect, useState } from 'react';

// Fullscreen with the WebKit names, which Safari on iPad still uses
type FullscreenElement = HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void };
type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element | null;
  webkitExitFullscreen?: () => Promise<void> | void;
};

// An installed web app already runs without browser chrome, so there is nothing to expand
const isStandalone = (): boolean =>
  typeof window.matchMedia === 'function' && window.matchMedia('(display-mode: standalone)').matches;

const getSupported = (): boolean => {
  const root = document.documentElement as FullscreenElement;
  const hasApi = typeof root.requestFullscreen === 'function' || typeof root.webkitRequestFullscreen === 'function';
  return hasApi && !isStandalone();
};

const isFullscreenNow = (): boolean => {
  const doc = document as FullscreenDocument;
  return Boolean(doc.fullscreenElement || doc.webkitFullscreenElement);
};

// Whole-page fullscreen on the document root. `supported` is false where the API is missing or the app is installed.
export function useFullscreen() {
  const [supported] = useState(getSupported);
  const [active, setActive] = useState(isFullscreenNow);

  useEffect(() => {
    if (!supported) return;
    const sync = () => setActive(isFullscreenNow());
    document.addEventListener('fullscreenchange', sync);
    document.addEventListener('webkitfullscreenchange', sync);
    return () => {
      document.removeEventListener('fullscreenchange', sync);
      document.removeEventListener('webkitfullscreenchange', sync);
    };
  }, [supported]);

  const toggle = useCallback(() => {
    if (!supported) return;
    const doc = document as FullscreenDocument;
    const root = document.documentElement as FullscreenElement;
    const request = isFullscreenNow()
      ? (doc.exitFullscreen ? doc.exitFullscreen() : doc.webkitExitFullscreen?.())
      : (root.requestFullscreen ? root.requestFullscreen() : root.webkitRequestFullscreen?.());
    // A refused request (no user gesture, or the platform says no) leaves the state as it was
    if (request instanceof Promise) request.catch(() => undefined);
  }, [supported]);

  return { supported, active, toggle };
}
