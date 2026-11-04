import { useLayoutEffect, useRef, useState, type FocusEvent, type KeyboardEvent, type RefObject } from 'react';
import { ROW_HEIGHT } from './ChapterRow';

// Roving focus over the rows of a list: one row is in the tab order, and the arrow, page, Home and End keys move the focus between rows
export function useRovingRows(listRef: RefObject<HTMLElement | null>, rowCount: number, sync: () => void, fallback: number) {
  // The row the focus moved to last; until then the fallback row is the one in the tab order
  const [focused, setFocused] = useState<number | null>(null);
  const active = focused ?? fallback;
  // The row element focused last, to notice when it is replaced
  const focusedRow = useRef<HTMLElement | null>(null);
  // The row to focus after the next render
  const wantFocus = useRef<number | null>(null);

  // After each render: a focused skeleton is replaced by a row when its page arrives, which takes the focus with it, so the row at its index gets it back
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (focusedRow.current && !focusedRow.current.isConnected) {
      focusedRow.current = null;
      wantFocus.current = focused;
    }
    const index = wantFocus.current;
    wantFocus.current = null;
    const row = index === null ? null : list.querySelector<HTMLElement>(`[data-index="${index}"]`);
    if (!row) return;
    row.focus();
    // Kept here as well as on focus: no focus event fires while the window itself is not focused
    focusedRow.current = row;
  });

  // A row that takes the focus, by click or by key, is the one in the tab order from then on
  const onFocus = (event: FocusEvent<HTMLElement>) => {
    const row = event.target as HTMLElement;
    if (row.dataset.index === undefined) return;
    focusedRow.current = row;
    setFocused(Number(row.dataset.index));
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const list = listRef.current;
    if (!list || rowCount === 0) return;
    // A page is a screen of rows, less one so the last row stays in view
    const pageRows = Math.max(1, Math.floor(list.clientHeight / ROW_HEIGHT) - 1);
    const moves: Record<string, number | undefined> = {
      ArrowDown: active + 1,
      ArrowUp: active - 1,
      PageDown: active + pageRows,
      PageUp: active - pageRows,
      Home: 0,
      End: rowCount - 1,
    };
    const move = moves[event.key];
    if (move === undefined) return;
    event.preventDefault();
    const index = Math.min(Math.max(move, 0), rowCount - 1);
    if (index === active) return;
    // Scrolls the row into view when it is outside the viewport
    const rowTop = index * ROW_HEIGHT;
    if (rowTop < list.scrollTop) list.scrollTop = rowTop;
    else if (rowTop + ROW_HEIGHT > list.scrollTop + list.clientHeight) list.scrollTop = rowTop + ROW_HEIGHT - list.clientHeight;
    sync();
    wantFocus.current = index;
    setFocused(index);
  };

  return { active, onFocus, onKeyDown };
}
