import { useState, useEffect, useCallback } from 'react';
import { Button, Box, LinearProgress, Typography, Alert, Tooltip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { downloadService, type ApiError } from '../../../services/api';
import { DownloadStatus } from '@models/downloader_types';
import UpdateIcon from '@mui/icons-material/Update';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutlined';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutlined';

interface NovelUpdateButtonProps {
  sourceUrl: string;
  novelTitle: string; // For context, potentially in messages
  disabled?: boolean; // No crawler for this source
}

const NovelUpdateButton: React.FC<NovelUpdateButtonProps> = ({ sourceUrl, novelTitle, disabled = false }) => {
  const { t } = useTranslation();
  const [updateJobId, setUpdateJobId] = useState<string | null>(null);
  const [downloadStatus, setDownloadStatus] = useState<DownloadStatus | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false); // For the initial startDownload call
  const [isPolling, setIsPolling] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [updateComplete, setUpdateComplete] = useState<boolean>(false);

  const resetState = () => {
    setUpdateJobId(null);
    setDownloadStatus(null);
    setIsLoading(false);
    setIsPolling(false);
    setError(null);
    setUpdateComplete(false);
  };

  const handleUpdateClick = async () => {
    resetState();
    setIsLoading(true);
    setError(null);
    try {
      const response = await downloadService.startDirectDownload(sourceUrl);
      if (response.job_id) {
        setUpdateJobId(response.job_id);
        setIsPolling(true);
      } else {
        setError(response.message || t('updateButton.startFailed'));
      }
    } catch (err) {
      const apiErr = err as ApiError;
      console.error('Error starting direct download:', err);
      setError(apiErr.response?.data?.message || apiErr.message || t('updateButton.unknownError'));
    } finally {
      setIsLoading(false);
    }
  };

  const pollDownloadStatus = useCallback(async () => {
    if (!updateJobId) return;

    try {
      const statusData = await downloadService.getDownloadStatus(updateJobId);
      setDownloadStatus(statusData);

      if (statusData.download_completed) {
        setIsPolling(false);
        setUpdateComplete(true);
        // Optionally, could reset after a delay or keep "Updated" state
      } else if (statusData.job_status === 'FAILED' || statusData.job_status === 'CANCELLED') {
        setIsPolling(false);
        setError(statusData.status_display || t('updateButton.updateFailed'));
      }
    } catch (err) {
      const apiErr = err as ApiError;
      console.error('Error fetching download status:', err);
      setIsPolling(false);
      setError(apiErr.response?.data?.message || apiErr.message || t('updateButton.fetchFailed'));
    }
  }, [updateJobId, t]);

  useEffect(() => {
    let intervalId: ReturnType<typeof setInterval> | null = null;
    if (isPolling && updateJobId) {
      pollDownloadStatus(); // Initial call
      intervalId = setInterval(pollDownloadStatus, 3000); // Poll every 3 seconds
    }
    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [isPolling, updateJobId, pollDownloadStatus]);

  const isUpdating = isLoading || isPolling;

  if (disabled) {
    return (
      <Box sx={{ width: '100%', mt: 2 }}>
        <Tooltip title={t('updateButton.disabledNoCrawler')}>
          <span style={{ display: 'inline-block', width: '100%' }}>
            <Button
              variant="contained"
              color="info"
              startIcon={<UpdateIcon />}
              disabled
              fullWidth
            >
              {t('updateButton.updateFrom', { title: novelTitle })}
            </Button>
          </span>
        </Tooltip>
      </Box>
    );
  }

  return (
    <Box sx={{ width: '100%', mt: 2 }}>
      {!isUpdating && !updateComplete && !error && (
        <Button
          variant="contained"
          color="info"
          startIcon={<UpdateIcon />}
          onClick={handleUpdateClick}
          disabled={isLoading}
          fullWidth
        >
          {isLoading ? t('updateButton.starting') : t('updateButton.updateFrom', { title: novelTitle })}
        </Button>
      )}

      {isLoading && !updateJobId && (
        <Box sx={{ display: 'flex', alignItems: 'center', flexDirection: 'column' }}>
          <LinearProgress sx={{ width: '100%', mb: 1 }} />
          <Typography variant="caption">{t('updateButton.initiating')}</Typography>
        </Box>
      )}

      {isPolling && downloadStatus && (
        <Box sx={{ width: '100%' }}>
          <Typography variant="subtitle2" gutterBottom>
            {t('updateButton.updatingStatus', { status: downloadStatus.status_display })}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={downloadStatus.progress_percentage || 0}
            sx={{ height: 10, borderRadius: 5, mb: 1 }}
          />
          <Typography variant="caption">
            {downloadStatus.progress_percentage !== undefined ? `${downloadStatus.progress_percentage}%` : t('updateButton.processing')}
            {downloadStatus.total_chapters > 0 && ` ${t('updateButton.progressOf', { progress: downloadStatus.progress, total: downloadStatus.total_chapters, unit: downloadStatus.progress_unit || 'chapters' })}`}
          </Typography>
        </Box>
      )}

      {updateComplete && downloadStatus && (
        <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
          {t('updateButton.complete', { title: novelTitle })}
        </Alert>
      )}
      
      {error && (
         <Alert severity="error" icon={<ErrorOutlineIcon fontSize="inherit" />}>
          {error}
        </Alert>
      )}

      {(updateComplete || error) && !isUpdating && (
         <Button
          variant="outlined"
          color="primary"
          startIcon={<UpdateIcon />}
          onClick={handleUpdateClick}
          sx={{ mt: 1 }}
          fullWidth
        >
          {t('updateButton.tryAgain')}
        </Button>
      )}
    </Box>
  );
};

export default NovelUpdateButton;
