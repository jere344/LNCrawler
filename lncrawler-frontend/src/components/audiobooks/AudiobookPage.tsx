import { useEffect, useState } from 'react';
import { Link as RouterLink, useParams, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Box,
  Button,
  Container,
  Divider,
  Grid,
  Menu,
  MenuItem,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import LibraryMusicIcon from '@mui/icons-material/LibraryMusic';
import LinkIcon from '@mui/icons-material/Link';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import { audiobookService } from '@services/audiobook.service';
import type { AudiobookDetail } from '@models/audiobook_types';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { useAuth } from '@context/AuthContext';
import { useNotification } from '@context/NotificationContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { audiobookPath, audiobookRevealKey, readLocalProgress } from '@utils/audiobook';
import { languageCodeToName, languageFlagUrl } from '@utils/Misc';
import { formatClock, formatHours } from '@utils/duration';
import type { ApiError } from '@services/api';
import BreadcrumbNav from '../common/BreadcrumbNav';
import NotFoundRedirect from '../common/NotFoundRedirect';
import SeoMeta from '../common/SeoMeta';
import NovelSynopsis from '../novels/common/NovelSynopsis';
import AudiobookPartCard from './AudiobookPartCard';
import { AudiobookPageSkeleton } from './AudiobooksSkeleton';

// Cast is collapsed past this many members.
const CAST_PREVIEW = 12;

// The resume point of the button: the server's when logged in, this browser's saved position otherwise.
const resumePointOf = (detail: AudiobookDetail, loggedIn: boolean): { chapter: number; position: number } | null => {
  if (loggedIn) {
    const progress = detail.progress;
    return progress && !progress.finished
      ? { chapter: progress.chapter_number ?? 1, position: progress.position_s }
      : null;
  }
  const local = readLocalProgress(detail.slug, detail.language);
  if (!local || local.finished) return null;
  const chapters = detail.parts.flatMap((part) => part.chapters ?? []);
  const chapter = chapters.find((item) => item.chapter_id === local.chapter_id);
  return { chapter: chapter?.number ?? 1, position: local.position_s };
};

const AudiobookPage = () => {
  const { t } = useTranslation();
  const { slug = '' } = useParams();
  const [searchParams] = useSearchParams();
  const lang = searchParams.get('lang') || 'en';
  const { playAudiobook } = useAudioPlayer();
  const { isAuthenticated } = useAuth();
  const { notify } = useNotification();
  const { isBlurred } = useAdultContent();

  const [detail, setDetail] = useState<AudiobookDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [notFound, setNotFound] = useState(false);
  const [castOpen, setCastOpen] = useState(false);
  const [subscribeAnchor, setSubscribeAnchor] = useState<HTMLElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    // The shown book belongs to the previous slug or lang: drop it, so the skeleton shows while this one loads.
    setDetail(null);
    setLoading(true);
    setError(false);
    setNotFound(false);
    audiobookService
      .detail(slug, lang)
      .then((response) => { if (!cancelled) setDetail(response); })
      .catch((err: ApiError) => {
        if (cancelled) return;
        if (err.response?.status === 404) setNotFound(true);
        else setError(true);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [slug, lang]);

  if (notFound) return <NotFoundRedirect />;
  if (loading && !detail) return <AudiobookPageSkeleton />;
  if (error || !detail) {
    return (
      <Container maxWidth="lg" sx={{ py: 3 }}>
        <Alert severity="error">{t('audiobooks.loadError')}</Alert>
      </Container>
    );
  }

  const cover = detail.cover_url || detail.cover_jpg_url;
  const languageName = languageCodeToName(t, detail.language);
  const revealKey = audiobookRevealKey(detail.slug, detail.language);
  const blurred = isBlurred(detail.is_adult, revealKey);
  const progress = detail.progress;
  const resume = resumePointOf(detail, isAuthenticated);
  const feedWithoutScheme = detail.feed_url.replace(/^https?:\/\//, '');
  const sourceLink = `/novels/${encodeURIComponent(detail.novel_slug)}/${encodeURIComponent(detail.source_slug)}`;
  const castMembers = detail.cast;
  // The section only shows once some character has a description (see the worker contract).
  const castShown = castMembers.some((member) => Boolean(member.description));
  const visibleCast = castOpen ? castMembers : castMembers.slice(0, CAST_PREVIEW);

  const copyFeed = async () => {
    setSubscribeAnchor(null);
    try {
      await navigator.clipboard.writeText(detail.feed_url);
      notify({ message: t('audiobooks.feedCopied'), severity: 'success' });
    } catch {
      notify({ message: t('audiobooks.feedCopyError'), severity: 'error' });
    }
  };

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <SeoMeta
        title={t('audiobooks.pageTitle', { title: detail.title })}
        description={detail.synopsis.slice(0, 160)}
        image={cover ?? undefined}
        type="book"
        canonical={`${window.location.origin}/audiobooks/${encodeURIComponent(detail.slug)}/`}
      />
      <BreadcrumbNav
        items={[
          { label: t('audiobooks.title'), link: '/audiobooks', icon: <LibraryMusicIcon fontSize="inherit" /> },
          { label: detail.title, icon: <HeadphonesIcon fontSize="inherit" /> },
        ]}
      />

      <Grid container spacing={3} sx={{ mt: 1 }}>
        <Grid size={{ xs: 12, sm: 4, md: 3 }}>
          <Box sx={{ position: 'relative', aspectRatio: '1 / 1', borderRadius: 2, overflow: 'hidden', bgcolor: 'action.hover', boxShadow: 3 }}>
            {cover ? (
              <Box component="img" src={cover} alt={detail.title} sx={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block', filter: blurred ? 'blur(16px)' : 'none' }} />
            ) : (
              <Box sx={{ width: '100%', height: '100%', display: 'grid', placeItems: 'center' }}>
                <HeadphonesIcon sx={{ fontSize: 72, color: 'text.disabled' }} />
              </Box>
            )}
            <AdultBadge isAdult={detail.is_adult} novelId={revealKey} />
            <Box sx={{
              position: 'absolute', top: 8, right: 8, bgcolor: 'rgba(0,0,0,0.7)', color: 'white', px: 1, py: 0.3, borderRadius: 1,
              fontSize: '0.75rem', fontWeight: 'bold', display: 'flex', alignItems: 'center', gap: 0.5, textTransform: 'uppercase',
            }}>
              <Box
                component="img"
                src={languageFlagUrl(detail.language)}
                alt={languageName}
                sx={{ width: 20, height: 15, objectFit: 'cover', borderRadius: '2px' }}
              />
              {detail.language}
            </Box>
          </Box>
        </Grid>

        <Grid size={{ xs: 12, sm: 8, md: 9 }}>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>{detail.title}</Typography>
          <Typography variant="body2" color="text.secondary">{t('audiobooks.generatedDisclaimer')}</Typography>
          {detail.is_dmca && (
            <Alert severity="info" sx={{ mt: 1 }}>{t('audiobooks.dmcaNotice')}</Alert>
          )}
          {detail.authors.length > 0 && (
            <Typography variant="subtitle1" color="text.secondary">{detail.authors.join(', ')}</Typography>
          )}
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('audiobooks.heroMeta', { hours: formatHours(detail.duration_s, t), parts: detail.parts.length, chapters: detail.chapters })}
          </Typography>
          {detail.credits.narrator && (
            <Typography variant="body2" color="text.secondary">{detail.credits.narrator}</Typography>
          )}
          {detail.other_languages.length > 0 && (
            <Stack direction="row" spacing={1} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap', mt: 1 }}>
              <Typography variant="body2" color="text.secondary">{t('audiobooks.alsoAvailable')}</Typography>
              {detail.other_languages.map((code) => (
                <Tooltip key={code} title={languageCodeToName(t, code)}>
                  <Box
                    component={RouterLink}
                    to={audiobookPath(detail.slug, code)}
                    aria-label={languageCodeToName(t, code)}
                    sx={{ display: 'block', width: 30, lineHeight: 0, border: '1px solid rgb(0, 0, 0)', borderRadius: 1, boxShadow: '0 2px 4px rgba(0,0,0,0.4)' }}
                  >
                    <Box
                      component="img"
                      src={languageFlagUrl(code)}
                      alt=""
                      sx={{ display: 'block', width: 30, height: 20, objectFit: 'cover', borderRadius: '2px' }}
                    />
                  </Box>
                </Tooltip>
              ))}
            </Stack>
          )}

          <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', mt: 2 }}>
            {resume ? (
              <Button
                variant="contained"
                startIcon={<PlayArrowIcon />}
                onClick={() => void playAudiobook(detail.slug, lang, { detail })}
              >
                {t('audiobooks.resumeAt', { chapter: resume.chapter, time: formatClock(resume.position) })}
              </Button>
            ) : (
              <Button variant="contained" startIcon={<PlayArrowIcon />} onClick={() => void playAudiobook(detail.slug, lang, { detail })}>
                {t('audiobooks.listen')}
              </Button>
            )}
            <Button variant="outlined" startIcon={<MenuBookIcon />} component={RouterLink} to={sourceLink}>
              {t('audiobooks.readNovel')}
            </Button>
            <Button
              variant="outlined"
              startIcon={<PodcastsIcon />}
              aria-haspopup="menu"
              onClick={(event) => setSubscribeAnchor(event.currentTarget)}
            >
              {t('audiobooks.subscribe')}
            </Button>
            <Menu anchorEl={subscribeAnchor} open={Boolean(subscribeAnchor)} onClose={() => setSubscribeAnchor(null)}>
              <MenuItem onClick={() => void copyFeed()}>
                <LinkIcon fontSize="small" sx={{ mr: 1 }} />
                {t('audiobooks.copyFeed')}
              </MenuItem>
              <MenuItem component="a" href={`antennapod-subscribe://${feedWithoutScheme}`} onClick={() => setSubscribeAnchor(null)}>
                {t('audiobooks.openAntennaPod')}
              </MenuItem>
              <MenuItem component="a" href={`pktc://subscribe/${feedWithoutScheme}`} onClick={() => setSubscribeAnchor(null)}>
                {t('audiobooks.openPocketCasts')}
              </MenuItem>
            </Menu>
          </Stack>

          {detail.synopsis && (
            <Box sx={{ mt: 3 }}>
              <NovelSynopsis synopsis={detail.synopsis} />
            </Box>
          )}
        </Grid>
      </Grid>

      {castShown && (
        <Box sx={{ mt: 4 }}>
          <Typography variant="h6" component="h2" sx={{ fontWeight: 600 }}>{t('audiobooks.castTitle')}</Typography>
          <Box component="ul" sx={{ listStyle: 'none', p: 0, m: 0, mt: 1 }}>
            {visibleCast.map((member, index) => (
              <Box component="li" key={`${member.name}-${index}`} sx={{ py: 0.5 }}>
                <Typography variant="body2" sx={{ fontWeight: 700 }}>{member.name}</Typography>
                {member.description && (
                  <Typography variant="body2" color="text.secondary">{member.description}</Typography>
                )}
              </Box>
            ))}
          </Box>
          {castMembers.length > CAST_PREVIEW && (
            <Button size="small" onClick={() => setCastOpen(open => !open)} sx={{ mt: 1 }}>
              {castOpen ? t('audiobooks.showLess') : t('audiobooks.showAll', { count: castMembers.length })}
            </Button>
          )}
        </Box>
      )}

      <Divider sx={{ my: 4 }} />

      <Typography variant="h6" component="h2" sx={{ fontWeight: 600, mb: 1 }}>{t('audiobooks.partsTitle')}</Typography>
      <Stack spacing={1.5}>
        {detail.parts.map(part => (
          <AudiobookPartCard
            key={part.index}
            slug={detail.slug}
            lang={lang}
            part={part}
            progress={progress}
            hasVolumes={detail.has_volumes}
          />
        ))}
      </Stack>
    </Container>
  );
};

export default AudiobookPage;
