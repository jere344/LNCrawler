import { Fragment, useEffect, useRef, type MouseEvent, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Container,
  Paper,
  Box,
  Divider,
} from '@mui/material';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import type { CommentPreview } from '@models/comments_types';
import { getChapterLabel } from '@utils/Misc';
import BreadcrumbNav from '../../common/BreadcrumbNav';
import ChapterSection, { ChapterSectionHeader } from './ChapterSection';
import ChapterStreamEnd from './ChapterStreamEnd';
import ReaderControls from '../controls/ReaderControls';
import ChapterCommentsCard from './ChapterCommentsCard';
import { reservedMargin } from '../panels/panelLayout';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';
import { useReaderSettings } from '../hooks/useReaderSettings';
import type { ChapterStream } from '../hooks/useChapterStream';
import { sectionKeyOf } from '../hooks/chapterRange';
import type { MarkReadProps } from '../controls/readerBarTypes';
import { TTS_BAR_HEIGHT } from '../tts/ttsTypes';
import type { SwipeableHandlers } from 'react-swipeable';

interface ChapterArticleProps {
  chapter: IChapterContent;
  novelSlug?: string;
  sourceSlug?: string;
  // Sentinel placed after the chapter text, watched to detect the reader reaching its end
  endOfChapterRef: RefObject<HTMLDivElement | null>;
  // Infinite mode: the chapters on the page, from the route's one down, and what stopped the list
  stream: ChapterStream;
  infinite: boolean;
  tapProps: ReaderTapProps;
  swipeHandlers: SwipeableHandlers;
  onListen: () => void;
  onOpenSettings: () => void;
  onOpenChapterList: () => void;
  onNarrate: () => void;
  markRead: MarkReadProps;
  onPrevious: () => void;
  onNext: () => void;
  // All comments on the chapter, the posted ones included
  commentCount: number;
  topComment: CommentPreview | null;
  onOpenComments: (opts?: { compose?: boolean }) => void;
  // Infinite mode: the chapters marked as read this session, the ones with a mark request in flight, and marking one
  markedChapters: ReadonlySet<number>;
  markingChapters: ReadonlySet<number>;
  onMarkChapter: (chapterNumber: number) => void;
  // Infinite mode: opens the comments of a section on the page, which may not be the route's chapter
  onOpenCommentsFor: (chapter: IChapterContent, opts?: { compose?: boolean }) => void;
  ttsOpen: boolean;
  // Height of the audiobook mini bar, kept clear of the end of the chapter
  barHeight: number;
  // Width in px kept clear at the start edge, so the text is not covered by the chapter list
  reservedStart: number;
  // Width in px kept clear at the end edge, so the text is not covered by the display panel
  reservedEnd: number;
}

// The article: breadcrumbs, the text, the comments summary and the controls at its end
const ChapterArticle = ({
  chapter,
  novelSlug,
  sourceSlug,
  endOfChapterRef,
  stream,
  infinite,
  tapProps,
  swipeHandlers,
  onListen,
  onOpenSettings,
  onOpenChapterList,
  onNarrate,
  markRead: { showMarkRead, markReadSuccess, markingAsRead, onMarkAsRead },
  onPrevious,
  onNext,
  commentCount,
  topComment,
  onOpenComments,
  markedChapters,
  markingChapters,
  onMarkChapter,
  onOpenCommentsFor,
  ttsOpen,
  barHeight,
  reservedStart,
  reservedEnd,
}: ChapterArticleProps) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const chapterLabel = getChapterLabel(t, chapter.title, chapter.chapter_id);
  const { chapters: streamChapters, end: streamEnd, loadMore } = stream;
  // Keyed on the last section, so a trim at the top does not re-observe
  const lastStreamKey = streamChapters.length ? sectionKeyOf(streamChapters[streamChapters.length - 1]) : null;

  // Sentinel after the last section, watched to load the next chapter in infinite mode
  const loadMoreRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // Without an observer the stream stays at the route's chapter
    if (!infinite || streamEnd || typeof IntersectionObserver === 'undefined') return;
    const node = loadMoreRef.current;
    if (!node) return;
    const observer = new IntersectionObserver(([entry]) => {
      if (entry?.isIntersecting) void loadMore();
    }, { rootMargin: '0px 0px 150% 0px' });
    // Observed again after each append: a short chapter can leave the sentinel in view, and the observer only fires on changes
    observer.observe(node);
    return () => observer.disconnect();
  }, [infinite, streamEnd, lastStreamKey, loadMore]);

  // The card around the text: the chapter mode one holds the comments and controls too
  const paperSx = (mb: number) => ({
    p: { xs: 2, md: 4 },
    mt: 2,
    mb,
    backgroundColor: settings.backgroundColor || undefined,
    color: settings.fontColor || undefined,
    mx: `${settings.margin}%`
  });

  // The reader leaves through its own navigation, so its panels do not stay in the history. A modified click keeps the link's own behaviour.
  const handleChapterListClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onOpenChapterList();
  };

  // The previous, mark-read and next controls, from the chapter's neighbours; the mark-read button only when asked for
  const readerControls = (withMarkRead: boolean, neighbours: IChapterContent = chapter) => (
    <ReaderControls
      prevChapter={neighbours.prev_chapter}
      nextChapter={neighbours.next_chapter}
      isAuthenticated={withMarkRead && showMarkRead}
      markReadSuccess={markReadSuccess}
      markingAsRead={markingAsRead}
      onMarkAsRead={onMarkAsRead}
      onPrevious={onPrevious}
      onNext={onNext}
    />
  );

  return (
    <>
      <Box sx={{
        marginInlineStart: reservedMargin(reservedStart),
        marginInlineEnd: reservedMargin(reservedEnd),
        transition: 'margin 0.25s ease-out',
        '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
      }}>
        <Container
          data-reader-surface
          maxWidth="md"
          sx={{ padding: { xs: 0, md: 4 } }}
          {...swipeHandlers}
        >
          {/* Breadcrumbs on every viewport; the gutter keeps them off the screen edge on mobile */}
          <Box sx={{ px: { xs: 2, md: 0 } }}>
            <BreadcrumbNav
              items={[
                {
                  label: chapter.novel_title,
                  icon: <BookIcon fontSize="inherit" />
                },
                {
                  label: chapter.source_name,
                  link: `/novels/${novelSlug}/${sourceSlug}`,
                  icon: <LanguageIcon fontSize="inherit" />
                },
                {
                  label: t('reader.chapters'),
                  link: `/novels/${novelSlug}/${sourceSlug}/chapterlist`,
                  onClick: handleChapterListClick,
                  icon: <ListAltIcon fontSize="inherit" />
                },
                {
                  label: chapterLabel,
                  icon: <MenuBookIcon fontSize="inherit" />
                }
              ]}
            />
          </Box>

          {infinite ? (
            // One card for the whole list, so the chapters read as one text. The trim compensates the scroll itself; browser anchoring would apply the shift a second time
            <Paper elevation={3} sx={{ ...paperSx(8), overflowAnchor: 'none' }}>
              {streamChapters[0] && (
                <ChapterSectionHeader chapter={streamChapters[0]} onListen={onListen} onOpenSettings={onOpenSettings} />
              )}
              {streamChapters.map((streamChapter, index) => {
                // The section of the chapter the route is on: TTS and read tracking follow it
                const sectionKey = sectionKeyOf(streamChapter);
                const isActive = sectionKey === sectionKeyOf(chapter);
                return (
                  <Fragment key={sectionKey}>
                    {/* Between chapters, outside the sections so a trim measures the text that stays */}
                    {index > 0 && <Divider sx={{ mb: 4 }} />}
                    <ChapterSection
                      chapter={streamChapter}
                      contentId={isActive ? 'reader-content' : `reader-content-${streamChapter.chapter_id}`}
                      endRef={isActive ? endOfChapterRef : undefined}
                      landmark
                      header={false}
                      tapProps={tapProps}
                      onListen={onListen}
                      onOpenSettings={onOpenSettings}
                      onNarrate={onNarrate}
                    />

                    {/* Comments summary of this section: opens its comments. Hidden by the setting, the comments stay in the reader controls */}
                    {settings.infiniteShowComments && (
                      <Box sx={{ mb: 4 }}>
                        <ChapterCommentsCard
                          count={isActive ? commentCount : (streamChapter.comment_count ?? 0)}
                          chapterLabel={getChapterLabel(t, streamChapter.title, streamChapter.chapter_id)}
                          topComment={streamChapter.top_comment ?? null}
                          onOpen={(opts) => onOpenCommentsFor(streamChapter, opts)}
                        />
                      </Box>
                    )}

                    {/* Mark as read for this section; no previous or next here, the controls at the end of the stream keep them */}
                    {showMarkRead && (
                      <ReaderControls
                        isAuthenticated
                        markReadSuccess={markedChapters.has(streamChapter.chapter_id)}
                        markingAsRead={markingChapters.has(streamChapter.chapter_id)}
                        onMarkAsRead={() => onMarkChapter(streamChapter.chapter_id)}
                        onPrevious={onPrevious}
                        onNext={onNext}
                      />
                    )}
                  </Fragment>
                );
              })}
              <ChapterStreamEnd stream={stream} novelSlug={novelSlug} sourceSlug={sourceSlug} />
              <Box ref={loadMoreRef} aria-hidden="true" sx={{ height: 1 }} />
              {/* The last section has its own mark-read button, so only previous and next are kept here, from the last section's neighbours */}
              {streamEnd && readerControls(false, streamChapters[streamChapters.length - 1] ?? chapter)}
            </Paper>
          ) : (
            <Paper elevation={3} sx={paperSx(8)}>
              <ChapterSection
                chapter={chapter}
                contentId="reader-content"
                endRef={endOfChapterRef}
                tapProps={tapProps}
                onListen={onListen}
                onOpenSettings={onOpenSettings}
                onNarrate={onNarrate}
              />

              {/* Comments summary: opens the comments panel */}
              <Box sx={{ mb: 4 }}>
                <ChapterCommentsCard
                  count={commentCount}
                  chapterLabel={chapterLabel}
                  topComment={topComment}
                  onOpen={onOpenComments}
                />
              </Box>

              {/* Reader Controls */}
              {readerControls(true)}
            </Paper>
          )}
        </Container>
      </Box>
      {ttsOpen && <Box sx={{ height: { xs: TTS_BAR_HEIGHT.mobile, sm: TTS_BAR_HEIGHT.desktop + 16 } }} />}
      {/* Keeps the end of the chapter clear of the audiobook mini bar */}
      <Box sx={{ height: barHeight }} />
    </>
  );
};

export default ChapterArticle;
