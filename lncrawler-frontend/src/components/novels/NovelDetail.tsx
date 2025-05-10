import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  Container,
  Typography,
  Grid,
  Box,
  Paper,
  Card,
  CardContent,
  CardMedia,
  Button,
  CircularProgress,
  Divider,
  Chip,
  CardActionArea,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import { utils } from '@utils/textUtils';

interface NovelSource {
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  source_slug: string;  // Add source_slug to the interface
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
}

interface NovelDetail {
  id: string;
  title: string;
  slug: string;
  sources: NovelSource[];
  created_at: string;
  updated_at: string;
}

const NovelDetail = () => {
  const { novelSlug } = useParams<{ novelSlug: string }>();
  const navigate = useNavigate();
  const [novel, setNovel] = useState<NovelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchNovelDetail = async () => {
      if (!novelSlug) return;
      
      setLoading(true);
      try {
        const data = await novelService.getNovelDetail(novelSlug);
        setNovel(data);
      } catch (err) {
        console.error('Error fetching novel details:', err);
        setError('Failed to load novel details. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchNovelDetail();
  }, [novelSlug]);

  const handleBackClick = () => {
    navigate('/novels');
  };

  const handleSourceClick = (sourceSlug: string) => {
    if (!novelSlug) return;
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
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

  if (error || !novel) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
          Back to Novels
        </Button>
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || 'Novel not found'}</Typography>
        </Paper>
      </Container>
    );
  }

  // Take the primary source (first in list)
  const primarySource = novel.sources[0] || null;

  return (
    <Container maxWidth="lg">
      <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
        Back to Novels
      </Button>

      {primarySource && (
        <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={4}>
              <Card sx={{ height: '100%' }}>
                <CardMedia
                  component="img"
                  image={primarySource.cover_url || defaultCover}
                  alt={novel.title}
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
                {novel.title}
              </Typography>
              
              {primarySource.authors.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle1" component="span">
                    Author{primarySource.authors.length > 1 ? 's' : ''}: 
                  </Typography>
                  <Typography component="span" sx={{ ml: 1 }}>
                    {primarySource.authors.join(', ')}
                  </Typography>
                </Box>
              )}

              {primarySource.genres.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle1" gutterBottom>
                    Genres:
                  </Typography>
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                    {primarySource.genres.map((genre, index) => (
                      <Chip key={index} label={genre} size="small" />
                    ))}
                  </Box>
                </Box>
              )}
              
              <Box sx={{ mb: 2 }}>
                <Typography variant="subtitle1" gutterBottom>
                  Available from {novel.sources.length} source{novel.sources.length !== 1 ? 's' : ''}
                </Typography>
              </Box>
            </Grid>
          </Grid>
          
          {primarySource.synopsis && (
            <Box sx={{ mt: 4 }}>
              <Divider sx={{ mb: 2 }} />
              <Typography variant="h6" gutterBottom>
                Synopsis
              </Typography>
              <Typography variant="body1" paragraph>
                {primarySource.synopsis}
              </Typography>
            </Box>
          )}
        </Paper>
      )}

      <Paper elevation={3} sx={{ p: 3, mt: 3 }}>
        <Typography variant="h5" gutterBottom>
          Available Sources
        </Typography>
        <Divider sx={{ mb: 2 }} />
        
        <Grid container spacing={3}>
          {novel.sources.map((source, index) => (
            <Grid item xs={12} sm={6} md={4} key={source.id}>
              <Card 
                sx={{ 
                  height: '100%', 
                  display: 'flex', 
                  flexDirection: 'column',
                  transition: 'transform 0.2s',
                  '&:hover': {
                    transform: 'scale(1.03)'
                  }
                }}
              >
                <CardActionArea onClick={() => handleSourceClick(source.source_slug)}>
                  <CardContent>
                    <Typography variant="h6" gutterBottom>
                      {source.source_name}
                    </Typography>
                    
                    <List dense disablePadding>
                      <ListItem disablePadding>
                        <ListItemText 
                          primary="Status" 
                          secondary={source.status} 
                        />
                      </ListItem>
                      <ListItem disablePadding>
                        <ListItemText 
                          primary="Chapters" 
                          secondary={source.chapters_count} 
                        />
                      </ListItem>
                      <ListItem disablePadding>
                        <ListItemText 
                          primary="Language" 
                          secondary={source.language} 
                        />
                      </ListItem>
                    </List>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Paper>
    </Container>
  );
};

export default NovelDetail;
