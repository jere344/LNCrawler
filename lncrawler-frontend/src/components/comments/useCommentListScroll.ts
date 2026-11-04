import { useEffect, useRef, useState, type RefObject } from 'react';
import type { Comment } from '@models/comments_types';
import { scrollToComment } from './commentScroll';

// How long a posted comment stays highlighted, in ms
export const HIGHLIGHT_MS = 1800;
// Room kept above a comment that is scrolled to, so its top edge is not under the list's edge
const SCROLL_MARGIN = 16;

// A posted comment is scrolled to once it is rendered, and highlighted for a moment. The page behind does not move when the comments have their own scroll.
export function useCommentListScroll(scrollRef: RefObject<HTMLDivElement | null> | undefined, roots: Comment[], threads: string[]) {
  const [highlightId, setHighlightId] = useState<string | null>(null);
  // The comment to scroll to once it is rendered
  const pendingScroll = useRef<string | null>(null);

  useEffect(() => {
    const id = pendingScroll.current;
    if (!id) return;
    const scroller = scrollRef?.current ?? null;
    const target = document.getElementById(`comment-${id}`);
    if (!target || (scroller && !scroller.contains(target))) return;
    pendingScroll.current = null;
    scrollToComment(scroller, target, SCROLL_MARGIN);
  }, [scrollRef, roots, threads, highlightId]);

  // The highlight is kept for a moment, then the comment is no longer marked
  useEffect(() => {
    if (!highlightId) return;
    const timer = window.setTimeout(() => {
      pendingScroll.current = null;
      setHighlightId(null);
    }, HIGHLIGHT_MS);
    return () => window.clearTimeout(timer);
  }, [highlightId]);

  // Marks a comment to be scrolled to and highlighted
  const highlight = (id: string) => {
    pendingScroll.current = id;
    setHighlightId(id);
  };

  return { highlightId, highlight };
}
