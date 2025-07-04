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
import { downloadService } from '@services/api';
import { DownloadStatus as DownloadStatusType, DownloadResults } from '@models/downloader_types';
import DownloadStepper from './DownloadStepper';

const POLLING_INTERVAL = 2000; // 2 seconds

const DownloadStatus = () => {
  const { jobId } = useParams<{ jobId: string }>();
  
  const [status, setStatus] = useState<DownloadStatusType | null>(null);
  const [results, setResults] = useState<DownloadResults | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStatus = async () => {
    if (!jobId) return;
    
    try {
      const statusResponse = await downloadService.getDownloadStatus(jobId);
      
      if (statusResponse.status === 'success') {
        setStatus(statusResponse);
        
        if (statusResponse.download_completed) {
          const resultsResponse = await downloadService.getDownloadResults(jobId);
          setResults(resultsResponse);
        }
      } else {
        setError(statusResponse.message || 'Failed to fetch download status');
      }
    } catch (err) {
      console.error('Error fetching download status:', err);
      setError('An error occurred while checking download status.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    
    // Set up polling for status updates
    const intervalId = setInterval(() => {
      if (status?.download_completed) {
        clearInterval(intervalId);
        return;
      }
      fetchStatus();
    }, POLLING_INTERVAL);
    
    return () => clearInterval(intervalId);
  }, [jobId, status?.download_completed]);

  if (loading && !status) {
    return (
      <Container maxWidth="md">
        <DownloadStepper activeStep="download" />
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', p: 4 }}>
          <LinearProgress sx={{ width: '100%', maxWidth: 400 }} />
          <Typography sx={{ mt: 2 }}>Loading download status...</Typography>
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
            Return Home
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
            Download failed. Please try again.
          </Alert>
          <Button variant="contained" component={Link} to="/download/">
            Return Home
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
            Download Complete
          </Typography>
          
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" fontWeight="bold">
              {results.selected_novel.title}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {results.selected_novel.chapters} chapters in {results.selected_novel.volumes} volumes
            </Typography>
          </Box>
          
          <Divider sx={{ mb: 2 }} /> 
          <Box sx={{ mt: 3 }}>
            <Button 
              variant="contained" 
              component={Link}
              to="/download/"
            >
              New Search
            </Button>
          </Box>
          <Box sx={{ mt: 3 }}>
            <Button 
              variant="contained" 
              component={Link}
              to={`/novels/${results.output_slug}`}
            >
              View Downloaded Novel
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
          Download in Progress
        </Typography>
        
        {status?.selected_novel && (
          <Box sx={{ mb: 3 }}>
            <Typography variant="subtitle1" fontWeight="bold">
              {status.selected_novel.title}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {status.selected_novel.chapters} chapters
            </Typography>
          </Box>
        )}
        
        <Box sx={{ mb: 3 }}>
          <Typography variant="body2" gutterBottom>
            {status?.status_display || 'Initializing...'}
          </Typography>
          <LinearProgress 
            variant="determinate" 
            value={status?.progress_percentage || 0} 
            sx={{ height: 10, borderRadius: 1 }}
          />
          <Typography variant="body2" sx={{ mt: 1 }} textAlign="right">
            {status?.progress || 0} / {status?.total_chapters || 0} chapters
          </Typography>
        </Box>
        
        <Typography variant="body2" color="text.secondary">
          You can close the page if you do not wish to monitor the progress, the download will continue in the background.
        </Typography>
      </Paper>
    </Container>
  );
};

export default DownloadStatus;
