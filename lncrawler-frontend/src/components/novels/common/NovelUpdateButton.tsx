import { useState, useEffect, useCallback } from 'react';
import { Button, Box, LinearProgress, Typography, Alert } from '@mui/material';
import { downloadService } from '../../../services/api';
import { DownloadStatus } from '@models/downloader_types';
import UpdateIcon from '@mui/icons-material/Update';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

interface NovelUpdateButtonProps {
  sourceUrl: string;
  novelTitle: string; // For context, potentially in messages
}

const NovelUpdateButton: React.FC<NovelUpdateButtonProps> = ({ sourceUrl, novelTitle }) => {
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
        setError(response.message || 'Failed to start update job.');
      }
    } catch (err: any) {
      console.error('Error starting direct download:', err);
      setError(err.response?.data?.message || err.message || 'An unknown error occurred while starting the update.');
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
        setError(statusData.status_display || 'Update failed or was cancelled.');
      }
    } catch (err: any) {
      console.error('Error fetching download status:', err);
      setIsPolling(false);
      setError(err.response?.data?.message || err.message || 'Failed to fetch update status.');
    }
  }, [updateJobId]);

  useEffect(() => {
    let intervalId: NodeJS.Timeout | null = null;
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
          {isLoading ? 'Starting Update...' : `Update ${novelTitle} from Source`}
        </Button>
      )}

      {isLoading && !updateJobId && (
        <Box sx={{ display: 'flex', alignItems: 'center', flexDirection: 'column' }}>
          <LinearProgress sx={{ width: '100%', mb: 1 }} />
          <Typography variant="caption">Initiating update...</Typography>
        </Box>
      )}

      {isPolling && downloadStatus && (
        <Box sx={{ width: '100%' }}>
          <Typography variant="subtitle2" gutterBottom>
            Updating: {downloadStatus.status_display}
          </Typography>
          <LinearProgress
            variant="determinate"
            value={downloadStatus.progress_percentage || 0}
            sx={{ height: 10, borderRadius: 5, mb: 1 }}
          />
          <Typography variant="caption">
            {downloadStatus.progress_percentage !== undefined ? `${downloadStatus.progress_percentage}%` : 'Processing...'}
            {downloadStatus.total_chapters > 0 && ` (${downloadStatus.progress} / ${downloadStatus.total_chapters} chapters)`}
          </Typography>
        </Box>
      )}

      {updateComplete && downloadStatus && (
        <Alert severity="success" icon={<CheckCircleOutlineIcon fontSize="inherit" />}>
          Update complete for {novelTitle}! {downloadStatus.output_files ? `${downloadStatus.output_files.length} file(s) processed.` : ''}
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
          Try Update Again
        </Button>
      )}
    </Box>
  );
};

export default NovelUpdateButton;
