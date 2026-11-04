import { useMemo, type MouseEvent, type RefObject } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Container,
  Typography,
  Paper,
  Box,
  IconButton,
  Button,
} from '@mui/material';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import SettingsIcon from '@mui/icons-material/Settings';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import type { CommentPreview } from '@models/comments_types';
import { getChapterLabel } from '@utils/Misc';
import BreadcrumbNav from '../../common/BreadcrumbNav';
import ReaderContent from './ReaderContent';
import ReaderControls from '../controls/ReaderControls';
import ReaderViewport from '../viewport/ReaderViewport';
import ChapterCommentsCard from './ChapterCommentsCard';
import { reservedMargin } from '../panels/panelLayout';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';
import { useReaderSettings } from '../hooks/useReaderSettings';
import type { MarkReadProps } from '../controls/readerBarTypes';
import { TTS_BAR_HEIGHT } from '../tts/ttsTypes';
import type { SwipeableHandlers } from 'react-swipeable';

// The listen and settings buttons at the end of the title row
const ICON_BUTTON_SX = { color: 'text.secondary', '&:hover': { color: 'primary.main' }, scale: '1.2' };

interface ChapterArticleProps {
  chapter: IChapterContent;
  novelSlug?: string;
  sourceSlug?: string;
  // Sentinel placed after the chapter text, watched to detect the reader reaching its end
  endOfChapterRef: RefObject<HTMLDivElement | null>;
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
  ttsOpen: boolean;
  // Height of the audiobook mini bar, kept clear of the end of the chapter
  barHeight: number;
  // Width in px kept clear at the start edge, so the text is not covered by the chapter list
  reservedStart: number;
  // Width in px kept clear at the end edge, so the text is not covered by the display panel
  reservedEnd: number;
}

// The article: breadcrumbs, title, the text, the comments summary and the controls at its end
const ChapterArticle = ({
  chapter,
  novelSlug,
  sourceSlug,
  endOfChapterRef,
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
  ttsOpen,
  barHeight,
  reservedStart,
  reservedEnd,
}: ChapterArticleProps) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const chapterLabel = getChapterLabel(t, chapter.title, chapter.chapter_id);

  // Reused across the parent's re-renders (TTS progress) so the text is not re-rendered; the settings object only changes when a setting is written
  const chapterContent = useMemo(
    () => <ReaderContent chapter={chapter} settings={settings} />,
    [chapter, settings]
  );

  // The reader leaves through its own navigation, so its panels do not stay in the history. A modified click keeps the link's own behaviour.
  const handleChapterListClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onOpenChapterList();
  };

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
  
          <Paper
            elevation={3}
            sx={{
              p: { xs: 2, md: 4 },
              mt: 2,
              mb: 8,
              backgroundColor: settings.backgroundColor || undefined,
              color: settings.fontColor || undefined,
              mx: `${settings.margin}%`
            }}
          >
            {/* Chapter title and content */}
            <Box sx={{ mb: 3 }}>
              <Typography variant="h5" gutterBottom align="center" sx={{ color: settings.fontColor || undefined }}>
                {chapterLabel}
              </Typography>
              <Typography variant="subtitle1" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                {chapter.novel_title}
              </Typography>
            </Box>
  
            {/* Listen and settings, kept on every layout so screen reader users can always reach them */}
            <Box sx={{
              borderBottom: 1,
              borderColor: 'divider',
              mb: 2,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end'
            }}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <IconButton
                  onClick={onListen}
                  aria-label={t('reader.listen')}
                  sx={ICON_BUTTON_SX}
                >
                  <HeadphonesIcon />
                </IconButton>
                <IconButton
                  onClick={onOpenSettings}
                  aria-label={t('reader.openSettings')}
                  sx={ICON_BUTTON_SX}
                >
                  <SettingsIcon />
                </IconButton>
              </Box>
            </Box>
  
            {/* Narration hint: the chapter has a recording but the listen button uses client TTS */}
            {chapter.audio_url && !settings.ttsPreferAudiobook && (
              <Box sx={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', columnGap: 1, mb: 2,
                px: 1.5, py: 0.5, borderRadius: 1, bgcolor: 'action.hover',
              }}>
                {/* Wraps onto its own line on phones rather than squeezing next to the button */}
                <Typography variant="body2" color="text.secondary" sx={{ flex: '1 1 12em' }}>{t('audioPlayer.narratedHint')}</Typography>
                <Button
                  size="small"
                  startIcon={<HeadphonesIcon />}
                  onClick={onNarrate}
                  sx={{ flexShrink: 0 }}
                >
                  {t('audioPlayer.listenToNarration')}
                </Button>
              </Box>
            )}
  
            {/* Chapter content */}
            <Box sx={{ mb: 4 }}>
              <ReaderViewport
                controlsTrigger={settings.controlsTrigger}
                tapProps={tapProps}
                dimLevel={settings.dimLevel}
                nightMode={settings.nightMode}
                nightModeStrength={settings.nightModeStrength}
                nightModeScheduleEnabled={settings.nightModeScheduleEnabled}
                nightModeStartTime={settings.nightModeStartTime}
                nightModeEndTime={settings.nightModeEndTime}
              >
                {chapterContent}
              </ReaderViewport>
              <Box ref={endOfChapterRef} aria-hidden="true" sx={{ height: 1 }} />
            </Box>

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
            <ReaderControls
              prevChapter={chapter.prev_chapter}
              nextChapter={chapter.next_chapter}
              isAuthenticated={showMarkRead}
              markReadSuccess={markReadSuccess}
              markingAsRead={markingAsRead}
              onMarkAsRead={onMarkAsRead}
              onPrevious={onPrevious}
              onNext={onNext}
            />
          </Paper>
        </Container>
      </Box>
      {ttsOpen && <Box sx={{ height: { xs: TTS_BAR_HEIGHT.mobile, sm: TTS_BAR_HEIGHT.desktop + 16 } }} />}
      {/* Keeps the end of the chapter clear of the audiobook mini bar */}
      <Box sx={{ height: barHeight }} />
    </>
  );
};

export default ChapterArticle;
