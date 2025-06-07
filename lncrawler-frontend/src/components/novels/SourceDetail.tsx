import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Paper,
  Button,
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
import NovelTags from './common/NovelTags';
import NovelUpdateButton from './common/NovelUpdateButton';
import BreadcrumbNav from '../common/BreadcrumbNav';
import BookIcon from '@mui/icons-material/Book';
import { getChapterNameWithNumber, languageCodeToFlag, languageCodeToName } from '@utils/Misc.tsx';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import CollectionsIcon from '@mui/icons-material/Collections';
import ActionButton from '../common/ActionButton';
import SectionContainer from '@components/common/SectionContainer.tsx';

const DEFAULT_OG_IMAGE = '/og-image.jpg';

const SourceDetail = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
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

  const continue_chapter = source?.reading_history?.next_chapter || source?.reading_history?.last_read_chapter;

  // Format date to readable format
  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    }).format(date);
  };

  const pageUrl = window.location.href;
  const siteName = "LNCrawler";

  const metaTitle = source 
    ? `${source.title} (${source.source_name}) - Read on ${siteName}`
    : `Loading Novel Source | ${siteName}`;
  const metaDescription = source
    ? `Read ${source.title} from ${source.source_name}. Synopsis: ${source.synopsis ? source.synopsis.substring(0, 120).replace(/<[^>]+>/g, '') + '...' : `Discover this light novel on ${siteName}.`} Chapters, ratings, and more.`
    : `Loading details for this novel source on ${siteName}.`;
  const metaKeywordsList = source
    ? [source.title, source.source_name, ...source.tags, ...source.authors, "read light novel", "web novel"]
    : ["light novel", "web novel", "source details"];
  const metaKeywords = [...new Set(metaKeywordsList.filter(Boolean))].join(', '); // Unique keywords
  const ogImage = source?.overview_url || source?.cover_url || DEFAULT_OG_IMAGE;

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

        {/* Tags Section Skeleton */}
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
        <Button startIcon={<ArrowBackIcon />} component={Link} to={`/novels/${novelSlug}`} variant="outlined" sx={{ mt: 2 }}>
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
            component={Link}
            to={`/novels/${novelSlug}`}
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
        <title>{metaTitle}</title>
        <meta name="description" content={metaDescription} />
        <meta name="keywords" content={metaKeywords} />
        <link rel="canonical" href={pageUrl} />

        <meta property="og:title" content={metaTitle} />
        <meta property="og:description" content={metaDescription} />
        <meta property="og:type" content="book" />
        <meta property="og:url" content={pageUrl} />
        <meta property="og:site_name" content={siteName} />
        <meta property="og:image" content={ogImage} />
        {source?.authors?.length > 0 && <meta property="book:author" content={source.authors.join(', ')} />}
        {source?.tags?.length > 0 && source.tags.map(tag => <meta property="book:tag" content={tag} key={tag} />)}
        
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content={metaTitle} />
        <meta name="twitter:description" content={metaDescription} />
        <meta name="twitter:image" content={ogImage} />

        {!loading && source && (
          <BreadcrumbNav
            items={[
              {
                label: source.novel_title,
                link: `/novels/${novelSlug}`,
                icon: <BookIcon fontSize="inherit" />
              },
              {
                label: source.source_name,
                icon: <LanguageIcon fontSize="inherit" />
              }
            ]}
          />
        )}
        
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
          <Button 
            startIcon={<ArrowBackIcon />}
            component={Link}
            to={`/novels/${novelSlug}`}
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
              <Grid size={{ xs: 12, md: 6, lg: 5 }}>
                <Zoom in={true} timeout={500}>
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
                        top: 8,
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
                      <img 
                        src={`/flags/${languageCodeToFlag(source.language)}.svg`} 
                        alt={languageCodeToName(source.language)}
                        style={{ 
                          width: '20px',
                          height: '15px',
                          objectFit: 'cover',
                          borderRadius: '2px',
                        }}
                      />
                      {source.language}
                    </Box>
                  </Box>
                </Zoom>
              </Grid>
              
              <Grid size={{ xs: 12, md: 6, lg: 7 }}>
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
                  {source.source_url.startsWith('http') && (
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
                  )}
                </Typography>
                
                {/* Author badges */}
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
                  </Box>
                  
                  {/* Novel rating component  */}
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
                
                {/* Source stats */}
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
                          {source.latest_available_chapter?.chapter_id || 0}
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
                
                {/* Source vote actions*/}
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
                  {continue_chapter && (
                    <ActionButton
                      title="Continue Reading"
                      subtitle={getChapterNameWithNumber(
                        continue_chapter.title,
                        continue_chapter.chapter_id
                      )}
                      startIcon={<BookmarkIcon />}
                      color="warning"
                      // onClick={handleContinueReading}
                      to={`/novels/${novelSlug}/${sourceSlug}/chapter/${continue_chapter.chapter_id}`}
                      tooltip={`Continue from chapter ${continue_chapter.chapter_id}`}
                      sx={{ mb: 1 }}
                    />
                  )}
                  <Box sx={{ 
                    width: '100%', 
                    display: 'flex', 
                    flexDirection: { xs: 'column', sm: 'row' }, 
                    gap: 1,
                    mb: 1
                  }}>
                    <ActionButton
                      title="Chapter List"
                      subtitle={`View all ${source?.chapters_count} chapters`}
                      startIcon={<ViewListIcon />}
                      backgroundIcon={<ListAltIcon />}
                      color="info"
                      to={`/novels/${novelSlug}/${sourceSlug}/chapterlist`}
                      disabled={source?.latest_available_chapter?.chapter_id === 0}
                      tooltip="Browse all chapters"
                    />

                    <ActionButton
                      title="Image Gallery"
                      subtitle="Browse all images"
                      startIcon={<CollectionsIcon />}
                      color="secondary"
                      to={`/novels/${novelSlug}/${sourceSlug}/gallery`}
                      tooltip="View image gallery"
                    />

                    <ActionButton
                      title="Start Reading"
                      subtitle="From Chapter 1"
                      startIcon={<PlayArrowIcon />}
                      color="success"
                      to={`/novels/${novelSlug}/${sourceSlug}/chapter/1`}
                      disabled={source?.latest_available_chapter?.chapter_id === 0}
                      tooltip="Start reading from chapter 1"
                    />

                    <ActionButton
                      title="Latest Chapter"
                      subtitle={`Chapter ${source?.latest_available_chapter?.chapter_id || 0}`}
                      startIcon={<SkipNextIcon />}
                      color="primary"
                      to={`/novels/${novelSlug}/${sourceSlug}/chapter/${source?.latest_available_chapter?.chapter_id || 0}`}
                      disabled={!source?.latest_available_chapter}
                      tooltip="Jump to the most recent chapter"
                    />
                  </Box>
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Update Button Section */}
        {source && source.source_url && source.source_url.startsWith('http') && (
          <Paper 
            sx={{ 
              p: { xs: 2, md: 3 }, 
              mb: 4,
              borderRadius: 3,
            }}
          >
            <NovelUpdateButton 
              sourceUrl={source.source_url} 
              novelTitle={source.title} 
            />
          </Paper>
        )}

        {source.tags.length > 0 && (
          <SectionContainer title="Tags" icon={<BookmarkIcon />}>
            <NovelTags 
              tags={source.tags} 
              chipSize="medium" 
            />
          </SectionContainer>
        )}
        
        {source.synopsis && (
          <SectionContainer title="Synopsis" icon={<BookmarkIcon />}>
            <NovelSynopsis synopsis={source.synopsis} />
          </SectionContainer>
        )}

        
        {novelSlug && (
          <SectionContainer title="Comments" icon={<CommentIcon />}>
            <CommentSection 
              novelSlug={novelSlug}
              title="Novel Comments" 
            />
          </SectionContainer>
        )}
    </Container>
  );
};

export default SourceDetail;
