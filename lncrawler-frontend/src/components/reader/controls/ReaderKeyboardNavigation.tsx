import { useEffect, useRef } from 'react';
import type { KeyAction } from '../ReaderSettings';

interface ReaderKeyboardNavigationProps {
  enabled: boolean;
  controlsVisible?: boolean;
  // Maps a KeyboardEvent.key value (e.g. 'ArrowLeft', ' ') to an action
  bindings: Record<string, KeyAction>;
  onAction: (action: KeyAction) => void;
}

// Actions this component handles; anything else (including 'none' and unknown cookie values) is ignored
const NAVIGATION_ACTIONS: KeyAction[] = ['scrollUp', 'scrollDown', 'prevChapter', 'nextChapter'];

// Controls that keep their own Space behavior (activation, toggling)
const BUTTON_LIKE_SELECTOR = 'button, a[href], [role="button"], [role="checkbox"], [role="switch"], [role="tab"], input[type="checkbox"], input[type="radio"]';

const ReaderKeyboardNavigation = ({
  enabled,
  controlsVisible = false,
  bindings,
  onAction,
}: ReaderKeyboardNavigationProps) => {
  // Latest-ref pattern: the listener reads the newest props without being re-bound on every render
  const bindingsRef = useRef(bindings);
  const onActionRef = useRef(onAction);

  useEffect(() => {
    bindingsRef.current = bindings;
    onActionRef.current = onAction;
  });

  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Only handle navigation when keyboard navigation is enabled
      if (!enabled) return;

      // Don't handle navigation if settings/controls are visible
      if (controlsVisible) return;

      // Don't handle navigation if user is typing in an input/textarea/select
      if (e.target instanceof HTMLInputElement ||
          e.target instanceof HTMLTextAreaElement ||
          e.target instanceof HTMLSelectElement ||
          (e.target instanceof HTMLElement && e.target.isContentEditable)) {
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

      // Unbound keys keep the browser's default behavior
      const action = bindingsRef.current[e.key];
      if (!action || !NAVIGATION_ACTIONS.includes(action)) return;

      e.preventDefault();

      // Holding a chapter key must not skip several chapters
      if (e.repeat && (action === 'prevChapter' || action === 'nextChapter')) return;

      onActionRef.current(action);
    };

    // Add event listener
    window.addEventListener('keydown', handleKeyPress);

    // Cleanup
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [enabled, controlsVisible]);

  // This is a utility component that doesn't render anything
  return null;
};

export default ReaderKeyboardNavigation;
