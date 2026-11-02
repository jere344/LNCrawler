import type { ChapterContent } from '@models/novels_types';
import { useTranslation } from 'react-i18next';
import { getChapterLabel } from '@utils/Misc';
import type { MarkReadProps, ReaderBarProps, ReaderShortcuts } from '../controls/readerBarTypes';
import type { ReaderPanel } from './useReaderPanels';

interface UseReaderBarPropsOptions {
  // Null while the chapter loads; the bars are only drawn once it is set
  chapter: ChapterContent | null;
  controlsVisible: boolean;
  isDesktop: boolean;
  panel: ReaderPanel;
  reservedEnd: number;
  shortcuts: ReaderShortcuts;
  setControlsVisible: (visible: boolean) => void;
  setActiveTab: (tab: number) => void;
  markRead: MarkReadProps;
  navigation: {
    goPrev: () => void;
    goNext: () => void;
    goToSource: () => void;
    goToChapterList: () => void;
  };
  onToggleDisplay: () => void;
  onOpenSettings: () => void;
  onListen: () => void;
}

// Props for the reader bars, the comments switch that hides the touch bars, and the chapter label
export function useReaderBarProps({
  chapter,
  controlsVisible,
  isDesktop,
  panel,
  reservedEnd,
  shortcuts,
  setControlsVisible,
  setActiveTab,
  markRead,
  navigation,
  onToggleDisplay,
  onOpenSettings,
  onListen,
}: UseReaderBarPropsOptions) {
  const { t } = useTranslation();
  const chapterLabel = chapter ? getChapterLabel(t, chapter.title, chapter.chapter_id) : '';

  // Touch layouts hide the bars after an action; the desktop toolbar stays
  const hideOnTouch = () => {
    if (!isDesktop) setControlsVisible(false);
  };

  // Switch to the comments tab, scroll back to the top and hide the touch bars
  const switchToComments = () => {
    setActiveTab(1);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    hideOnTouch();
  };

  const barProps: ReaderBarProps = {
    controlsVisible,
    chapterTitle: chapterLabel,
    novelTitle: chapter?.novel_title ?? '',
    hasPrev: !!chapter?.prev_chapter,
    hasNext: !!chapter?.next_chapter,
    displayOpen: panel === 'display',
    reservedEnd,
    shortcuts,
    markRead,
    onHome: navigation.goToSource,
    onChapterList: navigation.goToChapterList,
    onPrevious: navigation.goPrev,
    onNext: navigation.goNext,
    onDisplay: onToggleDisplay,
    onListen: () => {
      hideOnTouch();
      onListen();
    },
    onComments: switchToComments,
    onSettings: onOpenSettings,
  };

  return { barProps, switchToComments, chapterLabel };
}
