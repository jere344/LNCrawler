import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
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
  IconButton,
  Tooltip,
  Rating,
  Tabs,
  Tab,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import LanguageIcon from '@mui/icons-material/Language';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import StarIcon from '@mui/icons-material/Star';
import StarBorderIcon from '@mui/icons-material/StarBorder';
import CommentIcon from '@mui/icons-material/Comment';
import defaultCover from '@assets/default-cover.jpg';
import CommentSection from '../comments/CommentSection';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceDetail = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const navigate = useNavigate();
  const [source, setSource] = useState<ISourceDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [votingInProgress, setVotingInProgress] = useState<boolean>(false);
  const [novelRating, setNovelRating] = useState<{ avg_rating: number | null, rating_count: number, user_rating: number | null }>({
    avg_rating: null, 
    rating_count: 0, 
    user_rating: null
  });
  const [ratingInProgress, setRatingInProgress] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState(0);
  const [commentsLoaded, setCommentsLoaded] = useState(false);

  useEffect(() => {
    const fetchSourceDetail = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      try {
        const data = await novelService.getSourceDetail(novelSlug, sourceSlug);
        setSource(data);
        
        // Get novel details to fetch rating
        const novelDetails = await novelService.getNovelDetail(novelSlug);
        setNovelRating({
          avg_rating: novelDetails.avg_rating,
          rating_count: novelDetails.rating_count,
          user_rating: novelDetails.user_rating
        });
      } catch (err) {
        console.error('Error fetching source details:', err);
        setError('Failed to load source details. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchSourceDetail();
  }, [novelSlug, sourceSlug]);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    
    // Load comments only when switching to the comments tab for the first time
    if (newValue === 1 && !commentsLoaded) {
      setCommentsLoaded(true);
    }
  };

  const handleBackClick = () => {
    if (source) {
      navigate(`/novels/${source.novel_slug}`);
    } else {
      navigate('/');
    }
  };

  const handleChaptersClick = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleVote = async (voteType: 'up' | 'down') => {
    if (!novelSlug || !sourceSlug || votingInProgress || !source) return;
    
    setVotingInProgress(true);
    try {
      const voteResponse = await novelService.voteSource(novelSlug, sourceSlug, voteType);
      setSource({
        ...source,
        upvotes: voteResponse.upvotes,
        downvotes: voteResponse.downvotes,
        vote_score: voteResponse.vote_score,
        user_vote: voteResponse.user_vote
      });
    } catch (err) {
      console.error('Error voting for source:', err);
    } finally {
      setVotingInProgress(false);
    }
  };

  const handleRatingChange = async (_event: React.SyntheticEvent, value: number | null) => {
    if (!value || !novelSlug || ratingInProgress) return;
    
    setRatingInProgress(true);
    try {
      const ratingResponse = await novelService.rateNovel(novelSlug, value);
      setNovelRating({
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

  // Format date to readable format
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    }).format(date);
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
            <Box sx={{ 
                position: 'relative', 
                width: '100%',
                paddingTop: '150%', // 2:3 aspect ratio (standard book cover ratio)
                overflow: 'hidden'
              }}>
                <Card sx={{ 
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: '100%',
                  display: 'flex'
                }}>
                  <CardMedia
                    component="img"
                    image={source.cover_url || defaultCover}
                    alt={source.title}
                    sx={{ 
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover'
                    }}
                    onError={(e: any) => {
                      e.target.onerror = null;
                      e.target.src = defaultCover;
                    }}
                  />
                </Card>
              </Box>
          </Grid>
          
          <Grid item xs={12} md={8}>
            <Typography variant="h4" gutterBottom>
              {source.title}
            </Typography>
            
            {/* Novel rating component */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Rating
                name="novel-rating"
                value={novelRating.user_rating || 0}
                onChange={handleRatingChange}
                precision={1}
                icon={<StarIcon fontSize="inherit" />}
                emptyIcon={<StarBorderIcon fontSize="inherit" />}
                disabled={ratingInProgress}
              />
              
              <Typography variant="body2" sx={{ ml: 1 }}>
                {novelRating.avg_rating ? `${novelRating.avg_rating} / 5` : 'No ratings yet'}
                {novelRating.rating_count ? ` (${novelRating.rating_count} ${novelRating.rating_count === 1 ? 'rating' : 'ratings'})` : ''}
              </Typography>
            </Box>
            
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
                {formatDate(source.last_chapter_update)}
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
            
            {/* Vote section */}
            <Box sx={{ mb: 3, display: 'flex', alignItems: 'center' }}>
              <Typography variant="subtitle1" sx={{ mr: 2 }}>
                Source Rating:
              </Typography>
              
              <Tooltip title="Upvote this source">
                <IconButton 
                  color={source.user_vote === 'up' ? 'primary' : 'default'}
                  onClick={() => handleVote('up')}
                  disabled={votingInProgress}
                >
                  <ThumbUpIcon />
                </IconButton>
              </Tooltip>
              
              <Typography variant="body1" sx={{ mx: 1 }}>
                {source.vote_score}
              </Typography>
              
              <Tooltip title="Downvote this source">
                <IconButton 
                  color={source.user_vote === 'down' ? 'error' : 'default'}
                  onClick={() => handleVote('down')}
                  disabled={votingInProgress}
                >
                  <ThumbDownIcon />
                </IconButton>
              </Tooltip>
              
              <Typography variant="caption" color="text.secondary" sx={{ ml: 2 }}>
                ({source.upvotes} up / {source.downvotes} down)
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
        
        {/* Add a tab system for details and comments */}
        <Box sx={{ mt: 4 }}>
          <Divider sx={{ mb: 2 }} />
          
          <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={activeTab} onChange={handleTabChange} aria-label="novel content tabs">
              <Tab label="Details" id="tab-0" />
              <Tab 
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    Comments
                    <CommentIcon sx={{ ml: 1 }} />
                  </Box>
                } 
                id="tab-1" 
              />
            </Tabs>
          </Box>
          
          {/* Details Tab */}
          <Box role="tabpanel" hidden={activeTab !== 0} sx={{ py: 3 }}>
            {(source.genres.length > 0 || source.tags.length > 0) && (
              <Box sx={{ mb: 4 }}>
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
            
            <Box sx={{ mt: 2 }}>
              <Typography variant="h6" gutterBottom>
                Synopsis
              </Typography>
              <Typography variant="body1" paragraph dangerouslySetInnerHTML={{ __html: source.synopsis || 'No synopsis available' }} />
            </Box>
          </Box>
          
          {/* Comments Tab */}
          <Box role="tabpanel" hidden={activeTab !== 1} sx={{ py: 3 }}>
            {novelSlug && activeTab === 1 && (
              <CommentSection 
                novelSlug={novelSlug}
                title="Novel Comments" 
              />
            )}
          </Box>
        </Box>
      </Paper>
    </Container>
  );
};

export default SourceDetail;
