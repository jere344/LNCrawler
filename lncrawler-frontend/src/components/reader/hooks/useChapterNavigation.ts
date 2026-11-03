import { useNavigate } from 'react-router-dom';
import { ChapterContent as IChapterContent } from '@models/novels_types';

interface ChapterNavigationOptions {
  novelSlug?: string;
  sourceSlug?: string;
  chapter: IChapterContent | null;
  saveScrollIfReady: (force?: boolean) => void;
  markBeforeLeaving: () => Promise<void>;
  setActiveTab: (tab: number) => void;
  // Closes the open layers first, so no stale layer sits in the history behind the chapter
  closeThen: (run: () => void) => void;
}

// Moving between chapters, the source page and the chapter list
export function useChapterNavigation({
  novelSlug,
  sourceSlug,
  chapter,
  saveScrollIfReady,
  markBeforeLeaving,
  setActiveTab,
  closeThen,
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
      closeThen(() => handleChapterNavigation('next'));
    }
  };

  const goPrev = () => {
    if (chapter?.prev_chapter) {
      closeThen(() => handleChapterNavigation('prev'));
    }
  };

  const goToSource = () => {
    closeThen(() => {
      saveScrollIfReady(true);
      navigate(`/novels/${novelSlug}/${sourceSlug}`);
    });
  };

  const goToChapterList = () => {
    closeThen(() => {
      saveScrollIfReady(true);
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
    });
  };

  // A chapter picked from the chapter list: saved and marked like moving on, then opened
  const goToChapter = (chapterNumber: number) => {
    closeThen(async () => {
      saveScrollIfReady(true);
      await markBeforeLeaving();
      setActiveTab(0);
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}`);
    });
  };

  return { goNext, goPrev, goToSource, goToChapterList, goToChapter };
}
