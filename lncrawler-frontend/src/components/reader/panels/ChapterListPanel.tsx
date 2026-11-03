import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type Ref } from 'react';
import { Box, IconButton, LinearProgress, Link, Skeleton, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CloseIcon from '@mui/icons-material/Close';
import { getVolumeHeading } from '@utils/Misc';
import { useDebounce } from '@utils/useDebounce';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import ReaderPanelFrame from './ReaderPanelFrame';
import { pageRange } from './chapterList';
import { ChapterRow, ChapterRowSkeleton, ROW_HEIGHT } from './ChapterRow';
import { useChapterPages } from './useChapterPages';
import { useRovingRows } from './useRovingRows';
import { useVirtualRows } from './useVirtualRows';

const SEARCH_DEBOUNCE_MS = 250;
// Pages load once the scroll has settled this long, so a fling or a scrollbar drag loads only where it stops
const PAGE_LOAD_DELAY_MS = 120;
// Skeleton rows that fill the list while the first page is on its way
const SKELETON_FILL = 20;
const VOLUME_BAR_HEIGHT = 28;
// The list is dimmed while a search it does not show yet is on its way, or has failed
const STALE_OPACITY = 0.5;

export interface ChapterListPanelProps {
  novelSlug: string;
  sourceSlug: string;
  novelTitle: string;
  // The chapter being read: the list opens on its page and highlights its row
  currentChapterId: number;
  mode: ReaderLayoutMode;
  onClose: () => void;
  onOpenChapter: (chapterId: number) => void;
  onOpenNovel: () => void;
  // Set by the slide transition that opens the panel
  ref?: Ref<HTMLDivElement>;
  style?: CSSProperties;
}

// The chapter list over the reader: a search field, a volume bar, and the chapters as fixed-height rows
const ChapterListPanel = ({
  novelSlug,
  sourceSlug,
  novelTitle,
  currentChapterId,
  mode,
  onClose,
  onOpenChapter,
  onOpenNovel,
  ref,
  style,
}: ChapterListPanelProps) => {
  const { t } = useTranslation();
  const [text, setText] = useState('');
  // Typing waits for a pause before searching
  const query = useDebounce(text.trim(), SEARCH_DEBOUNCE_MS);
  const { view, failed, retry, chapterAt, loadPages, currentIndex } = useChapterPages({
    novelSlug,
    sourceSlug,
    currentChapterId,
    query,
  });
  // The count of the whole list, kept while a search is shown
  const [totalCount, setTotalCount] = useState<number | null>(null);
  const listRef = useRef<HTMLDivElement>(null);
  // The query the list was last positioned for: a view for another query is positioned again
  const positioned = useRef<string | null>(null);

  const rowCount = view?.count ?? 0;
  const { top, start, end, sync } = useVirtualRows(listRef, rowCount, ROW_HEIGHT);
  const { active, onFocus, onKeyDown } = useRovingRows(listRef, rowCount, sync, currentIndex ?? top);
  // The row in the tab order: the active one, or the nearest one rendered
  const tabStop = Math.min(Math.max(active, start), end - 1);
  // Volume bar and dividers only for the whole list, and only when its source has volumes
  const volumes = view?.query === '' && view.hasVolumes;

  if (view?.query === '' && view.count !== totalCount) setTotalCount(view.count);

  // The volume of the row at the top; a placeholder until its page arrives
  const topChapter = chapterAt(top);

  // A view for a query shown for the first time: the list opens at the current chapter, or at the top of a search
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !view || positioned.current === view.query) return;
    positioned.current = view.query;
    list.scrollTop = currentIndex === null || view.query !== ''
      ? 0
      : Math.max(0, currentIndex * ROW_HEIGHT - list.clientHeight / 3);
    sync();
  }, [view, currentIndex, sync]);

  const hasView = view !== null;
  // The pages under the rows in view, and one screen above and below them
  const visibleRows = end - start;
  const [firstPage, lastPage] = pageRange(start - visibleRows, end + visibleRows, rowCount);

  // Loads the pages in view once the scroll settles; after a failure, the retry starts it again
  useEffect(() => {
    if (!hasView || failed) return;
    const timer = window.setTimeout(() => loadPages(firstPage, lastPage), PAGE_LOAD_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [firstPage, lastPage, hasView, failed, loadPages]);

  // A row with its chapter, or a skeleton of the same height until its page arrives
  const renderRow = (index: number) => {
    const chapter = chapterAt(index);
    if (!chapter) return <ChapterRowSkeleton key={index} index={index} />;
    const previous = index > 0 ? chapterAt(index - 1) : undefined;
    const isCurrent = chapter.chapter_id === currentChapterId;
    return (
      <ChapterRow
        key={index}
        chapter={chapter}
        index={index}
        tabIndex={index === tabStop ? 0 : -1}
        isCurrent={isCurrent}
        volumeStart={volumes && previous !== undefined && previous.volume !== chapter.volume}
        onClick={() => (isCurrent ? onClose() : onOpenChapter(chapter.chapter_id))}
      />
    );
  };

  // The rows still show the last query's answer while a new one loads, or after it has failed
  const stale = view !== null && view.query !== query;
  // A search that finds nothing
  const isEmpty = view !== null && view.query === query && query !== '' && rowCount === 0;

  const errorMessage = (
    <Box sx={{ px: 2, py: 2, textAlign: 'center' }}>
      <Typography color="error" sx={{ mb: 1 }}>
        {t('chapterList.loadFailed')}
      </Typography>
      <Link component="button" onClick={retry}>
        {t('readerChapters.retry')}
      </Link>
    </Box>
  );

  return (
    <ReaderPanelFrame
      ref={ref}
      style={style}
      title={t('reader.chapters')}
      mode={mode}
      side="start"
      showBack={false}
      onBack={onClose}
      flush
      headerExtra={
        <IconButton onClick={onClose} aria-label={t('readerChapters.close')}>
          <CloseIcon />
        </IconButton>
      }
    >
      <Box sx={{ px: 2, pt: 1.5, pb: 1 }}>
        <Typography variant="subtitle1" noWrap sx={{ fontWeight: 600 }}>
          {novelTitle}
        </Typography>
        <Typography variant="caption" component="div" color="text.secondary">
          {/* A placeholder keeps the link in place until the count is known */}
          {totalCount === null
            ? <Skeleton variant="text" width={80} sx={{ display: 'inline-block', fontSize: 'inherit' }} />
            : t('units.chapters', { count: totalCount })}
          {' · '}
          <Link component="button" variant="caption" onClick={onOpenNovel}>
            {t('readerChapters.novelPage')}
          </Link>
        </Typography>
      </Box>

      <Box sx={{ px: 1.5, pb: 1 }}>
        <TextField
          size="small"
          fullWidth
          type="search"
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder={t('readerChapters.searchPlaceholder')}
          slotProps={{ htmlInput: { 'aria-label': t('readerChapters.searchLabel') } }}
        />
      </Box>

      {volumes && (
        <Typography
          noWrap
          sx={{
            height: VOLUME_BAR_HEIGHT,
            lineHeight: `${VOLUME_BAR_HEIGHT}px`,
            px: 2,
            fontSize: 12,
            fontWeight: 600,
            color: 'text.secondary',
          }}
        >
          {topChapter ? getVolumeHeading(t, topChapter.volume, topChapter.volume_title) : <Skeleton variant="text" width={120} sx={{ display: 'inline-block', fontSize: 'inherit' }} />}
        </Typography>
      )}

      <Box sx={{ position: 'relative', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}>
        {stale && !failed && (
          <LinearProgress aria-hidden sx={{ position: 'absolute', top: 0, insetInline: 0, height: 2, zIndex: 1 }} />
        )}

        <Box
          ref={listRef}
          aria-busy={stale && !failed}
          onFocus={onFocus}
          onKeyDown={onKeyDown}
          sx={{
            flex: 1,
            minHeight: 0,
            overflowY: view ? 'auto' : 'hidden',
            // Native scroll anchoring would move the rows in view when a row above is swapped for text
            overflowAnchor: 'none',
            scrollbarWidth: 'thin',
            borderTop: 1,
            borderColor: 'divider',
            opacity: stale ? STALE_OPACITY : 1,
            transition: 'opacity 150ms',
            // Room for the longest chapter number, so the titles line up
            '--chapter-number-width': `${Math.max(3, String(totalCount ?? 0).length) + 1}ch`,
          }}
        >
          {view === null && (failed
            ? errorMessage
            : Array.from({ length: SKELETON_FILL }, (_, index) => <ChapterRowSkeleton key={index} index={index} />))}

          {view !== null && (
            <>
              <Box sx={{ position: 'relative', height: rowCount * ROW_HEIGHT }}>
                <Box sx={{ position: 'absolute', insetInline: 0, top: 0, transform: `translateY(${start * ROW_HEIGHT}px)` }}>
                  {Array.from({ length: end - start }, (_, offset) => renderRow(start + offset))}
                </Box>
              </Box>

              {isEmpty && (
                <Typography sx={{ px: 2, py: 3, textAlign: 'center', color: 'text.secondary' }}>
                  {t('readerChapters.noMatch')}
                </Typography>
              )}
            </>
          )}
        </Box>

        {view !== null && failed && (
          <Box sx={{ position: 'absolute', insetInline: 0, bottom: 0, bgcolor: 'background.paper', borderTop: 1, borderColor: 'divider' }}>
            {errorMessage}
          </Box>
        )}
      </Box>
    </ReaderPanelFrame>
  );
};

export default ChapterListPanel;
