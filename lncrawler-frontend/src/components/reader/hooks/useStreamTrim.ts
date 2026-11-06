import { useLayoutEffect, useRef } from 'react';
import type { ChapterContent } from '@models/novels_types';
import { sectionKeyOf } from './chapterRange';
import { MAX_STREAM_CHAPTERS, trimCount } from './chapterStream';

// A section measured before a trim, and where its text sat on screen
interface PendingTrim {
  key: string;
  top: number;
}

const sectionElement = (key: string) =>
  document.querySelector<HTMLElement>(`[data-chapter-key="${CSS.escape(key)}"]`);

// Keeps the infinite-scroll page to its last chapters, and holds the text on screen when sections above it go
export function useStreamTrim(
  enabled: boolean,
  chapters: ChapterContent[],
  protectedKeys: ReadonlySet<string>,
  // Returns whether the list changed
  trimTop: (count: number) => boolean,
): void {
  // Kept current so the effect below is not re-run for a new set with the same keys
  const protectedRef = useRef(protectedKeys);
  protectedRef.current = protectedKeys;
  const protectedKeysSignature = [...protectedKeys].sort().join('\n');
  const pendingRef = useRef<PendingTrim | null>(null);

  // Layout effects run before paint, and an update dispatched here re-renders before paint too,
  // so the measurement, the trim and the correction below all land in the same frame
  useLayoutEffect(() => {
    const pending = pendingRef.current;
    if (pending) {
      // The trimmed list is committed: the window moves by the shift of the first section kept
      pendingRef.current = null;
      const el = sectionElement(pending.key);
      const delta = el ? el.getBoundingClientRect().top - pending.top : 0;
      if (Math.abs(delta) >= 1) window.scrollTo({ top: window.scrollY + delta, left: 0, behavior: 'instant' });
      return;
    }
    if (!enabled) return;
    const count = trimCount(chapters, protectedRef.current, MAX_STREAM_CHAPTERS);
    const stays = chapters[count];
    if (count <= 0 || !stays) return;
    const el = sectionElement(sectionKeyOf(stays));
    // Only sections entirely above the view go, so nothing visible disappears and the scroll is never clamped
    if (!el || el.getBoundingClientRect().top > 0) return;
    pendingRef.current = { key: sectionKeyOf(stays), top: el.getBoundingClientRect().top };
    if (!trimTop(count)) pendingRef.current = null;
  }, [enabled, chapters, protectedKeysSignature, trimTop]);
}
