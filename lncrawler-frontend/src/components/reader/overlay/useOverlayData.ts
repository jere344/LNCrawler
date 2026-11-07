import { useEffect, useState } from 'react';
import { chapterIndex, chapterListCache } from '../panels/chapterList';
import { chapterRange, pagesIn, percentIn } from '../hooks/chapterRange';

// Minimal shape of the Battery Status API, which only Chromium browsers ship
interface BatteryManager extends EventTarget {
  level: number;
  charging: boolean;
}

export interface BatteryState {
  percent: number;
  charging: boolean;
}

// The device battery, or null where the browser does not expose it (Firefox, Safari)
export function useBattery(enabled: boolean): BatteryState | null {
  const [state, setState] = useState<BatteryState | null>(null);

  useEffect(() => {
    const getBattery = (navigator as Navigator & { getBattery?: () => Promise<BatteryManager> }).getBattery;
    if (!enabled || !getBattery) return;
    let battery: BatteryManager | null = null;
    let cancelled = false;
    const update = () => {
      if (battery) setState({ percent: Math.round(battery.level * 100), charging: battery.charging });
    };
    getBattery.call(navigator).then((manager) => {
      if (cancelled) return;
      battery = manager;
      update();
      manager.addEventListener('levelchange', update);
      manager.addEventListener('chargingchange', update);
    }).catch(() => {});
    return () => {
      cancelled = true;
      battery?.removeEventListener('levelchange', update);
      battery?.removeEventListener('chargingchange', update);
    };
  }, [enabled]);

  return state;
}

// The clock, refreshed on the minute
export function useClock(enabled: boolean): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (!enabled) return;
    let timer: number;
    const tick = () => {
      const current = new Date();
      setNow(current);
      timer = window.setTimeout(tick, (60 - current.getSeconds()) * 1000 - current.getMilliseconds() + 50);
    };
    tick();
    return () => window.clearTimeout(timer);
  }, [enabled]);

  return now;
}

export interface ScrollProgress {
  percent: number;
  // Screens of text: the one in view, and how many the chapter takes
  page: number;
  pages: number;
}

const START: ScrollProgress = { percent: 0, page: 1, pages: 1 };

// How far the chapter (its section in infinite mode) is scrolled. Kept in its own state so the reader does not re-render on every scroll.
export function useScrollProgress(enabled: boolean, chapterId: number, sectionKey: string | null): ScrollProgress {
  const [progress, setProgress] = useState(START);

  useEffect(() => {
    if (!enabled) return;
    let frame: number | null = null;
    const update = () => {
      frame = null;
      const range = chapterRange(sectionKey);
      // The section is not on the page: the last value stays
      if (!range) return;
      const viewport = document.documentElement.clientHeight;
      const percent = Math.round(percentIn(range, window.scrollY));
      const { page, pages } = pagesIn(range, viewport, window.scrollY);
      setProgress((previous) =>
        previous.percent === percent && previous.page === page && previous.pages === pages ? previous : { percent, page, pages });
    };
    const handle = () => {
      if (frame === null) frame = window.requestAnimationFrame(update);
    };
    update();
    window.addEventListener('scroll', handle, { passive: true });
    window.addEventListener('resize', handle);
    // The text may still be laid out after the chapter id changes
    const settle = window.setTimeout(update, 400);
    return () => {
      window.removeEventListener('scroll', handle);
      window.removeEventListener('resize', handle);
      window.clearTimeout(settle);
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, [enabled, chapterId, sectionKey]);

  return progress;
}

export interface BookPosition {
  // 1-based position of the chapter in the whole list
  current: number;
  total: number;
}

// Where the chapter sits in the book, from the chapter list cache the reader already fills. Null until the list is known.
export function useBookPosition(
  enabled: boolean,
  novelSlug: string,
  sourceSlug: string,
  chapterId: number,
): BookPosition | null {
  const [found, setFound] = useState<{ chapterId: number; position: BookPosition } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    chapterListCache.load({ novelSlug, sourceSlug, around: chapterId }).then((data) => {
      const index = chapterIndex(data, chapterId);
      if (!cancelled && index !== null) setFound({ chapterId, position: { current: index + 1, total: data.count } });
    }).catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [enabled, novelSlug, sourceSlug, chapterId]);

  return found?.chapterId === chapterId ? found.position : null;
}
