import { useState } from 'react';
import { TextField, Button, Box, Typography, Alert } from '@mui/material';
import { searchService, downloadService } from '@services/api';
import { useNavigate } from 'react-router-dom';

const SearchForm = () => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Helper function to check if input is a URL
  const isUrl = (text: string): boolean => {
    return text.trim().toLowerCase().startsWith('http');
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!query || query.trim().length < 3) {
      setError('Search query must be at least 3 characters');
      return;
    }
    
    setLoading(true);
    setError(null);
    
    try {
      // If the query is a URL, start direct download instead of search
      if (isUrl(query)) {
        const response = await downloadService.startDirectDownload(query);
        if (response.status === 'success') {
          navigate(`/download/status/${response.job_id}`);
        } else {
          setError(response.message || 'Failed to start direct download');
        }
      } else {
        // Regular search flow
        const response = await searchService.startSearch(query);
        if (response.status === 'success') {
          navigate(`/download/search/${response.job_id}`);
        } else {
          setError(response.message || 'Failed to start search');
        }
      }
    } catch (err) {
      console.error('Search error:', err);
      setError('An error occurred while processing your request. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box
      component="form"
      onSubmit={handleSearch}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
        maxWidth: 'sm',
        mx: 'auto',
        p: 2,
      }}
    >
      <Typography variant="h5" component="h2" gutterBottom>
        Search for a Novel
      </Typography>
      
      {error && <Alert severity="error">{error}</Alert>}
      
      <TextField
        label="Novel Title or URL"
        variant="outlined"
        fullWidth
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
        placeholder="Enter novel title or direct URL"
      />
      
      <Button 
        type="submit" 
        variant="contained" 
        color="primary" 
        disabled={loading || query.length < 3}
      >
        {loading ? 'Searching...' : 'Search'}
      </Button>
    </Box>
  );
};

export default SearchForm;
