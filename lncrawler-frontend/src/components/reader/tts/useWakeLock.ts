import { useRef, type RefObject } from 'react';
import type { UseTtsPlayerArgs } from './useTtsPlayer';

export function useWakeLock(argsRef: RefObject<UseTtsPlayerArgs>) {
  const wakeLockRef = useRef<{ release: () => Promise<void> } | null>(null);

  const releaseWakeLock = () => {
    wakeLockRef.current?.release().catch(() => undefined);
    wakeLockRef.current = null;
  };
  const acquireWakeLock = async () => {
    if (!argsRef.current.prefs.ttsKeepScreenOn || wakeLockRef.current) return;
    const wl = (navigator as Navigator & { wakeLock?: { request: (t: 'screen') => Promise<{ release: () => Promise<void> }> } }).wakeLock;
    if (!wl || document.visibilityState !== 'visible') return;
    try {
      wakeLockRef.current = await wl.request('screen');
    } catch {
      wakeLockRef.current = null;
    }
  };

  return { acquireWakeLock, releaseWakeLock };
}
