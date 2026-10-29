import { Fragment, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Box,
  Button,
  ButtonGroup,
  Chip,
  Collapse,
  IconButton,
  LinearProgress,
  ListItemText,
  Menu,
  MenuItem,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import ArrowDropDownIcon from '@mui/icons-material/ArrowDropDown';
import CheckIcon from '@mui/icons-material/Check';
import DownloadIcon from '@mui/icons-material/Download';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import { audiobookService } from '@services/audiobook.service';
import type { AudiobookFormat, AudiobookPart, AudiobookVolume, ListeningProgress } from '@models/audiobook_types';
import { useNotification } from '@context/NotificationContext';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { formatClock, formatHours } from '@utils/duration';
import { isApplePlatform } from '@utils/platform';

// Approximate AAC size per second of audio, used before the file exists (the Opus size is known).
const AAC_BYTES_PER_S = 8 * 1024;

// Download state of one part: idle or waiting for a build (with its progress).
type DownloadState =
  | { status: 'idle' }
  | { status: 'building'; progress: number | null };

interface AudiobookPartCardProps {
  slug: string;
  lang: string;
  part: AudiobookPart;
  progress: ListeningProgress | null;
  hasVolumes: boolean;
}

const formatSize = (bytes: number): string => `${Math.max(1, Math.round(bytes / (1024 * 1024)))} MB`;

// Codec names of the download formats, shown as they are.
const FORMAT_NAMES: Record<AudiobookFormat, string> = { opus: 'Opus', aac: 'AAC' };

// One part of an audiobook: the playable chapters, the download split button and the chapter list.
// While a file is being built the card polls the backend every `retryAfter` seconds.
const AudiobookPartCard = ({ slug, lang, part, progress, hasVolumes }: AudiobookPartCardProps) => {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const { playAudiobook } = useAudioPlayer();
  const [download, setDownload] = useState<DownloadState>({ status: 'idle' });
  const [format, setFormat] = useState<AudiobookFormat>(isApplePlatform() ? 'aac' : 'opus');
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [chaptersOpen, setChaptersOpen] = useState(
    () => Boolean(part.chapters?.some(chapter => chapter.chapter_id === progress?.chapter_id)),
  );
  const pollTimer = useRef<number | null>(null);
  const linkRef = useRef<HTMLAnchorElement | null>(null);
  // False once unmounted: a request still in flight must not schedule a poll or update the card.
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Stop polling on unmount or when the part changes.
  useEffect(() => () => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
  }, [part.index]);

  const inProduction = part.state === 'in_production';
  const sizeLabel = (fmt: AudiobookFormat): string => {
    if (fmt === 'opus' && part.size_bytes) return formatSize(part.size_bytes);
    return formatSize(part.duration_s * AAC_BYTES_PER_S);
  };

  const startDownload = async (fmt: AudiobookFormat) => {
    if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    try {
      const result = await audiobookService.prepare(slug, lang, part.index, fmt);
      if (!mounted.current) return;
      if (result.status === 'ready') {
        setDownload({ status: 'idle' });
        // A hidden anchor starts the file download without leaving the page.
        linkRef.current?.setAttribute('href', result.url);
        linkRef.current?.click();
      } else {
        setDownload({ status: 'building', progress: result.progress });
        pollTimer.current = window.setTimeout(() => void startDownload(fmt), result.retryAfter * 1000);
      }
    } catch {
      if (!mounted.current) return;
      setDownload({ status: 'idle' });
      notify({ message: t('audiobooks.downloadError'), severity: 'error' });
    }
  };

  const chooseFormat = (fmt: AudiobookFormat) => {
    setFormat(fmt);
    setMenuAnchor(null);
    void startDownload(fmt);
  };

  const busy = download.status === 'building';
  const buildProgress = download.status === 'building' ? download.progress : null;
  const firstChapter = part.chapters?.[0];

  // A volume's title as the source gives it (often "Volume 1" already), or its number, as in the EPUB volume menu.
  const volumeText = (volume: AudiobookVolume): string =>
    volume.title || t('audiobooks.volumeNumbered', { number: volume.number });
  // Only shown for a book whose chapters span several volumes.
  const volumes = hasVolumes ? part.volumes : [];
  const volumeLabels = new Map(volumes.map((volume) => [volume.number, volumeText(volume)]));
  const volumeLabel = volumes.length === 0
    ? null
    : volumes.length === 1
      ? volumeText(volumes[0])
      : `${volumeText(volumes[0])} – ${volumeText(volumes[volumes.length - 1])}`;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ justifyContent: 'space-between', alignItems: { sm: 'center' } }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            {t('audiobooks.partTitle', { index: part.index })}
          </Typography>
          {inProduction ? (
            <Typography variant="body2" color="text.secondary">
              {volumeLabel && `${volumeLabel} · `}
              {part.progress !== null
                ? t('audiobooks.partInProduction', { progress: Math.round(part.progress * 100) })
                : t('audiobooks.partQueued')}
              {' · '}
              {t('audiobooks.partEstimated', { hours: formatHours(part.estimated_duration_s, t) })}
            </Typography>
          ) : (
            <Typography variant="body2" color="text.secondary">
              {volumeLabel && `${volumeLabel} · `}
              {t('audiobooks.partMeta', {
                start: part.chapter_start,
                end: part.chapter_end,
                hours: formatHours(part.duration_s, t),
                size: sizeLabel(format),
              })}
            </Typography>
          )}
        </Box>

        {!inProduction && (
          <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<PlayArrowIcon />}
              disabled={!firstChapter}
              onClick={() => firstChapter && void playAudiobook(slug, lang, { chapterId: firstChapter.chapter_id })}
            >
              {t('audiobooks.playPart')}
            </Button>
            <ButtonGroup variant="contained" size="small" disabled={busy}>
              <Button
                startIcon={<DownloadIcon />}
                onClick={() => void startDownload(format)}
                aria-label={t('audiobooks.downloadPart', { index: part.index })}
              >
                {busy ? t('audiobooks.preparing', { progress: Math.round((buildProgress ?? 0) * 100) }) : t('audiobooks.downloadFormat', { format: FORMAT_NAMES[format] })}
              </Button>
              <Button
                size="small"
                aria-label={t('audiobooks.downloadFormats')}
                aria-haspopup="menu"
                onClick={(event) => setMenuAnchor(event.currentTarget)}
              >
                <ArrowDropDownIcon />
              </Button>
            </ButtonGroup>
            <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
              <MenuItem selected={format === 'opus'} onClick={() => chooseFormat('opus')}>
                <ListItemText primary={t('audiobooks.formatOpus')} secondary={t('audiobooks.formatOpusHint', { size: sizeLabel('opus') })} />
              </MenuItem>
              <MenuItem selected={format === 'aac'} onClick={() => chooseFormat('aac')}>
                <ListItemText primary={t('audiobooks.formatAac')} secondary={t('audiobooks.formatAacHint', { size: sizeLabel('aac') })} />
              </MenuItem>
            </Menu>
            <a ref={linkRef} hidden download aria-hidden="true" href="#" tabIndex={-1}>{/* download target */}</a>
          </Stack>
        )}
      </Stack>

      {busy && (
        <LinearProgress
          variant={buildProgress === null ? 'indeterminate' : 'determinate'}
          value={(buildProgress ?? 0) * 100}
          aria-label={t('audiobooks.preparingLabel')}
          sx={{ mt: 1.5 }}
        />
      )}

      {!inProduction && part.chapters && part.chapters.length > 0 && (
        <>
          <Button
            size="small"
            onClick={() => setChaptersOpen(open => !open)}
            endIcon={<ExpandMoreIcon sx={{ transform: chaptersOpen ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />}
            aria-expanded={chaptersOpen}
            sx={{ mt: 1 }}
          >
            {t('audiobooks.chapterCount', { count: part.chapters.length })}
          </Button>
          <Collapse in={chaptersOpen}>
            <Box component="ol" sx={{ listStyle: 'none', p: 0, m: 0 }}>
              {part.chapters.map((chapter, index, chapters) => {
                const current = chapter.chapter_id === progress?.chapter_id;
                const listened = Boolean(progress && !current && progress.chapter_number !== null && chapter.number < progress.chapter_number);
                // A sub-heading row at each volume, only when the part spans several (the meta line names a single one)
                const newVolume = volumes.length > 1 && (index === 0 || chapter.volume !== chapters[index - 1].volume);
                return (
                  <Fragment key={chapter.chapter_id}>
                    {newVolume && (
                      <Box component="li" sx={{ pt: 1, pb: 0.5, px: 1 }}>
                        <Typography variant="subtitle2" color="text.secondary">
                          {volumeLabels.get(chapter.volume) ?? volumeText({ number: chapter.volume, title: chapter.volume_title })}
                        </Typography>
                      </Box>
                    )}
                    <Box
                      component="li"
                      sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5, px: 1, borderRadius: 1, bgcolor: current ? 'action.selected' : 'transparent' }}
                    >
                      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 40 }}>{chapter.number}</Typography>
                      <Typography variant="body2" noWrap sx={{ flex: 1, minWidth: 0 }}>{chapter.title}</Typography>
                      {current && progress && <Chip size="small" color="primary" label={formatClock(progress.position_s)} />}
                      {listened && <CheckIcon fontSize="small" color="success" aria-label={t('audiobooks.chapterListened')} />}
                      <Typography variant="caption" color="text.secondary">{formatClock(chapter.duration_s)}</Typography>
                      <IconButton
                        size="small"
                        aria-label={t('audiobooks.playChapter', { number: chapter.number })}
                        onClick={() => void playAudiobook(slug, lang, { chapterId: chapter.chapter_id })}
                      >
                        <PlayArrowIcon fontSize="small" />
                      </IconButton>
                    </Box>
                  </Fragment>
                );
              })}
            </Box>
          </Collapse>
        </>
      )}
    </Paper>
  );
};

export default AudiobookPartCard;
