import type { ChapterContent } from '@models/novels_types';
import { useTranslation } from 'react-i18next';
import { getChapterLabel } from '@utils/Misc';
import type { FullscreenProps, MarkReadProps, ReaderBarProps, ReaderShortcuts } from '../controls/readerBarTypes';
import type { ReaderPanel } from './useReaderPanels';

interface UseReaderBarPropsOptions {
  // Null while the chapter loads; the bars are only drawn once it is set
  chapter: ChapterContent | null;
  controlsVisible: boolean;
  isDesktop: boolean;
  panel: ReaderPanel;
  reservedStart: number;
  reservedEnd: number;
  shortcuts: ReaderShortcuts;
  setControlsVisible: (visible: boolean) => void;
  markRead: MarkReadProps;
  fullscreen: FullscreenProps;
  navigation: {
    goPrev: () => void;
    goNext: () => void;
    goToSource: () => void;
  };
  onToggleChapters: () => void;
  onToggleDisplay: () => void;
  toggleComments: () => void;
  commentsOpen: boolean;
  commentCount: number;
  onOpenSettings: () => void;
  onListen: () => void;
}

// Props for the reader bars, and the chapter label
export function useReaderBarProps({
  chapter,
  controlsVisible,
  isDesktop,
  panel,
  reservedStart,
  reservedEnd,
  shortcuts,
  setControlsVisible,
  markRead,
  fullscreen,
  navigation,
  onToggleChapters,
  onToggleDisplay,
  toggleComments,
  commentsOpen,
  commentCount,
  onOpenSettings,
  onListen,
}: UseReaderBarPropsOptions) {
  const { t } = useTranslation();
  const chapterLabel = chapter ? getChapterLabel(t, chapter.title, chapter.chapter_id) : '';
  const fullscreenLabel = t(fullscreen.active ? 'readerControls.exitFullscreen' : 'readerControls.enterFullscreen');
  const fullscreenTitle = shortcuts.fullscreen ? `${fullscreenLabel} (${shortcuts.fullscreen})` : fullscreenLabel;

  // Touch layouts hide the bars after an action; the desktop toolbar stays
  const hideOnTouch = () => {
    if (!isDesktop) setControlsVisible(false);
  };

  const barProps: ReaderBarProps = {
    controlsVisible,
    chapterTitle: chapterLabel,
    novelTitle: chapter?.novel_title ?? '',
    hasPrev: !!chapter?.prev_chapter,
    hasNext: !!chapter?.next_chapter,
    displayOpen: panel === 'display',
    commentsOpen,
    commentCount,
    reservedStart,
    reservedEnd,
    shortcuts,
    markRead,
    fullscreen,
    fullscreenLabel,
    fullscreenTitle,
    onHome: navigation.goToSource,
    onChapterList: onToggleChapters,
    onPrevious: navigation.goPrev,
    onNext: navigation.goNext,
    onDisplay: onToggleDisplay,
    onListen: () => {
      hideOnTouch();
      onListen();
    },
    onComments: toggleComments,
    onSettings: onOpenSettings,
  };

  return { barProps, chapterLabel };
}
