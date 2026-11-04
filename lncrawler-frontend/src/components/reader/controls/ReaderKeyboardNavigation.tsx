import { useEffect, useRef } from 'react';
import type { KeyAction } from '../readerSettingsSchema';

interface ReaderKeyboardNavigationProps {
  enabled: boolean;
  // A full-screen page covers the text: bound keys do nothing, so native scrolling can't move the hidden chapter
  paused?: boolean;
  // Maps a KeyboardEvent.key value (e.g. 'ArrowLeft', ' ') to an action
  bindings: Record<string, KeyAction>;
  onAction: (action: KeyAction) => void;
  onEscape?: () => void;
}

// Controls that keep their own Space behavior (activation, toggling)
const BUTTON_LIKE_SELECTOR = 'button, a[href], [role="button"], [role="checkbox"], [role="switch"], [role="tab"], input[type="checkbox"], input[type="radio"]';

// Widgets that use the arrow keys themselves
const KEY_WIDGET_SELECTOR = '[role="combobox"], [role="listbox"], [role="menu"], [role="slider"], [role="tablist"], [role="radiogroup"]';

// Scrolling may repeat while a key is held, the other actions must not
const REPEATABLE_ACTIONS: KeyAction[] = ['scrollUp', 'scrollDown'];

// Escape applies when focus is on the text, the bars, a reader panel or nowhere
const READER_SURFACE_SELECTOR = '[data-reader-surface]';
const READER_PANEL_SELECTOR = '[data-reader-panel]';

// Open MUI menus, selects and dialogs handle their own Escape
const OVERLAY_SELECTOR = '[role="listbox"], [role="menu"], [role="dialog"]:not([data-reader-panel])';

const ReaderKeyboardNavigation = ({
  enabled,
  paused = false,
  bindings,
  onAction,
  onEscape,
}: ReaderKeyboardNavigationProps) => {
  // Latest-ref pattern: the listener reads the newest props without being re-bound on every render
  const bindingsRef = useRef(bindings);
  const onActionRef = useRef(onAction);
  const onEscapeRef = useRef(onEscape);

  useEffect(() => {
    bindingsRef.current = bindings;
    onActionRef.current = onAction;
    onEscapeRef.current = onEscape;
  });

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (e.defaultPrevented) return;
        const target = e.target as Element;
        if (target.closest(OVERLAY_SELECTOR)) return;
        if (onEscapeRef.current && (target === document.body || target.closest(READER_SURFACE_SELECTOR) || target.closest(READER_PANEL_SELECTOR))) {
          onEscapeRef.current();
        }
        return;
      }

      // Only handle navigation when keyboard navigation is enabled
      if (!enabled) return;

      // Don't handle navigation if user is typing in an input/textarea/select
      if (e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLTextAreaElement ||
          e.target instanceof HTMLSelectElement ||
          (e.target instanceof HTMLElement && e.target.isContentEditable)) {
        return;
      }

      // Arrow keys belong to the focused widget (menus, sliders, tabs)
      if (e.target instanceof Element && e.target.closest(KEY_WIDGET_SELECTOR)) {
        return;
      }

      // Don't trigger if modifier keys are pressed
      if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) {
        return;
      }

      // Space on a focused button-like control must keep activating it
      if (e.key === ' ' && e.target instanceof Element && e.target.closest(BUTTON_LIKE_SELECTOR)) {
        return;
      }

      // Single characters are matched lowercase, so 'C' and 'c' are the same key
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;

      // Unbound keys keep the browser's default behavior
      const action = bindingsRef.current[key];
      if (!action || action === 'none') return;

      // While paused the text is covered: only the page itself is held still, a panel keeps native keys
      if (paused) {
        if (e.target === document.body) e.preventDefault();
        return;
      }

      e.preventDefault();

      // Holding a key must not skip chapters or flip the controls on and off
      if (e.repeat && !REPEATABLE_ACTIONS.includes(action)) return;

      onActionRef.current(action);
    };

    // Add event listener
    window.addEventListener('keydown', handleKeyPress);

    // Cleanup
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [enabled, paused]);

  // This is a utility component that doesn't render anything
  return null;
};

export default ReaderKeyboardNavigation;
