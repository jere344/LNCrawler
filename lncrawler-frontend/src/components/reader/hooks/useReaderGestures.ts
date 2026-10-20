import { useSwipeable } from 'react-swipeable';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { ReaderSettings as IReaderSettings } from '../ReaderSettings';

export function useReaderGestures({
  chapter,
  isMobile,
  controlsVisible,
  readerSettings,
  onNextChapter,
  onPrevChapter,
}: {
  chapter: IChapterContent | null;
  isMobile: boolean;
  controlsVisible: boolean;
  readerSettings: IReaderSettings;
  onNextChapter: () => void;
  onPrevChapter: () => void;
}) {
  // Handle swipe gestures
  const handleSwipeLeft = () => {
    const gesture = readerSettings.swipeLeftGesture;
    switch (gesture) {
      case 'nextChapter':
        if (chapter?.next_chapter) {
          onNextChapter();
        }
        break;
      case 'prevChapter':
        onPrevChapter();
        break;
      case 'none':
      default:
        // Do nothing
        break;
    }
  };

  const handleSwipeRight = () => {
    const gesture = readerSettings.swipeRightGesture;
    switch (gesture) {
      case 'prevChapter':
        onPrevChapter();
        break;
      case 'nextChapter':
        onNextChapter();
        break;
      case 'none':
      default:
        // Do nothing
        break;
    }
  };

  // Handle swipe gestures - simplified for non-page mode
  const handleGesture = (direction: 'left' | 'right') => {
    if (!isMobile || !chapter || controlsVisible) return;
    if (direction === 'left') {
      handleSwipeLeft();
    } else {
      handleSwipeRight();
    }
  };
  
  // Configure swipe handlers
  const swipeHandlers = useSwipeable({
    onSwipedLeft: () => handleGesture('left'),
    onSwipedRight: () => handleGesture('right'),
    trackMouse: false,
    preventScrollOnSwipe: false,
    // Only detect wider/more intentional swipes to prevent accidental activation
    delta: 50,
    swipeDuration: 500,
  });

  return { swipeHandlers };
}
