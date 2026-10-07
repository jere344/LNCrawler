import { useState } from 'react';
import { TextField, Button, Box, Typography, Alert } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { searchService, downloadService } from '@services/api';
import { useNavigate } from 'react-router-dom';

const SearchForm = () => {
  const { t } = useTranslation();
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
      setError(t('downloader.queryTooShort'));
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
          setError(response.message || t('downloader.directDownloadFailed'));
        }
      } else {
        // Regular search flow
        const response = await searchService.startSearch(query);
        if (response.status === 'success') {
          navigate(`/download/search/${response.job_id}`);
        } else {
          setError(response.message || t('downloader.searchFailed'));
        }
      }
    } catch (err) {
      console.error('Search error:', err);
      setError(t('downloader.genericError'));
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
        gap: 1.5,
        maxWidth: 'sm',
        mx: 'auto',
      }}
    >
      <Typography variant="h6" component="h2" gutterBottom>
        {t('downloader.searchForNovel')}
      </Typography>
      
      {error && <Alert severity="error">{error}</Alert>}
      
      <TextField
        label={t('downloader.novelTitleOrUrl')}
        variant="outlined"
        fullWidth
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        disabled={loading}
        placeholder={t('downloader.titleOrUrlPlaceholder')}
      />
      
      <Button 
        type="submit" 
        variant="contained" 
        color="primary" 
        disabled={loading || query.length < 3}
      >
        {loading ? t('downloader.searching') : t('downloader.search')}
      </Button>
    </Box>
  );
};

export default SearchForm;
