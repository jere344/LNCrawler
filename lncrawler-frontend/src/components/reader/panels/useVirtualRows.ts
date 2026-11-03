import { useCallback, useLayoutEffect, useState, type RefObject } from 'react';

// Rows rendered beyond each edge of the viewport, so a short scroll shows no gap
const OVERSCAN = 10;

// The rows to render for a scrolled list of fixed-height rows: the first row in view, and the range [start, end)
export function rowWindow(scrollTop: number, height: number, rowCount: number, rowHeight: number)
  : { top: number; start: number; end: number } {
  const top = rowCount === 0 ? 0 : Math.min(Math.max(Math.floor(scrollTop / rowHeight), 0), rowCount - 1);
  const bottom = Math.ceil((scrollTop + height) / rowHeight);
  const start = Math.min(Math.max(top - OVERSCAN, 0), rowCount);
  const end = Math.min(Math.max(bottom + OVERSCAN, 0), rowCount);
  return { top, start, end };
}

// The rows to render for a scrolled list of fixed-height rows, as rowWindow gives them, and a sync after the caller moves the list
export function useVirtualRows(listRef: RefObject<HTMLElement | null>, rowCount: number, rowHeight: number)
  : { top: number; start: number; end: number; sync: () => void } {
  const [metrics, setMetrics] = useState({ scrollTop: 0, height: 0 });

  // Reads the list's position; callers use it after they move the list themselves
  const sync = useCallback(() => {
    const list = listRef.current;
    if (!list) return;
    const { scrollTop, clientHeight } = list;
    setMetrics((previous) =>
      previous.scrollTop === scrollTop && previous.height === clientHeight
        ? previous
        : { scrollTop, height: clientHeight });
  }, [listRef]);

  // Measures before the first paint, then follows scrolls (one frame at a time) and size changes
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    sync();
    let frame = 0;
    const onScroll = () => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        frame = 0;
        sync();
      });
    };
    const resizeObserver = new ResizeObserver(sync);
    list.addEventListener('scroll', onScroll, { passive: true });
    resizeObserver.observe(list);
    return () => {
      list.removeEventListener('scroll', onScroll);
      resizeObserver.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [listRef, sync]);

  return { ...rowWindow(metrics.scrollTop, metrics.height, rowCount, rowHeight), sync };
}
