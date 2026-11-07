import { useNavigate } from 'react-router-dom';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { findStreamChapter } from './chapterStream';
import { READING_LINE } from './activeSection';
import { sectionKeyOf } from './chapterRange';
import type { NavigationTarget } from './readingPositionSync';

interface ChapterNavigationOptions {
  novelSlug?: string;
  sourceSlug?: string;
  chapter: IChapterContent | null;
  saveScrollIfReady: (force?: boolean) => void;
  // Records the position of the chapter the reader moves to, at its start
  onNavigate: (target: NavigationTarget) => void;
  // Records the position of the chapter being left, for the pages outside the reader
  onLeave: () => void;
  // Closes the open layers first, so no stale layer sits in the history behind the chapter
  closeThen: (run: () => void) => void;
  // readingMode === 'infinite'
  infinite: boolean;
  // The chapters on the page, in infinite mode
  streamChapters: IChapterContent[];
}

// Moving between chapters, the source page and the chapter list
export function useChapterNavigation({
  novelSlug,
  sourceSlug,
  chapter,
  saveScrollIfReady,
  onNavigate,
  onLeave,
  closeThen,
  infinite,
  streamChapters,
}: ChapterNavigationOptions) {
  const navigate = useNavigate();

  const handleChapterNavigation = (direction: 'prev' | 'next') => {
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

    // Infinite mode: a chapter already on the page is scrolled to, and the active-chapter tracker then updates the URL
    const onPage = infinite && gapChapter == null && targetChapter
      ? findStreamChapter(streamChapters, novelSlug, sourceSlug, targetChapter)
      : null;
    const pageKey = onPage ? sectionKeyOf(onPage) : null;
    const pageElement = pageKey ? document.querySelector<HTMLElement>(`[data-chapter-key="${pageKey}"]`) : null;
    if (pageElement) {
      // Its top lands just above the reading line, so the tracker picks it whatever its height; the margin absorbs scroll rounding
      const top = pageElement.getBoundingClientRect().top + window.scrollY - window.innerHeight * READING_LINE + 2;
      window.scrollTo({ top, behavior: 'auto' });
      return;
    }

    // Not for a gap: the unavailable chapter in between is where the reader lands
    if (gapChapter == null && targetChapter) onNavigate({ novelSlug, sourceSlug, chapterNumber: targetChapter });

    // Navigate to the target (or to the unavailable chapter that sits in between)
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
      onLeave();
      navigate(`/novels/${novelSlug}/${sourceSlug}`);
    });
  };

  const goToChapterList = () => {
    closeThen(() => {
      saveScrollIfReady(true);
      onLeave();
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
    });
  };

  // A chapter picked from the chapter list: its position is recorded, then it opens
  const goToChapter = (chapterNumber: number) => {
    closeThen(() => {
      saveScrollIfReady(true);
      onNavigate({ novelSlug, sourceSlug, chapterNumber });
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}`);
    });
  };

  return { goNext, goPrev, goToSource, goToChapterList, goToChapter };
}
