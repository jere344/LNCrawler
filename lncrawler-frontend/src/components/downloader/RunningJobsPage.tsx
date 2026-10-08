import { useCallback, useEffect, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Container,
  LinearProgress,
  Paper,
  Stack,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { jobService } from '@services/api';
import { Job } from '@models/downloader_types';
import { formatDateTime } from '@utils/Misc';

const POLLING_INTERVAL = 3000; // 3 seconds

const RunningJobsPage = () => {
  const { t, i18n } = useTranslation();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchJobs = useCallback(async () => {
    try {
      const response = await jobService.listJobs(true);
      if (response.status === 'success') {
        setJobs(response.jobs);
        setError(null);
      } else {
        setError(response.message || t('downloader.jobsLoadFailed'));
      }
    } catch (err) {
      console.error('Error fetching running jobs:', err);
      setError(t('downloader.jobsLoadFailed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    fetchJobs();
    const intervalId = setInterval(fetchJobs, POLLING_INTERVAL);
    return () => clearInterval(intervalId);
  }, [fetchJobs]);

  const handleCancel = async (jobId: string) => {
    try {
      await jobService.cancelJob(jobId);
      await fetchJobs();
    } catch (err) {
      console.error('Error cancelling job:', err);
      setError(t('downloader.jobCancelFailed'));
    }
  };

  const jobTitle = (job: Job) =>
    job.selected_novel?.title || job.query || t('downloader.jobUntitled');
  const jobLink = (job: Job) =>
    job.job_type === 'download' ? `/download/status/${job.id}` : `/download/search/${job.id}`;

  return (
    <Container maxWidth="md">
      <Box sx={{ my: 2 }}>
        <Typography variant="h5" component="h1" gutterBottom>
          {t('downloader.jobsHeading')}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {t('downloader.jobsSubtitle')}
        </Typography>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading && jobs.length === 0 ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : jobs.length === 0 ? (
        <Paper sx={{ p: 3, textAlign: 'center' }}>
          <Typography sx={{ mb: 2 }}>{t('downloader.jobsEmpty')}</Typography>
          <Button variant="contained" component={RouterLink} to="/download">
            {t('downloader.jobsBackToAdd')}
          </Button>
        </Paper>
      ) : (
        <Stack spacing={2}>
          {jobs.map((job) => (
            <Paper key={job.id} sx={{ p: 2 }}>
              <Stack
                direction="row"
                sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1, mb: 1 }}
              >
                <Typography variant="subtitle1" sx={{ fontWeight: 'bold', flexGrow: 1 }}>
                  {jobTitle(job)}
                </Typography>
                <Chip
                  size="small"
                  label={
                    job.job_type === 'download'
                      ? t('downloader.jobDownload')
                      : t('downloader.jobSearch')
                  }
                  variant="outlined"
                />
                <Chip size="small" label={job.status_display} color="primary" />
              </Stack>

              {job.total_items > 0 && (
                <Box sx={{ mb: 1 }}>
                  <LinearProgress
                    variant="determinate"
                    value={job.progress_percentage}
                    sx={{ height: 8, borderRadius: 1 }}
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'right', mt: 0.5 }}>
                    {job.progress} / {job.total_items} {job.progress_unit}
                  </Typography>
                </Box>
              )}

              <Stack
                direction="row"
                sx={{ alignItems: 'center', flexWrap: 'wrap', gap: 1 }}
              >
                <Typography variant="caption" color="text.secondary" sx={{ flexGrow: 1 }}>
                  {t('downloader.jobCreated')}: {formatDateTime(job.created_at, i18n.language)}
                </Typography>
                <Button size="small" component={RouterLink} to={jobLink(job)}>
                  {t('downloader.jobView')}
                </Button>
                <Button size="small" color="error" onClick={() => handleCancel(job.id)}>
                  {t('downloader.jobCancel')}
                </Button>
              </Stack>
            </Paper>
          ))}
        </Stack>
      )}
    </Container>
  );
};

export default RunningJobsPage;
