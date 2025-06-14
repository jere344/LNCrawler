import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Button,
  Paper,
  CircularProgress,
  Alert,
  Container
} from '@mui/material';
import { downloadService } from '@services/api';
import { DownloadParams } from '@models/downloader_types';
import DownloadStepper from './DownloadStepper';

const DownloadForm = () => {
  const { jobId, novelIndex = '0', sourceIndex = '0' } = useParams<{
    jobId: string;
    novelIndex: string;
    sourceIndex: string;
  }>();
  const navigate = useNavigate();
  
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!jobId) return;
    
    setLoading(true);
    setError(null);
    
    try {
      const downloadParams: DownloadParams = {
        novel_index: parseInt(novelIndex, 10),
        source_index: parseInt(sourceIndex, 10)
      };
      
      const response = await downloadService.startDownload(jobId, downloadParams);
      
      if (response.status === 'success') {
        navigate(`/download/status/${jobId}`);
      } else {
        setError(response.message || 'Failed to start download');
      }
    } catch (err) {
      console.error('Download error:', err);
      setError('An error occurred while starting download. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container maxWidth="md">
      <DownloadStepper activeStep="download" />
      <Paper sx={{ p: 3, maxWidth: 'md', mx: 'auto', mt: 2 }}>
        <Typography variant="h5" gutterBottom>
          Download Options
        </Typography>
        
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        
        <Box component="form" onSubmit={handleSubmit}>
          <Typography variant="body1" sx={{ mb: 3 }}>
            The novel will be downloaded and add to our library.
          </Typography>
          
          <Box sx={{ display: 'flex', gap: 2 }}>
            <Button
              variant="outlined"
              onClick={() => navigate(-1)}
              disabled={loading}
            >
              Back
            </Button>
            
            <Button
              type="submit"
              variant="contained"
              disabled={loading}
            >
              {loading ? (
                <>
                  <CircularProgress size={24} sx={{ mr: 1 }} />
                  Starting Download...
                </>
              ) : (
                'Start Download'
              )}
            </Button>
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default DownloadForm;
