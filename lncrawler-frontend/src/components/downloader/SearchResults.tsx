import { useState, useEffect, type SyntheticEvent } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Box,
  Typography,
  CircularProgress,
  Alert,
  Card,
  CardActionArea,
  Chip,
  Button,
  Divider,
  Grid,
  LinearProgress,
  Paper,
  Stack,
  Container,
  Tooltip
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useTranslation } from 'react-i18next';
import { searchService, jobService } from '@services/api';
import { SearchStatus, SearchResult, SearchResults as SearchResultsType } from '@models/downloader_types';
import defaultCover from '@assets/default-cover.jpg';
import DownloadStepper from './DownloadStepper';

const POLLING_INTERVAL = 1000; // 1 second
const MAX_CONSECUTIVE_FAILURES = 3;

const countSources = (groups: SearchResult[]) =>
  groups.reduce((total, group) => total + group.sources.length, 0);

const getHostname = (url: string) => {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
};

const SearchResults = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { jobId } = useParams<{ jobId: string }>();
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [results, setResults] = useState<SearchResultsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Chained timeouts: the next request starts only after the previous one settled
  useEffect(() => {
    if (!jobId) return;

    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let shownCount = 0;
    let failures = 0;

    const poll = async () => {
      try {
        const statusResponse = await searchService.getSearchStatus(jobId);
        if (!active) return;
        failures = 0;

        if (statusResponse.status === 'error') {
          setError(statusResponse.message || t('downloader.fetchSearchFailed'));
          setLoading(false);
          return;
        }

        if ((statusResponse.result_count ?? 0) !== shownCount) {
          const resultsResponse = await searchService.getSearchResults(jobId);
          if (!active) return;
          if (resultsResponse.status !== 'success') {
            setError(resultsResponse.message || t('downloader.fetchSearchFailed'));
            setLoading(false);
            return;
          }
          shownCount = countSources(resultsResponse.results);
          setResults(resultsResponse);
        }

        setStatus(statusResponse);
        setLoading(false);

        const finished = statusResponse.search_completed || statusResponse.status === 'failed' || !!statusResponse.error;
        if (!finished) {
          timeoutId = setTimeout(poll, POLLING_INTERVAL);
        }
      } catch (err) {
        if (!active) return;
        console.error('Error fetching search status:', err);
        failures += 1;
        if (failures >= MAX_CONSECUTIVE_FAILURES) {
          setError(t('downloader.fetchSearchFailed'));
          setLoading(false);
          return;
        }
        timeoutId = setTimeout(poll, POLLING_INTERVAL);
      }
    };

    setLoading(true); // Reset loading for a new search
    setStatus(null);  // Reset status
    setResults(null); // Reset results
    setError(null);   // Reset error
    poll();

    return () => {
      active = false;
      clearTimeout(timeoutId);
    };
    // Intentionally keyed on jobId only; the loop reads t from its first render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const handleCancel = async () => {
    if (!jobId) return;
    try {
      await jobService.cancelJob(jobId);
    } catch {
      // Leaving the page is enough when the cancel request fails
    }
    navigate('/download/');
  };

  if (loading) { // Simplified loading condition
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="search" />
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 4 }}>
          <CircularProgress size={40} />
          <Typography sx={{ mt: 2 }}>{t('downloader.initializingSearch')}</Typography>
        </Box>
      </Container>
    );
  }

  if (error || status?.error || status?.status === 'failed') {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="search" />
        <Alert severity="error">{error || status?.error || t('downloader.errorOccurred')}</Alert>
      </Container>
    );
  }

  const completed = !!status?.search_completed;
  const groups = results?.status === 'success' ? results.results : [];
  const hasResults = groups.length > 0;

  if (!completed && !hasResults) {
    // Display search progress
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="search" />
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 4, maxWidth: 'md', mx: 'auto' }}>
          <Typography variant="h5" gutterBottom>
            {t('downloader.searchingForNovels')}
          </Typography>

          <Box sx={{ width: '100%', mb: 3 }}>
            <Typography variant="body2" gutterBottom>
              {status?.status_display || t('downloader.initializing')}
            </Typography>

            <LinearProgress
              variant="determinate"
              value={status?.progress_percentage || 0}
              sx={{ height: 10, borderRadius: 1 }}
            />

            {status?.progress !== undefined && status?.total_items !== undefined && (
              <Typography
                variant="body2"
                sx={{
                  textAlign: "right",
                  mt: 1
                }}>
                {t('downloader.itemsProgress', { progress: status.progress, total: status.total_items })}
              </Typography>
            )}
          </Box>

          <Typography variant="body2" sx={{
            color: "text.secondary"
          }}>
            {t('downloader.pleaseWait')}
          </Typography>

          <Button
            variant="outlined"
            sx={{ mt: 3 }}
            onClick={handleCancel}
          >
            {t('downloader.cancelSearch')}
          </Button>
        </Box>
      </Container>
    );
  }

  return (
    <Container maxWidth="md">
      <DownloadStepper activeStep={completed ? 'select' : 'search'} />
      <Box>
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={1}
          justifyContent="space-between"
          alignItems={{ xs: 'flex-start', sm: 'center' }}
          sx={{ mb: 2 }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Typography variant="h5" component="h1" sx={{ fontWeight: 700 }}>
              {t('downloader.searchResults')}
            </Typography>
            <Chip size="small" label={countSources(groups)} />
            {status?.query && (
              <Typography variant="body1" sx={{ color: 'text.secondary', wordBreak: 'break-word' }}>
                « {status.query} »
              </Typography>
            )}
          </Box>
          {completed && (
            <Button
              variant="outlined"
              size="small"
              component={Link}
              to="/download/"
            >
              {t('downloader.newSearch')}
            </Button>
          )}
        </Stack>

        {!completed && (
          <Paper variant="outlined" sx={{ p: 2, mb: 3 }}>
            <LinearProgress
              variant="determinate"
              value={status?.progress_percentage || 0}
              sx={{ height: 8, borderRadius: 1 }}
              aria-label={t('downloader.searching')}
            />
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 1.5 }}>
              <Button variant="outlined" size="small" onClick={handleCancel}>
                {t('downloader.cancelSearch')}
              </Button>
              {status?.progress !== undefined && status?.total_items !== undefined && (
                <Typography variant="body2" sx={{ color: 'text.secondary' }}>
                  {t('downloader.itemsProgress', { progress: status.progress, total: status.total_items })}
                </Typography>
              )}
            </Stack>
          </Paper>
        )}

        {hasResults ? (
          groups.map((source, sourceIndex) => (
            <Box key={source.title} sx={{ mb: 4 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
                <Typography variant="h6" component="h2" sx={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                  {source.title}
                </Typography>
                <Chip size="small" variant="outlined" sx={{ flexShrink: 0 }} label={source.sources.length} />
              </Box>
              <Divider sx={{ mb: 2 }} />

              <Grid container spacing={2}>
                {source.sources.map((novel, novelIndex) => (
                  <Grid key={`${novel.url}-${novelIndex}`} size={{ xs: 12, sm: 6, md: 4 }}>
                    <Card sx={{ height: '100%' }}>
                      <CardActionArea
                        component={Link}
                        to={`/download/${jobId}/${sourceIndex}/${novelIndex}`}
                        state={{ novelUrl: novel.url, title: source.title, added: novel.added }}
                        sx={{ display: 'flex', alignItems: 'stretch', justifyContent: 'flex-start', height: '100%' }}
                      >
                        <Box
                          component="img"
                          src={novel.cover || defaultCover}
                          alt=""
                          loading="lazy"
                          referrerPolicy="no-referrer"
                          onError={(e: SyntheticEvent<HTMLImageElement>) => {
                            e.currentTarget.onerror = null;
                            if (e.currentTarget.getAttribute('src') !== defaultCover) {
                              e.currentTarget.src = defaultCover;
                            }
                          }}
                          sx={{ width: 64, height: 96, objectFit: 'cover', flexShrink: 0 }}
                        />
                        <Box sx={{ p: 1.5, minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, minWidth: 0 }}>
                            <Typography variant="subtitle2" component="p" noWrap sx={{ minWidth: 0 }}>
                              {getHostname(novel.url)}
                            </Typography>
                            {novel.added && (
                              <Tooltip title={t('downloader.alreadyAdded')}>
                                <CheckCircleIcon
                                  fontSize="small"
                                  color="success"
                                  aria-label={t('downloader.alreadyAdded')}
                                  sx={{ flexShrink: 0 }}
                                />
                              </Tooltip>
                            )}
                          </Box>
                          <Typography
                            variant="caption"
                            sx={{
                              color: 'text.secondary',
                              display: '-webkit-box',
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: 'vertical',
                              overflow: 'hidden',
                              wordBreak: 'break-all'
                            }}
                          >
                            {novel.url}
                          </Typography>
                        </Box>
                      </CardActionArea>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>
          ))
        ) : (
          <Alert severity="info">{t('downloader.noResults')}</Alert>
        )}
      </Box>
    </Container>
  );
};

export default SearchResults;
