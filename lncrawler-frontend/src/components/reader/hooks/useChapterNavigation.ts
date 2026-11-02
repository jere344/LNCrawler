import { useNavigate } from 'react-router-dom';
import { ChapterContent as IChapterContent } from '@models/novels_types';

interface ChapterNavigationOptions {
  novelSlug?: string;
  sourceSlug?: string;
  chapter: IChapterContent | null;
  saveScrollIfReady: (force?: boolean) => void;
  markBeforeLeaving: () => Promise<void>;
  setActiveTab: (tab: number) => void;
}

// Moving between chapters, the source page and the chapter list
export function useChapterNavigation({
  novelSlug,
  sourceSlug,
  chapter,
  saveScrollIfReady,
  markBeforeLeaving,
  setActiveTab,
}: ChapterNavigationOptions) {
  const navigate = useNavigate();

  const handleChapterNavigation = async (direction: 'prev' | 'next') => {
    // Save current scroll position
    saveScrollIfReady(true);

    // Get the chapter number to navigate to
    const targetChapter = direction === 'next'
      ? chapter?.next_chapter
      : chapter?.prev_chapter;

    // The immediate neighbour exists but isn't the next *available* chapter:
    // there's a gap. Route through the unavailable chapter's page so the skip
    // is deliberate rather than silent.
    const neighbor = direction === 'next' ? chapter?.next_chapter_id : chapter?.prev_chapter_id;
    const gapChapter = neighbor != null && neighbor !== targetChapter ? neighbor : null;

    if (!targetChapter && gapChapter == null) return;

    await markBeforeLeaving();

    // Navigate to the target (or to the unavailable chapter that sits in between)
    setActiveTab(0);
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${gapChapter ?? targetChapter}`);
  };

  const goNext = () => {
    if (chapter?.next_chapter) {
      handleChapterNavigation('next');
    }
  };

  const goPrev = () => {
    if (chapter?.prev_chapter) {
      handleChapterNavigation('prev');
    }
  };

  const goToSource = () => {
    saveScrollIfReady(true);
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };

  const goToChapterList = () => {
    saveScrollIfReady(true);
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  return { goNext, goPrev, goToSource, goToChapterList };
}
