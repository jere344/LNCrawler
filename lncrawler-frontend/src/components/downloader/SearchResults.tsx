import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Box,
  Typography,
  CircularProgress,
  Alert,
  Card,
  CardContent,
  Button,
  List,
  Divider,
  ListItemButton,
  ListItemText,
  LinearProgress,
  Container
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { searchService, jobService } from '@services/api';
import { SearchStatus, SearchResult, SearchResults as SearchResultsType } from '@models/downloader_types';
import DownloadStepper from './DownloadStepper';

const POLLING_INTERVAL = 1000; // 1 second
const MAX_CONSECUTIVE_FAILURES = 3;

const countSources = (groups: SearchResult[]) =>
  groups.reduce((total, group) => total + group.sources.length, 0);

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
      <Box sx={{ p: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="h6">
            {t('downloader.searchResults')}
          </Typography>
          {completed ? (
            <Button
              variant="outlined"
              size="small"
              component={Link}
              to="/download/"
            >
              {t('downloader.newSearch')}
            </Button>
          ) : (
            <Button variant="outlined" size="small" onClick={handleCancel}>
              {t('downloader.newSearch')}
            </Button>
          )}
        </Box>

        {!completed && (
          <Box sx={{ mb: 2 }}>
            <LinearProgress
              variant="determinate"
              value={status?.progress_percentage || 0}
              sx={{ height: 6, borderRadius: 1 }}
              aria-label={t('downloader.searching')}
            />
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 1 }}>
              <Button variant="outlined" size="small" onClick={handleCancel}>
                {t('downloader.cancelSearch')}
              </Button>
              {status?.progress !== undefined && status?.total_items !== undefined && (
                <Typography variant="body2">
                  {t('downloader.itemsProgress', { progress: status.progress, total: status.total_items })}
                </Typography>
              )}
            </Box>
          </Box>
        )}

        {hasResults ? (
          groups.map((source, sourceIndex) => (
            <Card key={source.title} sx={{ mb: 0.5 }}>
              <CardContent sx={{ py: 0.5, '&:last-child': { pb: 0.5 } }}>
                <Typography variant="subtitle2">{source.title}</Typography>

                <List dense disablePadding>
                  {source.sources.map((novel, novelIndex) => (
                    <Box key={`${novel.url}-${novelIndex}`}>
                      {novelIndex > 0 && <Divider />}
                      <ListItemButton
                        component={Link}
                        to={`/download/${jobId}/${sourceIndex}/${novelIndex}`}
                        state={{ novelUrl: novel.url, title: source.title }}
                      >
                        <ListItemText
                          primary={source.title}
                          secondary={novel.url}
                        />
                      </ListItemButton>
                    </Box>
                  ))}
                </List>
              </CardContent>
            </Card>
          ))
        ) : (
          <Alert severity="info">{t('downloader.noResults')}</Alert>
        )}
      </Box>
    </Container>
  );
};

export default SearchResults;
