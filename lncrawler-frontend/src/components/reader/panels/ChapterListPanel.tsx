import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { Box, IconButton, Link, ListItemButton, Skeleton, TextField, Typography, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import CloseIcon from '@mui/icons-material/Close';
import type { NovelChaptersResponse } from '@models/novels_types';
import { getChapterLabel } from '@utils/Misc';
import { novelService } from '@services/novel.service';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import ReaderPanelFrame from './ReaderPanelFrame';
import { createChapterListCache } from './chapterListCache';

// Rows are 48px; the list loads the neighbouring page when the scroll gets this close to an end
const ROW_HEIGHT = 48;
const EDGE_PX = 200;
const SEARCH_DEBOUNCE_MS = 250;
const SKELETON_ROWS = 8;

// Shared by every reader visit: a chapter list reopened within its TTL makes no request
const chapterListCache = createChapterListCache((request) =>
  novelService.getNovelChapters(request.novelSlug, request.sourceSlug, request.page, undefined, request.search, request.around),
);

// The page-by-page list the pages loaded so far make up; `query` is the search they answer ('' for the whole list)
interface ListView {
  query: string;
  pages: Map<number, NovelChaptersResponse>;
}

// What the list is doing: the first page, one page added above or below, or nothing
type Busy = 'initial' | 'up' | 'down' | null;

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
}

// The chapter list over the reader: a search field, the chapters page by page, and volume headings
const ChapterListPanel = ({
  novelSlug,
  sourceSlug,
  novelTitle,
  currentChapterId,
  mode,
  onClose,
  onOpenChapter,
  onOpenNovel,
}: ChapterListPanelProps) => {
  const { t } = useTranslation();
  const theme = useTheme();

  const [text, setText] = useState('');
  const [query, setQuery] = useState('');
  const [view, setView] = useState<ListView | null>(null);
  const [count, setCount] = useState<number | null>(null);
  const [busy, setBusy] = useState<Busy>('initial');
  const [failed, setFailed] = useState(false);

  const listRef = useRef<HTMLDivElement>(null);
  // Bumped by every first-page load: a response from an older load is dropped
  const session = useRef(0);
  const busyRef = useRef(false);
  // Height of the list before a page was added above it, so the rows in view stay put
  const anchorHeight = useRef<number | null>(null);
  const scrollToCurrent = useRef(false);
  const retryRef = useRef<() => void>(() => {});

  // Typing waits for a pause before searching
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(text.trim()), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [text]);

  // The first page: the chapter's own page, or page 1 of a search
  const runFirst = useCallback(async (search: string) => {
    const token = ++session.current;
    busyRef.current = true;
    anchorHeight.current = null;
    setBusy('initial');
    setFailed(false);
    try {
      const data = await chapterListCache.load(search
        ? { novelSlug, sourceSlug, page: 1, search }
        : { novelSlug, sourceSlug, around: currentChapterId });
      if (token !== session.current) return;
      if (!search) setCount(data.count);
      scrollToCurrent.current = !search;
      setView({ query: search, pages: new Map([[data.current_page, data]]) });
    } catch {
      if (token !== session.current) return;
      retryRef.current = () => { void runFirst(search); };
      setFailed(true);
    } finally {
      if (token === session.current) {
        busyRef.current = false;
        setBusy(null);
      }
    }
  }, [novelSlug, sourceSlug, currentChapterId]);

  useEffect(() => {
    void runFirst(query);
  }, [query, runFirst]);

  // The page above or below the loaded ones, when the scroll reaches that end
  const loadNeighbour = async (current: ListView, direction: 'up' | 'down') => {
    if (busyRef.current) return;
    const numbers = [...current.pages.keys()];
    const first = Math.min(...numbers);
    const last = Math.max(...numbers);
    const pageNumber = direction === 'up' ? first - 1 : last + 1;
    const totalPages = current.pages.get(last)?.total_pages ?? 0;
    if (pageNumber < 1 || pageNumber > totalPages) return;

    const token = session.current;
    busyRef.current = true;
    setBusy(direction);
    setFailed(false);
    if (direction === 'up') anchorHeight.current = listRef.current?.scrollHeight ?? null;
    retryRef.current = () => { void loadNeighbour(current, direction); };
    try {
      const data = await chapterListCache.load({ novelSlug, sourceSlug, page: pageNumber, search: current.query });
      if (token !== session.current) return;
      setView((previous) => {
        if (!previous || previous.query !== current.query) return previous;
        const pages = new Map(previous.pages);
        pages.set(pageNumber, data);
        return { ...previous, pages };
      });
    } catch {
      if (token !== session.current) return;
      anchorHeight.current = null;
      setFailed(true);
    } finally {
      if (token === session.current) {
        busyRef.current = false;
        setBusy(null);
      }
    }
  };

  // Keeps the scroll where it was when a page is added above, and brings the current chapter into view at open
  useLayoutEffect(() => {
    const list = listRef.current;
    if (!list || !view) return;
    if (anchorHeight.current !== null) {
      list.scrollTop += list.scrollHeight - anchorHeight.current;
      anchorHeight.current = null;
    } else if (scrollToCurrent.current) {
      scrollToCurrent.current = false;
      const current = list.querySelector<HTMLElement>('[aria-current="true"]');
      if (current) list.scrollTop = current.offsetTop - list.clientHeight / 3;
    }
  }, [view]);

  const shown = view && view.query === query ? view : null;

  const handleScroll = () => {
    const list = listRef.current;
    if (!list || !shown) return;
    const numbers = [...shown.pages.keys()];
    if (list.scrollTop < EDGE_PX && Math.min(...numbers) > 1) {
      void loadNeighbour(shown, 'up');
      return;
    }
    const totalPages = shown.pages.get(Math.max(...numbers))?.total_pages ?? 0;
    if (list.scrollHeight - list.scrollTop - list.clientHeight < EDGE_PX && Math.max(...numbers) < totalPages) {
      void loadNeighbour(shown, 'down');
    }
  };

  // Rows and volume headings, in page order. Search results have no headings.
  const rows: ReactNode[] = [];
  let previousVolume: number | undefined;
  if (shown) {
    const numbers = [...shown.pages.keys()].sort((a, b) => a - b);
    for (const number of numbers) {
      const page = shown.pages.get(number);
      if (!page) continue;
      for (const chapter of page.chapters) {
        const title = chapter.volume_title?.trim();
        // Same headings as the chapter list page: the volume's title, else its number, none for an untitled volume 0
        if (page.has_volumes && !shown.query && chapter.volume !== previousVolume && (title || chapter.volume !== 0)) {
          rows.push(
            <Typography
              key={`volume-${chapter.id}`}
              component="div"
              sx={{
                position: 'sticky',
                top: 0,
                zIndex: 1,
                bgcolor: 'background.paper',
                px: 2,
                py: 0.75,
                fontSize: 12,
                fontWeight: 600,
                color: 'text.secondary',
              }}
            >
              {title || t('chapterList.volume', { volume: chapter.volume })}
            </Typography>,
          );
        }
        previousVolume = chapter.volume;

        const isCurrent = chapter.chapter_id === currentChapterId;
        rows.push(
          <ListItemButton
            key={chapter.id}
            aria-current={isCurrent ? 'true' : undefined}
            disabled={!chapter.has_content}
            onClick={() => (isCurrent ? onClose() : onOpenChapter(chapter.chapter_id))}
            sx={{
              height: ROW_HEIGHT,
              px: 2,
              gap: 1.5,
              contentVisibility: 'auto',
              containIntrinsicSize: `${ROW_HEIGHT}px`,
              bgcolor: isCurrent ? 'action.selected' : undefined,
              // Every row has the bar, so the text does not move when the current row changes
              borderInlineStart: `3px solid ${isCurrent ? theme.palette.primary.main : 'transparent'}`,
              color: chapter.has_content ? 'text.primary' : 'text.disabled',
              fontWeight: isCurrent ? 600 : undefined,
            }}
          >
            <Typography component="span" sx={{ width: 34, flexShrink: 0, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
              {chapter.chapter_id}
            </Typography>
            <Typography component="span" noWrap sx={{ flex: 1, minWidth: 0, color: 'inherit', fontWeight: 'inherit' }}>
              {getChapterLabel(t, chapter.title, chapter.chapter_id)}
            </Typography>
          </ListItemButton>,
        );
      }
    }
  }

  const countText = count !== null ? t('units.chapters', { count }) : '';
  // A search that finds nothing
  const isEmpty = shown !== null && shown.query !== '' && rows.length === 0;

  return (
    <>
      {/* Phones: the list overlays the text, and a tap on the rest of the screen closes it */}
      {mode === 'phone' && (
        <Box
          aria-hidden
          onClick={onClose}
          sx={{
            position: 'fixed',
            inset: 0,
            zIndex: theme.zIndex.appBar + 2,
            bgcolor: 'rgba(0, 0, 0, 0.4)',
          }}
        />
      )}

      <ReaderPanelFrame
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
            {countText && `${countText} · `}
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

        <Box
          ref={listRef}
          onScroll={handleScroll}
          // Native scroll anchoring would fight the compensation made when a page is added above
          sx={{ position: 'relative', flex: 1, minHeight: 0, overflowY: 'auto', overflowAnchor: 'none', borderTop: 1, borderColor: 'divider' }}
        >
          {busy === 'up' && <ListSkeleton rows={2} />}
          {!shown && busy === 'initial' && <ListSkeleton rows={SKELETON_ROWS} />}
          {rows}
          {busy === 'down' && <ListSkeleton rows={2} />}

          {isEmpty && (
            <Typography sx={{ px: 2, py: 3, textAlign: 'center', color: 'text.secondary' }}>
              {t('readerChapters.noMatch')}
            </Typography>
          )}

          {failed && (
            <Box sx={{ px: 2, py: 2, textAlign: 'center' }}>
              <Typography color="error" sx={{ mb: 1 }}>
                {t('chapterList.loadFailed')}
              </Typography>
              <Link component="button" onClick={() => retryRef.current()}>
                {t('readerChapters.retry')}
              </Link>
            </Box>
          )}
        </Box>
      </ReaderPanelFrame>
    </>
  );
};

// Placeholder rows while a page loads, the height of the real rows
const ListSkeleton = ({ rows }: { rows: number }) => (
  <>
    {Array.from({ length: rows }, (_, index) => (
      <Skeleton key={index} variant="rectangular" height={ROW_HEIGHT} sx={{ mx: 2, my: 0.5 }} />
    ))}
  </>
);

export default ChapterListPanel;
