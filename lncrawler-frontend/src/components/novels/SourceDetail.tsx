import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Container,
  Typography,
  Grid,
  Box,
  Paper,
  Button,
  CircularProgress,
  Chip,
  Divider,
  Card,
  CardMedia,
  List,
  ListItem,
  ListItemText,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import LanguageIcon from '@mui/icons-material/Language';
import { utils } from '@utils/textUtils';

interface SourceDetail {
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  source_slug: string;
  cover_url: string | null;
  authors: string[];
  genres: string[];
  tags: string[];
  language: string;
  status: string;
  synopsis: string;
  chapters_count: number;
  volumes_count: number;
  last_updated: string;
  novel_id: string;
  novel_slug: string;
  novel_title: string;
}

const SourceDetail = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const navigate = useNavigate();
  const [source, setSource] = useState<SourceDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSourceDetail = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      try {
        const data = await novelService.getSourceDetail(novelSlug, sourceSlug);
        setSource(data);
      } catch (err) {
        console.error('Error fetching source details:', err);
        setError('Failed to load source details. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchSourceDetail();
  }, [novelSlug, sourceSlug]);

  const handleBackClick = () => {
    if (source) {
      navigate(`/novels/${source.novel_slug}`);
    } else {
      navigate('/novels');
    }
  };

  const handleChaptersClick = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  // Format date to readable format
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    }).format(date);
  };

  const defaultCover = '/default-cover.jpg';

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error || !source) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
          Back to Novel
        </Button>
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || 'Source not found'}</Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
        Back to Novel
      </Button>

      <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
        <Grid container spacing={3}>
          <Grid item xs={12} md={4}>
            <Card sx={{ height: '100%' }}>
              <CardMedia
                component="img"
                image={source.cover_url || defaultCover}
                alt={source.title}
                sx={{ height: 400, objectFit: 'contain' }}
                onError={(e: any) => {
                  e.target.onerror = null;
                  e.target.src = defaultCover;
                }}
              />
            </Card>
          </Grid>
          
          <Grid item xs={12} md={8}>
            <Typography variant="h4" gutterBottom>
              {source.title}
            </Typography>
            
            <Typography variant="subtitle1" color="text.secondary" gutterBottom>
              From: {source.source_name}
            </Typography>
            
            {source.authors.length > 0 && (
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle1" component="span">
                  Author{source.authors.length > 1 ? 's' : ''}: 
                </Typography>
                <Typography component="span" sx={{ ml: 1 }}>
                  {source.authors.join(', ')}
                </Typography>
              </Box>
            )}
            
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" component="span">
                Status:
              </Typography>
              <Chip 
                label={source.status} 
                size="small" 
                color={source.status === 'Completed' ? 'success' : 'primary'} 
                sx={{ ml: 1 }} 
              />
            </Box>
            
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" component="span">
                Language:
              </Typography>
              <Typography component="span" sx={{ ml: 1 }}>
                {source.language}
              </Typography>
            </Box>
            
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" component="span">
                Last Updated:
              </Typography>
              <Typography component="span" sx={{ ml: 1 }}>
                {formatDate(source.last_updated)}
              </Typography>
            </Box>
            
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle1" component="span">
                Chapters:
              </Typography>
              <Typography component="span" sx={{ ml: 1 }}>
                {source.chapters_count}
              </Typography>
            </Box>
            
            <Box sx={{ mt: 3, display: 'flex', gap: 2, flexWrap: 'wrap' }}>
              <Button 
                variant="contained" 
                color="primary" 
                size="large" 
                startIcon={<MenuBookIcon />}
                onClick={handleChaptersClick}
                disabled={source.chapters_count === 0}
              >
                Read Chapters
              </Button>
              
              <Button 
                variant="outlined" 
                color="primary" 
                size="large" 
                startIcon={<LanguageIcon />}
                href={source.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                Visit Source
              </Button>
            </Box>
          </Grid>
        </Grid>
        
        {(source.genres.length > 0 || source.tags.length > 0) && (
          <Box sx={{ mt: 4 }}>
            <Divider sx={{ mb: 2 }} />
            
            <Grid container spacing={3}>
              {source.genres.length > 0 && (
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Genres
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {source.genres.map((genre, index) => (
                      <Chip key={index} label={genre} size="medium" />
                    ))}
                  </Box>
                </Grid>
              )}
              
              {source.tags.length > 0 && (
                <Grid item xs={12} md={6}>
                  <Typography variant="h6" gutterBottom>
                    Tags
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {source.tags.map((tag, index) => (
                      <Chip key={index} label={tag} size="medium" variant="outlined" />
                    ))}
                  </Box>
                </Grid>
              )}
            </Grid>
          </Box>
        )}
        
        <Box sx={{ mt: 4 }}>
          <Divider sx={{ mb: 2 }} />
          <Typography variant="h6" gutterBottom>
            Synopsis
          </Typography>
          <Typography variant="body1" paragraph>
            {source.synopsis || 'No synopsis available'}
          </Typography>
        </Box>
      </Paper>
    </Container>
  );
};

export default SourceDetail;
