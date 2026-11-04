import { useSwipeable } from 'react-swipeable';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import type { SwipeGesture } from '../readerSettingsSchema';

interface ReaderGesturesOptions {
  chapter: IChapterContent | null;
  // Swipes are ignored while a settings page covers the text
  disabled: boolean;
  swipeLeftGesture: SwipeGesture;
  swipeRightGesture: SwipeGesture;
  onNextChapter: () => void;
  onPrevChapter: () => void;
}

export function useReaderGestures({
  chapter,
  disabled,
  swipeLeftGesture,
  swipeRightGesture,
  onNextChapter,
  onPrevChapter,
}: ReaderGesturesOptions) {
  // One mapping for both directions: the gesture setting names the action
  const runGesture = (gesture: SwipeGesture) => {
    if (gesture === 'nextChapter') onNextChapter();
    else if (gesture === 'prevChapter') onPrevChapter();
  };

  // trackMouse stays off, so only touch swipes count
  const swipeHandlers = useSwipeable({
    onSwipedLeft: () => {
      if (chapter && !disabled) runGesture(swipeLeftGesture);
    },
    onSwipedRight: () => {
      if (chapter && !disabled) runGesture(swipeRightGesture);
    },
    trackMouse: false,
    preventScrollOnSwipe: false,
    // Only detect wider/more intentional swipes to prevent accidental activation
    delta: 50,
    swipeDuration: 500,
  });

  return { swipeHandlers };
}
