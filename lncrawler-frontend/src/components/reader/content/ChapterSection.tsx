import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Typography,
  Box,
  IconButton,
  Button,
} from '@mui/material';
import SettingsIcon from '@mui/icons-material/Settings';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import ReaderContent from './ReaderContent';
import ReaderViewport from '../viewport/ReaderViewport';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { sectionKeyOf } from '../hooks/chapterRange';

// The listen and settings buttons at the end of the title row
const ICON_BUTTON_SX = { color: 'text.secondary', '&:hover': { color: 'primary.main' }, scale: '1.2' };

interface ChapterSectionProps {
  chapter: IChapterContent;
  // id of the text element; the first section keeps 'reader-content', which TTS looks up
  contentId: string;
  // Infinite mode: each chapter is a named region, so screen reader users can jump between them
  landmark?: boolean;
  tapProps: ReaderTapProps;
  onListen: () => void;
  onOpenSettings: () => void;
  onNarrate: () => void;
  // Infinite mode draws the header once above the list, so the chapters read as one text
  header?: boolean;
}

interface ChapterSectionHeaderProps {
  chapter: IChapterContent;
  onListen: () => void;
  onOpenSettings: () => void;
}

// The chapter's title, novel and the listen and settings row; once at the top of the page in infinite mode
export const ChapterSectionHeader = ({ chapter, onListen, onOpenSettings }: ChapterSectionHeaderProps) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const chapterLabel = chapter.display_title;

  return (
    <>
      {/* Chapter title and novel */}
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
    </>
  );
};

// One chapter's title, text and listen controls, as a section of the article
const ChapterSection = ({
  chapter,
  contentId,
  landmark = false,
  header = true,
  tapProps,
  onListen,
  onOpenSettings,
  onNarrate,
}: ChapterSectionProps) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const chapterLabel = chapter.display_title;

  // Reused across the parent's re-renders (TTS progress) so the text is not re-rendered; the settings object only changes when a setting is written
  const chapterContent = useMemo(
    () => <ReaderContent chapter={chapter} settings={settings} contentId={contentId} />,
    [chapter, settings, contentId]
  );

  return (
    <Box
      component={landmark ? 'section' : 'div'}
      aria-label={landmark ? chapterLabel : undefined}
      data-chapter-key={sectionKeyOf(chapter)}
    >
      {header && <ChapterSectionHeader chapter={chapter} onListen={onListen} onOpenSettings={onOpenSettings} />}

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
          centerLongPress={settings.centerLongPress}
          tapProps={tapProps}
          settings={settings}
        >
          {chapterContent}
        </ReaderViewport>
      </Box>
    </Box>
  );
};

export default ChapterSection;
