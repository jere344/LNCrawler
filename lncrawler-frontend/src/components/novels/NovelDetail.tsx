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
  ListItemText,
  IconButton,
  Tooltip,
  Badge,
  Rating,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import PriorityHighIcon from '@mui/icons-material/PriorityHigh';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import defaultCover from '@assets/default-cover.jpg';

interface NovelSource {
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
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user_vote: 'up' | 'down' | null;
}

interface NovelDetail {
  id: string;
  title: string;
  slug: string;
  sources: NovelSource[];
  created_at: string;
  updated_at: string;
  avg_rating: number | null;
  rating_count: number;
  user_rating: number | null;
}

const NovelDetail = () => {
  const { novelSlug } = useParams<{ novelSlug: string }>();
  const navigate = useNavigate();
  const [novel, setNovel] = useState<NovelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [votingInProgress, setVotingInProgress] = useState<{[key: string]: boolean}>({});
  const [ratingInProgress, setRatingInProgress] = useState<boolean>(false);

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

  const handleVote = async (sourceSlug: string, voteType: 'up' | 'down', event: React.MouseEvent) => {
    event.stopPropagation();
    if (!novelSlug || votingInProgress[sourceSlug]) return;
    
    setVotingInProgress(prev => ({ ...prev, [sourceSlug]: true }));
    try {
      const voteResponse = await novelService.voteSource(novelSlug, sourceSlug, voteType);
      
      if (novel) {
        const updatedSources = novel.sources.map(source => {
          if (source.source_slug === sourceSlug) {
            return {
              ...source,
              upvotes: voteResponse.upvotes,
              downvotes: voteResponse.downvotes,
              vote_score: voteResponse.vote_score,
              user_vote: voteResponse.user_vote
            };
          }
          return source;
        });
        
        // Sort sources by vote score
        updatedSources.sort((a, b) => b.vote_score - a.vote_score);
        
        setNovel({
          ...novel,
          sources: updatedSources
        });
      }
    } catch (err) {
      console.error('Error voting for source:', err);
    } finally {
      setVotingInProgress(prev => ({ ...prev, [sourceSlug]: false }));
    }
  };

  const handleRatingChange = async (event: React.SyntheticEvent, value: number | null) => {
    if (!value || !novelSlug || !novel || ratingInProgress) return;
    
    setRatingInProgress(true);
    try {
      const ratingResponse = await novelService.rateNovel(novelSlug, value);
      setNovel({
        ...novel,
        avg_rating: ratingResponse.avg_rating,
        rating_count: ratingResponse.rating_count,
        user_rating: ratingResponse.user_rating
      });
    } catch (err) {
      console.error('Error rating novel:', err);
    } finally {
      setRatingInProgress(false);
    }
  };

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

  // Use the first source in the sorted list (by votes) as the primary source
  const primarySource = novel?.sources[0] || null;

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
                  image={primarySource.cover_url ? (import.meta.env.VITE_API_BASE_URL + "/" + primarySource.cover_url) : defaultCover}
                  alt={novel?.title}
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
                {novel?.title}
              </Typography>
              
              {/* Rating component */}
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                <Rating
                  name="novel-rating"
                  value={novel?.user_rating || 0}
                  onChange={handleRatingChange}
                  precision={1}
                  icon={<StarIcon fontSize="inherit" />}
                  emptyIcon={<StarBorderIcon fontSize="inherit" />}
                  disabled={ratingInProgress}
                />
                
                <Typography variant="body2" sx={{ ml: 1 }}>
                  {novel?.avg_rating ? `${novel.avg_rating} / 5` : 'No ratings yet'}
                  {novel?.rating_count ? ` (${novel.rating_count} ${novel.rating_count === 1 ? 'rating' : 'ratings'})` : ''}
                </Typography>
              </Box>
              
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
                  position: 'relative',
                }}
              >
                {index === 0 && (
                  <Tooltip title="Primary Source (highest rated)">
                    <Chip
                      icon={<PriorityHighIcon />}
                      label="Primary"
                      color="primary"
                      size="small"
                      sx={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        zIndex: 1
                      }}
                    />
                  </Tooltip>
                )}
                
                {/* Card content area (clickable) */}
                <Box sx={{ flexGrow: 1 }}>
                  <CardActionArea 
                    onClick={() => handleSourceClick(source.source_slug)}
                    sx={{ height: '100%' }}
                  >
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
                </Box>
                
                {/* Voting area (separate from clickable area) */}
                <Divider />
                <Box sx={{ p: 1, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">
                    Rating: <strong>{source.vote_score}</strong>
                  </Typography>
                  
                  <Box>
                    <Tooltip title="Upvote">
                      <IconButton 
                        size="small" 
                        color={source.user_vote === 'up' ? 'primary' : 'default'}
                        onClick={(e) => handleVote(source.source_slug, 'up', e)}
                        disabled={votingInProgress[source.source_slug]}
                      >
                        <ThumbUpIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    
                    <Tooltip title="Downvote">
                      <IconButton 
                        size="small" 
                        color={source.user_vote === 'down' ? 'error' : 'default'}
                        onClick={(e) => handleVote(source.source_slug, 'down', e)}
                        disabled={votingInProgress[source.source_slug]}
                      >
                        <ThumbDownIcon fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Paper>
    </Container>
  );
};

export default NovelDetail;
