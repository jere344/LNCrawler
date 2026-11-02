import type { Dispatch, SetStateAction } from 'react';
import type { EdgeTapBehavior, KeyAction, ReaderSettings } from '../readerSettingsSchema';

// Settings that hold the action of one key
type KeyBindingSetting =
  | 'keyArrowLeft' | 'keyArrowRight' | 'keyArrowUp' | 'keyArrowDown'
  | 'keyPageUp' | 'keyPageDown' | 'keySpace' | 'keyC' | 'keyD';

// Every bindable key, in display order: the KeyboardEvent.key value, its setting, and its label
export const READER_KEYS: { key: string; setting: KeyBindingSetting; labelKey: string }[] = [
  { key: 'ArrowLeft', setting: 'keyArrowLeft', labelKey: 'keyboardSettings.arrowLeft' },
  { key: 'ArrowRight', setting: 'keyArrowRight', labelKey: 'keyboardSettings.arrowRight' },
  { key: 'ArrowUp', setting: 'keyArrowUp', labelKey: 'keyboardSettings.arrowUp' },
  { key: 'ArrowDown', setting: 'keyArrowDown', labelKey: 'keyboardSettings.arrowDown' },
  { key: 'PageUp', setting: 'keyPageUp', labelKey: 'keyboardSettings.pageUp' },
  { key: 'PageDown', setting: 'keyPageDown', labelKey: 'keyboardSettings.pageDown' },
  { key: ' ', setting: 'keySpace', labelKey: 'keyboardSettings.space' },
  { key: 'c', setting: 'keyC', labelKey: 'readerSettingsPages.keyC' },
  { key: 'd', setting: 'keyD', labelKey: 'readerSettingsPages.keyD' },
];

// Scroll by 80% of viewport height (1 = down, -1 = up)
const scrollPage = (direction: 1 | -1) => {
  window.scrollBy({
    top: direction * window.innerHeight * 0.8,
    behavior: 'smooth'
  });
};

// KeyboardEvent.key value -> action, from the Keyboard settings. Letters are matched lowercase.
export const buildKeyBindings = (settings: ReaderSettings): Record<string, KeyAction> =>
  Object.fromEntries(READER_KEYS.map(({ key, setting }) => [key, settings[setting]]));

// The key bound to an action, written as a shortcut label ('Space', 'D'); undefined when nothing is bound
export const keyLabelFor = (bindings: Record<string, KeyAction>, action: KeyAction): string | undefined => {
  const key = Object.keys(bindings).find((k) => bindings[k] === action);
  if (key === undefined) return undefined;
  if (key === ' ') return 'Space';
  return key.length === 1 ? key.toUpperCase() : key;
};

interface ReaderActionOptions {
  goNext: () => void;
  goPrev: () => void;
  setControlsVisible: Dispatch<SetStateAction<boolean>>;
  toggleDisplay: () => void;
}

// What taps and keys can do, written once for both
export function useReaderActions({ goNext, goPrev, setControlsVisible, toggleDisplay }: ReaderActionOptions) {
  // Scrolling and changing chapter, shared by edge taps and keys
  const runScrollOrChapter = (action: KeyAction) => {
    switch (action) {
      case 'scrollUp':
        scrollPage(-1);
        break;
      case 'scrollDown':
        scrollPage(1);
        break;
      case 'prevChapter':
        goPrev();
        break;
      case 'nextChapter':
        goNext();
        break;
      default:
        // 'none', or an action that is not about scrolling or chapters
        break;
    }
  };

  // Edge taps: 'chapter' goes back on the left edge and on from the right
  const runEdge = (edge: 'left' | 'right', behavior: EdgeTapBehavior) => {
    if (behavior === 'chapter') runScrollOrChapter(edge === 'left' ? 'prevChapter' : 'nextChapter');
    else runScrollOrChapter(behavior);
  };

  const runKeyAction = (action: KeyAction) => {
    switch (action) {
      case 'toggleControls':
        setControlsVisible((visible) => !visible);
        break;
      case 'displaySheet':
        setControlsVisible(true);
        toggleDisplay();
        break;
      default:
        runScrollOrChapter(action);
        break;
    }
  };

  return { runEdge, runKeyAction };
}
