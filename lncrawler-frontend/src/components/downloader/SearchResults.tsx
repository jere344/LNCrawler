import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
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
import { searchService } from '@services/api';
import { SearchStatus, SearchResults as SearchResultsType } from '@models/downloader_types';
import DownloadStepper from './DownloadStepper';

const POLLING_INTERVAL = 2000; // 2 seconds

const SearchResults = () => {
  const { t } = useTranslation();
  const { jobId } = useParams<{ jobId: string }>();
  const [status, setStatus] = useState<SearchStatus | null>(null);
  const [results, setResults] = useState<SearchResultsType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Function to check search status
  const checkSearchStatus = async () => {
    if (!jobId) return;
    
    try {
      const statusResponse = await searchService.getSearchStatus(jobId);
      setStatus(statusResponse);
      
      if (statusResponse.search_completed && statusResponse.has_results) {
        // If search is complete, get the results
        const resultsResponse = await searchService.getSearchResults(jobId);
        setResults(resultsResponse);
      }
      
      // Set loading to false after the first successful status check.
      // Subsequent checks are part of polling, where UI shows progress.
      if (loading) {
        setLoading(false);
      }
    } catch (err) {
      console.error('Error fetching search status:', err);
      setError(t('downloader.fetchSearchFailed'));
      if (loading) { // Ensure loading is false on error during initial phase
        setLoading(false);
      }
    }
  };

  // Effect for initial fetch when jobId changes
  useEffect(() => {
    if (jobId) {
      setLoading(true); // Reset loading for a new search
      setStatus(null);  // Reset status
      setResults(null); // Reset results
      setError(null);   // Reset error
      checkSearchStatus();
    }
    // Intentionally not depending on checkSearchStatus to avoid re-runs from its definition changing
    // eslint-disable-next-line react-hooks/exhaustive-deps 
  }, [jobId]);

  // Effect for polling based on status
  useEffect(() => {
    if (!jobId) return; // Don't do anything if jobId is not available

    // Only start polling if status is available and search is not completed.
    if (status && !status.search_completed) {
      const intervalId = setInterval(() => {
        checkSearchStatus();
      }, POLLING_INTERVAL);
      
      // Cleanup function to clear interval when component unmounts
      // or when dependencies change causing the effect to re-run.
      return () => clearInterval(intervalId);
    }
    // If status is null, or search is completed, any existing interval
    // (from a previous state where search_completed was false) will be cleared
    // by the cleanup of *that* effect run, and no new interval will start.

    // Intentionally not depending on checkSearchStatus
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, status?.search_completed]); // Re-run if jobId or search_completed status changes.
                                         // status itself is not needed as a dep if only search_completed matters for polling logic.

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

  if (error || (status && status.error)) {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="search" />
        <Alert severity="error">{error || status?.error || t('downloader.errorOccurred')}</Alert>
      </Container>
    );
  }

  if (!status?.search_completed) {
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
            component={Link}
            to="/download/"
          >
            {t('downloader.cancelSearch')}
          </Button>
        </Box>
      </Container>
    );
  }

  if (results && results.status === 'success') {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="select" />
        <Box sx={{ p: 1 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="h6">
              {t('downloader.searchResults')}
            </Typography>
            <Button
              variant="outlined"
              size="small"
              component={Link}
              to="/download/"
            >
              {t('downloader.newSearch')}
            </Button>
          </Box>

          {results.results && results.results.length > 0 ? (
            results.results.map((source, sourceIndex) => (
              <Card key={`source-${sourceIndex}`} sx={{ mb: 0.5 }}>
                <CardContent sx={{ py: 0.5, '&:last-child': { pb: 0.5 } }}>
                  <Typography variant="subtitle2">{source.title}</Typography>
                  
                  <List dense disablePadding>
                    {source.sources.map((novel, novelIndex) => (
                      <Box key={`novel-${novelIndex}`}>
                        {novelIndex > 0 && <Divider />}
                        <ListItemButton 
                          component={Link} 
                          to={`/download/${jobId}/${sourceIndex}/${novelIndex}`}
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
  }

  return (
    <Container maxWidth="md">
      <DownloadStepper activeStep="search" />
      <Alert severity="warning">
        {t('downloader.unexpectedResponse')}
      </Alert>
    </Container>
  );
};

export default SearchResults;
