import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Paper,
  Button,
  Chip,
  CardMedia,
  IconButton,
  Tooltip,
  useTheme,
  alpha,
  Skeleton,
  Zoom,
  Grid2 as Grid,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import LanguageIcon from '@mui/icons-material/Language';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import CommentIcon from '@mui/icons-material/Comment';
import PersonIcon from '@mui/icons-material/Person';
import FlagIcon from '@mui/icons-material/Flag';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import ListAltIcon from '@mui/icons-material/ListAlt';
import LaunchIcon from '@mui/icons-material/Launch';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import SkipNextIcon from '@mui/icons-material/SkipNext';
import ViewListIcon from '@mui/icons-material/ViewList';
import defaultCover from '@assets/default-cover.jpg';
import CommentSection from '../comments/CommentSection';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';
import NovelSynopsis from './common/NovelSynopsis';
import NovelRating from './common/NovelRating';
import NovelGenres from './common/NovelGenres';
import NovelTags from './common/NovelTags';
import NovelUpdateButton from './common/NovelUpdateButton';

const SourceDetail = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const navigate = useNavigate();
  const theme = useTheme();
  const [source, setSource] = useState<ISourceDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [votingInProgress, setVotingInProgress] = useState<boolean>(false);
  const [novelRating, setNovelRating] = useState<{ avg_rating: number | null, rating_count: number, user_rating: number | null }>({
    avg_rating: null, 
    rating_count: 0, 
    user_rating: null
  });

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

  const handleFirstChapterClick = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/1`);
  };

  const handleLatestChapterClick = () => {
    if (!source) return;
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${source.chapters_count}`);
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
      <Container maxWidth="lg">
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
          <Skeleton variant="rectangular" width={120} height={36} sx={{ borderRadius: '20px' }} />
        </Box>

        <Paper 
          elevation={0}
          sx={{ 
            p: 0,
            overflow: 'hidden',
            borderRadius: 3,
            mb: 4,
            position: 'relative',
            background: `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.3)} 0%, ${alpha(theme.palette.primary.main, 0.1)} 100%)`,
          }}
        >
          <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 4, lg: 3 }}>
                <Box
                  sx={{
                    position: 'relative',
                    width: '100%',
                    paddingTop: '150%',
                    borderRadius: 2,
                    overflow: 'hidden',
                    boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
                    border: `4px solid ${theme.palette.common.white}`,
                  }}
                >
                  <Skeleton 
                    variant="rectangular" 
                    width="100%" 
                    height="100%" 
                    sx={{ position: 'absolute', top: 0, left: 0 }} 
                    animation="wave"
                  />
                </Box>
              </Grid>
              
              <Grid size={{ xs: 12, md: 8, lg: 9 }}>
                <Skeleton variant="text" width="80%" height={60} sx={{ mb: 1 }} animation="wave" />
                <Skeleton variant="text" width="60%" height={40} sx={{ mb: 3 }} animation="wave" />
                
                <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                    <Skeleton variant="rectangular" width={150} height={36} sx={{ borderRadius: 6 }} animation="wave" />
                    <Skeleton variant="rectangular" width={100} height={36} sx={{ borderRadius: 6 }} animation="wave" />
                  </Box>
                  
                  <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
                    <Skeleton variant="rectangular" width={200} height={30} animation="wave" />
                  </Box>
                </Box>
                
                <Box 
                  sx={{ 
                    height: '2px', 
                    background: `linear-gradient(to right, ${alpha(theme.palette.common.white, 0.8)}, transparent)`,
                    mb: 2.5,
                    mt: 0.5,
                  }} 
                />
                
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                    <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 2 }} animation="wave" />
                  </Grid>
                  
                  <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                    <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 2 }} animation="wave" />
                  </Grid>
                </Grid>
                
                <Box sx={{ mb: 3 }}>
                  <Skeleton variant="text" width={150} height={20} sx={{ mb: 1 }} animation="wave" />
                  <Box sx={{ display: 'flex', gap: 2 }}>
                    <Skeleton variant="rectangular" width={150} height={40} sx={{ borderRadius: '20px' }} animation="wave" />
                    <Skeleton variant="rectangular" width={150} height={40} sx={{ borderRadius: '20px' }} animation="wave" />
                  </Box>
                </Box>
                
                <Box sx={{ 
                  width: '100%', 
                  display: 'flex', 
                  flexDirection: { xs: 'column', sm: 'row' }, 
                  gap: 1,
                  mb: 1
                }}>
                  <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
                  <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
                  <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Update Button Section Skeleton */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: { xs: 2, md: 3 }, 
            mb: 4, 
            borderRadius: 3,
            background: theme.palette.mode === 'dark' 
              ? alpha(theme.palette.background.paper, 0.95)
              : theme.palette.background.default,
          }}
        >
          <Skeleton variant="rectangular" width="100%" height={100} sx={{ borderRadius: 2 }} animation="wave" />
        </Paper>

        {/* Genres and Tags Section Skeleton */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: 3, 
            mb: 4, 
            borderRadius: 3,
            background: theme.palette.mode === 'dark' 
              ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
              : theme.palette.background.paper,
          }}
        >
          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 6 }}>
              <Skeleton variant="text" width={100} height={30} sx={{ mb: 2 }} animation="wave" />
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {[...Array(5)].map((_, i) => (
                  <Skeleton key={i} variant="rectangular" width={80} height={32} sx={{ borderRadius: 4 }} animation="wave" />
                ))}
              </Box>
            </Grid>
            
            <Grid size={{ xs: 12, md: 6 }}>
              <Skeleton variant="text" width={100} height={30} sx={{ mb: 2 }} animation="wave" />
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {[...Array(7)].map((_, i) => (
                  <Skeleton key={i} variant="rectangular" width={60} height={32} sx={{ borderRadius: 4 }} animation="wave" />
                ))}
              </Box>
            </Grid>
          </Grid>
        </Paper>
        
        {/* Synopsis Section Skeleton */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: 3, 
            mb: 4, 
            borderRadius: 3,
            background: theme.palette.mode === 'dark' 
              ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
              : theme.palette.background.paper,
          }}
        >
          <Skeleton variant="text" width={150} height={40} sx={{ mb: 2 }} animation="wave" />
          {[...Array(6)].map((_, i) => (
            <Skeleton key={i} variant="text" width="100%" height={20} sx={{ mb: 1 }} animation="wave" />
          ))}
        </Paper>

        {/* Comments Section Skeleton */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: 3,
            mb: 4, 
            borderRadius: 3,
            background: theme.palette.mode === 'dark' 
              ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
              : theme.palette.background.paper,
          }}
        >
          <Skeleton variant="text" width={150} height={40} sx={{ mb: 2 }} animation="wave" />
          <Skeleton variant="rectangular" width="100%" height={150} sx={{ mb: 2, borderRadius: 2 }} animation="wave" />
          {[...Array(3)].map((_, i) => (
            <Box key={i} sx={{ mb: 3 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                <Skeleton variant="circular" width={40} height={40} sx={{ mr: 2 }} animation="wave" />
                <Box>
                  <Skeleton variant="text" width={120} height={24} animation="wave" />
                  <Skeleton variant="text" width={80} height={16} animation="wave" />
                </Box>
              </Box>
              <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 1 }} animation="wave" />
            </Box>
          ))}
        </Paper>
      </Container>
    );
  }

  if (error || !source) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
          Back to Novel
        </Button>
        <Paper 
          elevation={3} 
          sx={{ 
            p: 4, 
            textAlign: 'center', 
            mt: 3, 
            borderRadius: 3,
            background: `linear-gradient(135deg, ${alpha(theme.palette.error.dark, 0.05)} 0%, ${alpha(theme.palette.error.light, 0.1)} 100%)`,
          }}
        >
          <Typography color="error" variant="h5" gutterBottom>
            {error || 'Source not found'}
          </Typography>
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleBackClick}
            sx={{ mt: 2 }}
          >
            Return to Novel
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
      <Container maxWidth="lg">
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
          <Button 
            startIcon={<ArrowBackIcon />} 
            onClick={handleBackClick}
            variant="outlined"
            sx={{ 
              borderRadius: '20px',
              px: 2,
            }}
          >
            Back to Novel
          </Button>
        </Box>

        <Paper 
          elevation={0}
          sx={{ 
            p: 0,
            overflow: 'hidden',
            borderRadius: 3,
            mb: 4,
            position: 'relative',
            background: `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.3)} 0%, ${alpha(theme.palette.primary.main, 0.1)} 100%)`,
          }}
        >
          {/* Hero background with blur effect */}
          <Box 
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              opacity: 0.35,
              backgroundImage: `url(${source.cover_url || defaultCover})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(20px)',
              zIndex: 0,
            }}
          />
          
          <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 4, lg: 3 }}>
                <Zoom in={true} timeout={1000}>
                  <Box
                    sx={{
                      position: 'relative',
                      width: '100%',
                      paddingTop: '150%',
                      borderRadius: 2,
                      overflow: 'hidden',
                      boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
                      border: `4px solid ${theme.palette.common.white}`,
                    }}
                  >
                    <CardMedia
                      component="img"
                      image={source.cover_url || defaultCover}
                      alt={source.title}
                      sx={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        height: '100%',
                        objectFit: 'cover',
                      }}
                      onError={(e: any) => {
                        e.target.onerror = null;
                        e.target.src = defaultCover;
                      }}
                    />
                    
                    {/* Language indicator */}
                    <Box
                      sx={{
                        position: 'absolute',
                        bottom: 8,
                        right: 8,
                        bgcolor: 'rgba(0,0,0,0.7)',
                        color: 'white',
                        px: 1,
                        py: 0.3,
                        borderRadius: 1,
                        fontSize: '0.75rem',
                        fontWeight: 'bold',
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        textTransform: 'uppercase',
                      }}
                    >
                      <LanguageIcon sx={{ fontSize: '0.9rem' }} />
                      {source.language}
                    </Box>
                  </Box>
                </Zoom>
              </Grid>
              
              <Grid size={{ xs: 12, md: 8, lg: 9 }}>
                <Typography 
                  variant="h3" 
                  gutterBottom 
                  sx={{ 
                    color: 'common.white',
                    textShadow: '0 2px 4px rgba(0,0,0,0.2)',
                    fontWeight: 700,
                  }}
                >
                  {source.title}
                </Typography>
                
                <Typography 
                  variant="h6" 
                  sx={{ 
                    color: alpha(theme.palette.common.white, 0.9),
                    mb: 3,
                    textShadow: '0 1px 3px rgba(0,0,0,0.2)',
                    fontWeight: 500,
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1
                  }}
                >
                  From: {source.source_name}
                  <Tooltip title="Visit Source">
                    <IconButton
                      size="small"
                      href={source.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      sx={{ 
                        color: alpha(theme.palette.common.white, 0.9),
                        '&:hover': {
                          color: theme.palette.common.white,
                          bgcolor: alpha(theme.palette.common.white, 0.1)
                        }
                      }}
                    >
                      <LaunchIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Typography>
                
                {/* Author and Status badges */}
                <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                    {source.authors.length > 0 && (
                      <Box
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          bgcolor: alpha('#8e44ad', 0.7),
                          backdropFilter: 'blur(10px)',
                          px: 2,
                          py: 0.75,
                          borderRadius: 6,
                        }}
                      >
                        <Typography 
                          variant="body1" 
                          sx={{ 
                            color: theme.palette.common.white,
                            fontWeight: 600,
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <PersonIcon sx={{ mr: 1, fontSize: '1rem' }} />
                          {source.authors.join(', ')}
                        </Typography>
                      </Box>
                    )}
                    
                    {source.status && (
                      <Chip
                        icon={<FlagIcon />}
                        label={source.status}
                        size="medium"
                        sx={{
                          bgcolor: source.status.toLowerCase() === 'completed' ? 
                            alpha('#27ae60', 0.7) : alpha('#3498db', 0.7),
                          color: 'white',
                          fontWeight: 600,
                          backdropFilter: 'blur(10px)',
                          '& .MuiChip-icon': { color: 'white' }
                        }}
                      />
                    )}
                  </Box>
                  
                  {/* Novel rating component with better styling */}
                  <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
                    {novelSlug && (
                      <NovelRating
                        novelSlug={novelSlug}
                        initialUserRating={novelRating.user_rating}
                        initialAvgRating={novelRating.avg_rating}
                        initialRatingCount={novelRating.rating_count}
                        size="small"
                      />
                    )}
                  </Box>
                </Box>
                
                {/* Divider with gradient */}
                <Box 
                  sx={{ 
                    height: '2px', 
                    background: `linear-gradient(to right, ${alpha(theme.palette.common.white, 0.8)}, transparent)`,
                    mb: 2.5,
                    mt: 0.5,
                  }} 
                />
                
                {/* Source stats with improved design */}
                <Grid container spacing={2} sx={{ mb: 3 }}>
                  <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        p: 1,
                        borderRadius: 2,
                        bgcolor: alpha('#3498db', 0.3),
                        backdropFilter: 'blur(10px)',
                        border: `1px solid ${alpha('#3498db', 0.5)}`,
                      }}
                    >
                      <ListAltIcon sx={{ color: alpha('#3498db', 0.9), mr: 1 }} />
                      <Box>
                        <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.7) }}>
                          Chapters
                        </Typography>
                        <Typography variant="body1" sx={{ fontWeight: 700, color: theme.palette.common.white }}>
                          {source.chapters_count}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                  
                  <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                    <Box
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        p: 1,
                        borderRadius: 2,
                        bgcolor: alpha('#9b59b6', 0.3),
                        backdropFilter: 'blur(10px)',
                        border: `1px solid ${alpha('#9b59b6', 0.5)}`,
                      }}
                    >
                      <CalendarTodayIcon sx={{ color: alpha('#9b59b6', 0.9), mr: 1 }} />
                      <Box>
                        <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.7) }}>
                          Last Updated
                        </Typography>
                        <Typography variant="body1" sx={{ fontWeight: 700, color: theme.palette.common.white }}>
                          {formatDate(source.last_chapter_update)}
                        </Typography>
                      </Box>
                    </Box>
                  </Grid>
                </Grid>
                
                {/* Source vote actions with integrated display */}
                <Box sx={{ mb: 3 }}>
                  <Typography variant="body2" sx={{ color: alpha(theme.palette.common.white, 0.8), mb: 1 }}>
                    Rate this source:
                  </Typography>
                  <Box sx={{ display: 'flex', gap: 2 }}>
                    <Button
                      variant={source.user_vote === 'up' ? 'contained' : 'outlined'}
                      color="success"
                      startIcon={<ThumbUpIcon />}
                      onClick={() => handleVote('up')}
                      disabled={votingInProgress}
                      sx={{ 
                        borderRadius: '20px',
                        px: 2,
                        backdropFilter: 'blur(10px)',
                        minWidth: '120px',
                        position: 'relative'
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        Upvote
                        <Typography
                          variant="body2"
                          sx={{
                            bgcolor: alpha(theme.palette.success.main, 0.2),
                            px: 1,
                            py: 0.2,
                            borderRadius: 1,
                            fontWeight: 'bold'
                          }}
                        >
                          {source.upvotes}
                        </Typography>
                      </Box>
                    </Button>
                    
                    <Button
                      variant={source.user_vote === 'down' ? 'contained' : 'outlined'}
                      color="error"
                      startIcon={<ThumbDownIcon />}
                      onClick={() => handleVote('down')}
                      disabled={votingInProgress}
                      sx={{ 
                        borderRadius: '20px',
                        px: 2,
                        backdropFilter: 'blur(10px)',
                        minWidth: '120px',
                        position: 'relative'
                      }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        Downvote
                        <Typography
                          variant="body2"
                          sx={{
                            bgcolor: alpha(theme.palette.error.main, 0.2),
                            px: 1,
                            py: 0.2,
                            borderRadius: 1,
                            fontWeight: 'bold'
                          }}
                        >
                          {source.downvotes}
                        </Typography>
                      </Box>
                    </Button>
                  </Box>
                </Box>
                
                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  {/* Replace the existing chapter buttons with the following improved version */}
                  <Box sx={{ 
                    width: '100%', 
                    display: 'flex', 
                    flexDirection: { xs: 'column', sm: 'row' }, 
                    gap: 1,
                    mb: 1
                  }}>
                    <Tooltip title="Browse all chapters" arrow placement="top">
                      <Button 
                        variant="contained" 
                        color="info" 
                        size="large" 
                        fullWidth
                        startIcon={<ViewListIcon />}
                        onClick={handleChaptersClick}
                        disabled={source.chapters_count === 0}
                        sx={{
                          borderRadius: '12px',
                          p: 1.5,
                          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                          display: 'flex',
                          justifyContent: 'flex-start',
                          alignItems: 'center',
                          textAlign: 'left',
                          position: 'relative',
                          overflow: 'hidden',
                        }}
                      >
                        <Box sx={{ zIndex: 1 }}>
                          <Typography variant="button" sx={{ display: 'block', fontWeight: 700 }}>
                            Chapter List
                          </Typography>
                          <Typography variant="caption" sx={{ opacity: 0.8 }}>
                            View all {source.chapters_count} chapters
                          </Typography>
                        </Box>
                        <ListAltIcon sx={{ 
                          position: 'absolute', 
                          right: '5px',  
                          fontSize: '3rem', 
                          opacity: 0.2,
                          transform: 'rotate(15deg)'
                        }} />
                      </Button>
                    </Tooltip>

                    <Tooltip title="Start reading from chapter 1" arrow placement="top">
                      <Button
                        variant="contained"
                        color="success"
                        size="large"
                        fullWidth
                        startIcon={<PlayArrowIcon />}
                        onClick={handleFirstChapterClick}
                        disabled={source.chapters_count === 0}
                        sx={{
                          borderRadius: '12px',
                          p: 1.5,
                          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                          display: 'flex',
                          justifyContent: 'flex-start',
                          alignItems: 'center',
                          textAlign: 'left',
                          position: 'relative',
                          overflow: 'hidden',
                        }}
                      >
                        <Box sx={{ zIndex: 1 }}>
                          <Typography variant="button" sx={{ display: 'block', fontWeight: 700 }}>
                            Start Reading
                          </Typography>
                          <Typography variant="caption" sx={{ opacity: 0.8 }}>
                            From Chapter 1
                          </Typography>
                        </Box>
                        <PlayArrowIcon sx={{ 
                          position: 'absolute', 
                          right: '5px', 
                          fontSize: '3rem', 
                          opacity: 0.2,
                          transform: 'rotate(15deg)'
                        }} />
                      </Button>
                    </Tooltip>

                    <Tooltip title="Jump to the most recent chapter" arrow placement="top">
                      <Button
                        variant="contained"
                        color="secondary"
                        size="large"
                        fullWidth
                        startIcon={<SkipNextIcon />}
                        onClick={handleLatestChapterClick}
                        disabled={source.chapters_count === 0}
                        sx={{
                          borderRadius: '12px',
                          p: 1.5,
                          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                          display: 'flex',
                          justifyContent: 'flex-start',
                          alignItems: 'center',
                          textAlign: 'left',
                          position: 'relative',
                          overflow: 'hidden',
                        }}
                      >
                        <Box sx={{ zIndex: 1 }}>
                          <Typography variant="button" sx={{ display: 'block', fontWeight: 700 }}>
                            Latest Chapter
                          </Typography>
                          <Typography variant="caption" sx={{ opacity: 0.8 }}>
                            Chapter {source.chapters_count}
                          </Typography>
                        </Box>
                        <SkipNextIcon sx={{ 
                          position: 'absolute', 
                          right: '5px', 
                          fontSize: '3rem', 
                          opacity: 0.2,
                          transform: 'rotate(15deg)'
                        }} />
                      </Button>
                    </Tooltip>
                  </Box>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Update Button Section */}
        {source && source.source_url && (
          <Paper 
            elevation={3} 
            sx={{ 
              p: { xs: 2, md: 3 }, 
              mb: 4, 
              borderRadius: 3,
              background: theme.palette.mode === 'dark' 
                ? alpha(theme.palette.background.paper, 0.95)
                : theme.palette.background.default,
            }}
          >
            <NovelUpdateButton 
              sourceUrl={source.source_url} 
              novelTitle={source.title} 
            />
          </Paper>
        )}

        {/* Genres and Tags Section */}
        {(source.genres.length > 0 || source.tags.length > 0) && (
          <Paper 
            elevation={3} 
            sx={{ 
              p: 3, 
              mb: 4, 
              borderRadius: 3,
              background: theme.palette.mode === 'dark' 
                ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
                : theme.palette.background.paper,
            }}
          >
            <Grid container spacing={3}>
              {source.genres.length > 0 && (
                <Grid size={{ xs: 12, md: source.tags.length > 0 ? 6 : 12 }}>
                  <NovelGenres 
                    genres={source.genres} 
                    title="Genres"
                    titleVariant="h6"
                    chipSize="medium"
                    textColor={theme.palette.text.primary}
                    showTitle={true} 
                  />
                </Grid>
              )}
              
              {source.tags.length > 0 && (
                <Grid size={{ xs: 12, md: source.genres.length > 0 ? 6 : 12 }}>
                  <NovelTags 
                    tags={source.tags} 
                    title="Tags"
                    titleVariant="h6"
                    chipSize="medium"
                  />
                </Grid>
              )}
            </Grid>
          </Paper>
        )}
        
        <NovelSynopsis synopsis={source.synopsis || 'No synopsis available'} />

        {/* Comments Section */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: 3,
            mb: 4, 
            borderRadius: 3,
            background: theme.palette.mode === 'dark' 
              ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
              : theme.palette.background.paper,
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          {/* Decorative element */}
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '5px',
              height: '100%',
              background: `linear-gradient(to bottom, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
            }}
          />

          <Typography 
            variant="h5" 
            gutterBottom 
            sx={{ 
              pl: 2,
              borderBottom: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
              pb: 1,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <CommentIcon sx={{ mr: 1, color: theme.palette.primary.main }} />
            Comments
          </Typography>
          
          {novelSlug && (
            <Box sx={{ px: 2, py: 1 }}>
              <CommentSection 
                novelSlug={novelSlug}
                title="Novel Comments" 
              />
            </Box>
          )}
        </Paper>
      </Container>
  );
};

export default SourceDetail;
