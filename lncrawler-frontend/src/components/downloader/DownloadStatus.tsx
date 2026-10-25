import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Box,
  Typography,
  Paper,
  LinearProgress,
  Button,
  Alert,
  Divider,
  Container
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { downloadService } from '@services/api';
import { DownloadStatus as DownloadStatusType, DownloadResults } from '@models/downloader_types';
import { formatProgress } from '@utils/progressUnit';
import DownloadStepper from './DownloadStepper';

const POLLING_INTERVAL = 2000; // 2 seconds
const MAX_CONSECUTIVE_FAILURES = 3;

const DownloadStatus = () => {
  const { t } = useTranslation();
  const { jobId } = useParams<{ jobId: string }>();
  
  const [status, setStatus] = useState<DownloadStatusType | null>(null);
  const [results, setResults] = useState<DownloadResults | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Chained timeouts: the next request starts only after the previous one settled
  useEffect(() => {
    if (!jobId) return;

    let active = true;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;

    const poll = async () => {
      try {
        const statusResponse = await downloadService.getDownloadStatus(jobId);
        if (!active) return;
        failures = 0;

        if (statusResponse.status !== 'success') {
          setError(statusResponse.message || t('downloader.fetchStatusFailed'));
          return;
        }

        if (statusResponse.download_completed) {
          const resultsResponse = await downloadService.getDownloadResults(jobId);
          if (!active) return;
          if (resultsResponse.status !== 'success') {
            setError(resultsResponse.message || t('downloader.fetchStatusFailed'));
            return;
          }
          setResults(resultsResponse);
        }

        setStatus(statusResponse);

        const finished = statusResponse.download_completed || statusResponse.job_status === 'failed';
        if (!finished) {
          timeoutId = setTimeout(poll, POLLING_INTERVAL);
        }
      } catch (err) {
        if (!active) return;
        console.error('Error fetching download status:', err);
        failures += 1;
        if (failures >= MAX_CONSECUTIVE_FAILURES) {
          setError(t('downloader.statusError'));
          return;
        }
        timeoutId = setTimeout(poll, POLLING_INTERVAL);
      } finally {
        setLoading(false);
      }
    };

    setLoading(true); // Reset loading for a new download
    setStatus(null);  // Reset status
    setResults(null); // Reset results
    setError(null);   // Reset error
    poll();

    return () => {
      active = false;
      clearTimeout(timeoutId);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- polling keyed to jobId, not translator identity
  }, [jobId]);

  if (loading && !status) {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="download" />
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 4 }}>
          <LinearProgress sx={{ width: '100%', maxWidth: 400 }} />
          <Typography sx={{ mt: 2 }}>{t('downloader.loadingStatus')}</Typography>
        </Box>
      </Container>
    );
  }

  if (error) {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="download" />
        <Box sx={{ p: 2, maxWidth: 'md', mx: 'auto' }}>
          <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>
          <Button variant="contained" component={Link} to="/download/">
            {t('downloader.returnHome')}
          </Button>
        </Box>
      </Container>
    );
  }

  if (status?.job_status === 'failed') {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="download" />
        <Box sx={{ p: 2, maxWidth: 'md', mx: 'auto' }}>
          <Alert severity="error" sx={{ mb: 2 }}>
            {t('downloader.downloadFailed')}
          </Alert>
          <Button variant="contained" component={Link} to="/download/">
            {t('downloader.returnHome')}
          </Button>
        </Box>
      </Container>
    );
  }

  if (status?.download_completed && results) {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="complete" />
        <Paper sx={{ p: 3, maxWidth: 'md', mx: 'auto', mt: 2 }}>
          <Typography variant="h5" gutterBottom color="primary">
            {t('downloader.downloadComplete')}
          </Typography>
          
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" sx={{
              fontWeight: "bold"
            }}>
              {results.selected_novel.title}
            </Typography>
            <Typography variant="body2" sx={{
              color: "text.secondary"
            }}>
              {t('units.chapters', { count: results.selected_novel.chapters })}
            </Typography>
          </Box>
          
          <Divider sx={{ mb: 2 }} /> 
          <Box sx={{ mt: 3 }}>
            <Button 
              variant="contained" 
              component={Link}
              to="/download/"
            >
              {t('downloader.newSearch')}
            </Button>
          </Box>
          <Box sx={{ mt: 3 }}>
            <Button 
              variant="contained" 
              component={Link}
              to={`/novels/${results.output_slug}`}
            >
              {t('downloader.viewDownloaded')}
            </Button>
          </Box>
        </Paper>
      </Container>
    );
  }

  // Display download progress
  return (
    <Container maxWidth="md">
      <DownloadStepper activeStep="download" />
      <Paper sx={{ p: 3, maxWidth: 'md', mx: 'auto', mt: 2 }}>
        <Typography variant="h5" gutterBottom>
          {t('downloader.downloadInProgress')}
        </Typography>
        
        {status?.selected_novel && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" sx={{
              fontWeight: "bold"
            }}>
              {status.selected_novel.title}
            </Typography>
            <Typography variant="body2" sx={{
              color: "text.secondary"
            }}>
              {t('units.chapters', { count: status.selected_novel.chapters })}
            </Typography>
          </Box>
        )}

        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" gutterBottom>
            {status?.status_display || t('downloader.initializing')}
          </Typography>
          {status && (
            <Typography variant="body2" sx={{ fontWeight: 'bold' }} gutterBottom>
              {status.progress_unit === 'images'
                ? t('downloader.phaseImages')
                : status.progress_unit === 'chapters'
                  ? t('downloader.phaseChapters')
                  : t('downloader.phaseToc')}
            </Typography>
          )}
          <LinearProgress 
            variant="determinate" 
            value={status?.progress_percentage || 0} 
            sx={{ height: 10, borderRadius: 1 }}
          />
          <Typography
            variant="body2"
            sx={{
              textAlign: "right",
              mt: 1
            }}>
            {formatProgress(t, status?.progress || 0, status?.total_items ?? status?.total_chapters ?? 0, status?.progress_unit)}
          </Typography>
        </Box>
        
        <Typography variant="body2" sx={{
          color: "text.secondary"
        }}>
          {t('downloader.backgroundNote')}
        </Typography>
      </Paper>
    </Container>
  );
};

export default DownloadStatus;
