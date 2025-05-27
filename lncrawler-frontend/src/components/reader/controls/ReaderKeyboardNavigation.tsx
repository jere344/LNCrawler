import { useEffect } from 'react';

interface ReaderKeyboardNavigationProps {
  enabled: boolean;
  onNextChapter: () => void;
  onPrevChapter: () => void;
  controlsVisible?: boolean;
}

const ReaderKeyboardNavigation = ({
  enabled,
  onNextChapter,
  onPrevChapter,
  controlsVisible = false,
}: ReaderKeyboardNavigationProps) => {
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Only handle navigation when keyboard navigation is enabled
      if (!enabled) return;
      
      // Don't handle navigation if settings/controls are visible
      if (controlsVisible) return;

      // Don't handle navigation if user is typing in an input/textarea
      if (e.target instanceof HTMLInputElement || 
          e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Don't trigger if modifier keys are pressed
      if (e.ctrlKey || e.altKey || e.shiftKey || e.metaKey) {
        return;
      }

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault();
          onPrevChapter();
          break;
        case 'ArrowRight':
          e.preventDefault();
          onNextChapter();
          break;
      }
    };

    // Add event listener
    window.addEventListener('keydown', handleKeyPress);

    // Cleanup
    return () => {
      window.removeEventListener('keydown', handleKeyPress);
    };
  }, [enabled, controlsVisible, onNextChapter, onPrevChapter]);

  // This is a utility component that doesn't render anything
  return null;
};

export default ReaderKeyboardNavigation;
