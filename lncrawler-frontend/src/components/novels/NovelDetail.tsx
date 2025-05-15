import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PersonIcon from '@mui/icons-material/Person';
import FlagIcon from '@mui/icons-material/Flag';
import {
  Container,
  Typography,
  Grid,
  Box,
  Paper,
  CardMedia,
  Button,
  Divider,
  Chip,
  useTheme,
  alpha,
  Skeleton,
  Fade,
  Zoom,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import defaultCover from '@assets/default-cover.jpg';
import { NovelDetail as INovelDetail } from '@models/novels_types';
import NovelSources from './NovelSources.tsx';
import NovelSynopsis from './common/NovelSynopsis.tsx';
import NovelRating from './common/NovelRating.tsx';
import NovelGenres from './common/NovelGenres.tsx'; // Added import

const NovelDetail = () => {
  const { novelSlug } = useParams<{ novelSlug: string }>();
  const navigate = useNavigate();
  const theme = useTheme();
  const [novel, setNovel] = useState<INovelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [votingInProgress, setVotingInProgress] = useState<{[key: string]: boolean}>({});
  const [pageLoaded, setPageLoaded] = useState<boolean>(false);

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
        setPageLoaded(true)
      }
    };

    fetchNovelDetail();
  }, [novelSlug]);

  const handleBackClick = () => {
    navigate('/');
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
          <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick}>
            Back to Novels
          </Button>
        </Box>
        
        {/* Hero Section Skeleton */}
        <Paper 
          elevation={0}
          sx={{ 
            p: 0,
            overflow: 'hidden',
            borderRadius: 3,
            mb: 4,
            background: `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.8)} 0%, ${alpha(theme.palette.primary.main, 0.6)} 100%)`,
          }}
        >
          <Box sx={{ position: 'relative', height: '300px', overflow: 'hidden' }}>
            <Skeleton variant="rectangular" width="100%" height="100%" animation="wave" />
          </Box>
          
          <Box sx={{ p: 3 }}>
            <Skeleton variant="text" width="60%" height={60} animation="wave" />
            <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 2 }}>
              <Skeleton variant="rectangular" width={150} height={28} animation="wave" />
            </Box>
            
            <Grid container spacing={3} sx={{ mt: 1 }}>
              <Grid item xs={12} md={8}>
                <Skeleton variant="text" width="90%" animation="wave" />
                <Skeleton variant="text" width="75%" animation="wave" />
                <Box sx={{ mt: 3 }}>
                  <Skeleton variant="rectangular" width={120} height={36} animation="wave" sx={{ mr: 2, display: 'inline-block' }} />
                  <Skeleton variant="rectangular" width={120} height={36} animation="wave" sx={{ display: 'inline-block' }} />
                </Box>
              </Grid>
              <Grid item xs={12} md={4}>
                <Skeleton variant="rectangular" width="100%" height={120} animation="wave" />
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Available Sources Skeleton */}
        <Paper 
          elevation={3} 
          sx={{ 
            p: 3, 
            mb: 4, 
            borderRadius: 3,
          }}
        >
          <Skeleton variant="text" width="40%" height={40} animation="wave" />
          <Divider sx={{ my: 2 }} />
          
          <Grid container spacing={3}>
            {[1, 2, 3].map((item) => (
              <Grid item xs={12} sm={6} md={4} key={item}>
                <Skeleton variant="rectangular" width="100%" height={200} animation="wave" sx={{ borderRadius: 2 }} />
              </Grid>
            ))}
          </Grid>
        </Paper>
      </Container>
    );
  }

  if (error || !novel) {
    return (
      <Container maxWidth="lg">
        <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
          Back to Novels
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
          <Typography variant="h5" color="error" gutterBottom>
            {error || 'Novel not found'}
          </Typography>
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleBackClick}
            sx={{ mt: 2 }}
          >
            Return to Home
          </Button>
        </Paper>
      </Container>
    );
  }

  // Use the first source in the sorted list (by votes) as the primary source
  const primarySource = novel?.sources[0] || null;

  return (
    <Fade in={pageLoaded} timeout={800}>
      <Container maxWidth="lg" sx={{ pb: 6 }}>
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
            Back to Novels
          </Button>
        </Box>

        {primarySource && (
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
            id="hero-background"
              sx={{ 
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                height: '100%',
                opacity: 0.35,
                backgroundImage: `url(${primarySource.cover_url || defaultCover})`,
                backgroundSize: 'cover',
                backgroundPosition: 'center',
                filter: 'blur(20px)',
                zIndex: 0,
              }}
            />
            {/* region Misc metadata */}
             <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
              <Grid container spacing={3}>
                <Grid item xs={12} md={4} lg={3}>
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
                        image={primarySource.cover_url || defaultCover}
                        alt={novel?.title}
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
                      
                      {/* Language indicators */}
                      <Box
                        sx={{
                          position: 'absolute',
                          bottom: 8,
                          right: 8,
                          display: 'flex',
                          gap: 0.5,
                          flexDirection: 'column',
                          alignItems: 'flex-end',
                        }}
                      >
                        {Array.from(new Set(novel.sources.map(source => source.language)))
                          .filter(Boolean)
                          .map((language, index) => (
                            <Box
                              key={index}
                              sx={{
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
                              {language}
                            </Box>
                          ))}
                      </Box>
                    </Box>
                  </Zoom>
                </Grid>
                
                <Grid item xs={12} md={8} lg={9}>
                  <Typography 
                    variant="h3" 
                    gutterBottom 
                    sx={{ 
                      color: 'common.white',
                      textShadow: '0 2px 4px rgba(0,0,0,0.2)',
                      fontWeight: 700,
                    }}
                  >
                    {novel?.title}
                  </Typography>
                  
                  {/* Author and Status badges */}
                  <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                      {primarySource.authors.length > 0 && (
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
                            {primarySource.authors.join(', ')}
                          </Typography>
                        </Box>
                      )}
                      
                      {primarySource.status && (
                        <Chip
                          icon={<FlagIcon />}
                          label={primarySource.status}
                          size="medium"
                          sx={{
                            bgcolor: primarySource.status.toLowerCase() === 'completed' ? 
                              alpha('#27ae60', 0.7) : alpha('#3498db', 0.7),
                            color: 'white',
                            fontWeight: 600,
                            backdropFilter: 'blur(10px)',
                            '& .MuiChip-icon': { color: 'white' }
                          }}
                        />
                      )}
                    </Box>
                    
                    {/* Rating component with better contrasting colors */}
                    <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
                      {novelSlug && novel && (
                        <NovelRating
                          novelSlug={novelSlug}
                          initialUserRating={novel.user_rating}
                          initialAvgRating={novel.avg_rating}
                          initialRatingCount={novel.rating_count}
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
                  
                  {/* Stats badges with improved design */}
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
                    <Box 
                      sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        bgcolor: alpha('#e74c3c', 0.7),
                        backdropFilter: 'blur(10px)',
                        px: 2, 
                        py: 0.75, 
                        borderRadius: 6,
                      }}
                    >
                      <VisibilityIcon sx={{ mr: 1, color: theme.palette.common.white, fontSize: '0.9rem' }} />
                      <Typography 
                        variant="body2" 
                        sx={{ color: theme.palette.common.white, fontWeight: 700 }}
                      >
                        {novel?.total_views?.toLocaleString() || 0} Views
                      </Typography>
                    </Box>
                    
                    <Box 
                      sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        bgcolor: alpha('#2ecc71', 0.7),
                        backdropFilter: 'blur(10px)',
                        px: 2, 
                        py: 0.75, 
                        borderRadius: 6,
                      }}
                    >
                      <TrendingUpIcon sx={{ mr: 1, color: theme.palette.common.white, fontSize: '0.9rem' }} />
                      <Typography 
                        variant="body2" 
                        sx={{ color: theme.palette.common.white, fontWeight: 700 }}
                      >
                        {novel?.weekly_views?.toLocaleString() || 0} Weekly
                      </Typography>
                    </Box>
                    
                    <Box 
                      sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        bgcolor: alpha('#3498db', 0.7),
                        backdropFilter: 'blur(10px)',
                        px: 2, 
                        py: 0.75, 
                        borderRadius: 6,
                      }}
                    >
                      <BookIcon sx={{ mr: 1, color: theme.palette.common.white, fontSize: '0.9rem' }} />
                      <Typography 
                        variant="body2" 
                        sx={{ color: theme.palette.common.white, fontWeight: 700 }}
                      >
                        {novel.sources.length} {novel.sources.length > 1 ? 'Sources' : 'Source'}
                      </Typography>
                    </Box>
                    
                    <Box 
                      sx={{ 
                        display: 'flex',
                        alignItems: 'center',
                        bgcolor: alpha('#9b59b6', 0.7),
                        backdropFilter: 'blur(10px)',
                        px: 2, 
                        py: 0.75, 
                        borderRadius: 6,
                      }}
                    >
                      <MenuBookIcon sx={{ mr: 1, color: theme.palette.common.white, fontSize: '0.9rem' }} />
                      <Typography 
                        variant="body2" 
                        sx={{ color: theme.palette.common.white, fontWeight: 700 }}
                      >
                        {Math.max(...novel.sources.map(source => source.chapters_count))} Chapters
                      </Typography>
                    </Box>
                  </Box>
                  
                  {/* Genres tags with improved styling */}
                  {primarySource.genres.length > 0 && (
                    <Box sx={{ mb: 3 }}>
                      <NovelGenres 
                        genres={primarySource.genres} 
                        chipSize="small"
                        // textColor will default to a light color suitable for the hero section
                      />
                    </Box>
                  )}
                </Grid>
              </Grid>
            </Box>
          </Paper>
        )}

        {/* Novel Synopsis */}
        {primarySource && primarySource.synopsis && (
          <NovelSynopsis synopsis={primarySource.synopsis} />
        )}

        {/* Available Sources */}
        <NovelSources novel={novel!} handleSourceClick={handleSourceClick} handleVote={handleVote} votingInProgress={votingInProgress} formatDate={formatDate} />
      </Container>
    </Fade>
  );
};

export default NovelDetail;
