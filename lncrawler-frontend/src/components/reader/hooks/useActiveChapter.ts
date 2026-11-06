import { useEffect, useRef } from 'react';
import { pickActiveSection, READING_LINE, type SectionBounds } from './activeSection';

// Reports the chapter section under the reading line while the page scrolls
export function useActiveChapter(enabled: boolean, chapterCount: number, onChange: (key: string) => void): void {
  // Kept current so the listeners below are not re-subscribed on every render
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  // Last key reported, so the callback only fires when the active section changes
  const lastKeyRef = useRef<string | null>(null);

  useEffect(() => {
    if (!enabled) lastKeyRef.current = null;
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return;

    const check = () => {
      const sections: SectionBounds[] = [];
      document.querySelectorAll<HTMLElement>('[data-chapter-key]').forEach((element) => {
        const rect = element.getBoundingClientRect();
        sections.push({ key: element.dataset.chapterKey ?? '', top: rect.top, bottom: rect.bottom });
      });
      const key = pickActiveSection(sections, window.innerHeight * READING_LINE);
      if (key === null || key === lastKeyRef.current) return;
      lastKeyRef.current = key;
      onChangeRef.current(key);
    };

    // One frame at a time: scroll events within a frame share a single check
    let frame: number | null = null;
    const schedule = () => {
      if (frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        check();
      });
    };

    // Once now, and again when sections are added to the page
    check();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    return () => {
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, [enabled, chapterCount]);
}
