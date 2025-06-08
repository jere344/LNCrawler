import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import PersonIcon from '@mui/icons-material/Person';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import {
  Container,
  Typography,
  Box,
  Paper,
  CardMedia,
  Button,
  useTheme,
  alpha,
  Skeleton,
  Zoom,
  Grid2 as Grid,
  Snackbar,
  Alert,
  Tooltip,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import defaultCover from '@assets/default-cover.jpg';
import { NovelDetail as INovelDetail } from '@models/novels_types';
import NovelSources from './NovelSources.tsx';
import NovelSynopsis from './common/NovelSynopsis.tsx';
import NovelRating from './common/NovelRating.tsx';
import NovelTags from './common/NovelTags';
import BreadcrumbNav from '../common/BreadcrumbNav';
import { getChapterNameWithNumber, languageCodeToFlag, languageCodeToName } from '@utils/Misc.tsx';
import ActionButton from '../common/ActionButton';
import NovelRecommendation from '../common/NovelRecommendation';
import SectionContainer from '@components/common/SectionContainer.tsx';
import Reviews from './Reviews.tsx';
import { useAuth } from '@context/AuthContext';
import BookmarkButton from '@components/common/BookmarkButton';
import CompactAddToListButton from '@components/readinglist/CompactAddToListButton';
import ReadingListCard from '../readinglist/ReadingListCard';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';

const DEFAULT_OG_IMAGE = '/og-image.jpg';

const NovelDetail = () => {
  const { isAuthenticated } = useAuth();
  const { novelSlug } = useParams<{ novelSlug: string }>();
  const theme = useTheme();
  const [novel, setNovel] = useState<INovelDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [snackbar, setSnackbar] = useState<{
    open: boolean;
    message: string;
    severity: 'success' | 'error';
  }>({
    open: false,
    message: '',
    severity: 'success',
  });

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
  const continue_chapter = novel?.reading_history?.next_chapter || novel?.reading_history?.last_read_chapter;

  const handleCloseSnackbar = () => {
    setSnackbar((prev) => ({
      ...prev,
      open: false,
    }));
  };

  const pageUrl = window.location.href;
  const siteName = "LNCrawler";

  const metaTitle = novel 
    ? `${novel.title} - Read Light Novel Online | ${siteName}`
    : `Loading Novel | ${siteName}`;
  const metaDescription = novel
    ? `Discover ${novel.title}, an Asian light novel. ${novel.prefered_source?.synopsis ? `Synopsis: ${novel.prefered_source.synopsis.substring(0, 100).replace(/<[^>]+>/g, '')}... ` : ''}Read reviews, find sources, and dive into the story on ${siteName}.`
    : `Loading novel details. Your source for Asian light novels and web novels - ${siteName}.`;
  const metaKeywordsList = novel
    ? [novel.title, ...(novel.prefered_source?.tags || []), ...(novel.prefered_source?.authors || []), "light novel", "web novel", "read online", "Asian novel"]
    : ["light novel", "web novel", "read online", "Asian novel"];
  const metaKeywords = [...new Set(metaKeywordsList.filter(Boolean))].join(', ');
  const ogImage = novel?.prefered_source?.overview_url || novel?.prefered_source?.cover_url || DEFAULT_OG_IMAGE;

  if (loading) {
    return (
      <Container maxWidth="lg" sx={{ pb: 6 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
          <Skeleton variant="rounded" width={150} height={36} sx={{ borderRadius: '20px' }} />
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
                <Skeleton 
                  variant="rectangular" 
                  sx={{ 
                    width: '100%', 
                    paddingTop: '150%', 
                    borderRadius: 2,
                    transform: 'none'
                  }} 
                />
              </Grid>
              
              <Grid size={{ xs: 12, md: 8, lg: 9 }}>
                <Skeleton variant="text" height={60} width="80%" sx={{ mb: 1 }} />
                
                <Box sx={{ display: 'flex', gap: 2, mb: 2 }}>
                  <Skeleton variant="rounded" width={120} height={32} />
                  <Skeleton variant="rounded" width={100} height={32} />
                </Box>
                
                <Skeleton variant="rounded" width={180} height={32} sx={{ mb: 2 }} />
                
                <Box sx={{ height: '2px', mb: 2.5, mt: 0.5 }}>
                  <Skeleton variant="text" height={2} width="60%" />
                </Box>
                
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
                  {[1, 2, 3, 4].map((item) => (
                    <Skeleton key={item} variant="rounded" width={100} height={32} />
                  ))}
                </Box>
                
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mb: 3 }}>
                  {[1, 2, 3, 4, 5].map((item) => (
                    <Skeleton key={item} variant="rounded" width={80} height={24} />
                  ))}
                </Box>
                
                <Skeleton variant="rounded" width={220} height={48} />
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Skeleton for Synopsis */}
        <Paper sx={{ p: 3, mb: 4, borderRadius: 2 }}>
          <Skeleton variant="text" width={150} height={32} sx={{ mb: 2 }} />
          <Skeleton variant="text" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="text" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="text" height={20} sx={{ mb: 1 }} />
          <Skeleton variant="text" height={20} width="80%" />
        </Paper>
      </Container>
    );
  }

  if (error || !novel) {
    return (
      <Container maxWidth="lg">
        <Button startIcon={<ArrowBackIcon />} component={Link} to="/" sx={{ mt: 2 }}>
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
            component={Link} to="/"
            sx={{ mt: 2 }}
          >
            Return to Home
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ pb: 6 }}>
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
      {(novel?.prefered_source?.authors?.length || 0) > 0 && <meta property="book:author" content={novel.prefered_source?.authors.join(', ')} />}
      {(novel?.prefered_source?.tags?.length || 0 > 0) && novel.prefered_source?.tags.map(tag => <meta property="book:tag" content={tag} key={tag} />)}

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={metaTitle} />
      <meta name="twitter:description" content={metaDescription} />
      <meta name="twitter:image" content={ogImage} />

      {!loading && novel && (
        <BreadcrumbNav
          items={[
            {
              label: novel.title,
              icon: <BookIcon fontSize="inherit" />
            }
          ]}
        />
      )}
      
      <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
        <Button 
          startIcon={<ArrowBackIcon />} 
          component={Link} to="/"
          variant="outlined"
          sx={{ 
            borderRadius: '20px',
            px: 2,
          }}
        >
          Back to Novels
        </Button>
      </Box>

      {novel.prefered_source && (
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
              backgroundImage: `url(${novel.prefered_source.cover_url || defaultCover})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(20px)',
              zIndex: 0,
            }}
          />
          {/* region Misc metadata */}
            <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 5, lg: 4 }}>
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
                      image={novel.prefered_source.cover_url || defaultCover}
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
                    
                    {/* Language flags */}
                    <Box
                      sx={{
                        position: 'absolute',
                        top: 0,
                        right: 0,
                        display: 'flex',
                        gap: 0.5,
                        boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
                        border: '1px solid rgb(0, 0, 0)',
                        borderRadius: 1,
                        alignItems: 'center',
                      }}
                    >
                      {Array.from(new Set(novel.sources.map(source => source.language)))
                        .filter(Boolean)
                        .map((lang, index) => (
                          <Tooltip key={index} title={languageCodeToName(lang)}>
                            <img 
                              src={`/flags/${languageCodeToFlag(lang)}.svg`} 
                              alt={languageCodeToName(lang)}
                              style={{ 
                                width: '30px',
                                height: '20px',
                                objectFit: 'cover',
                                borderRadius: '2px',
                              }}
                            />
                          </Tooltip>
                        ))}
                      {Array.from(new Set(novel.sources.map(source => source.language))).length === 0 && (
                        <Tooltip title="Unknown language">
                          <Typography
                            sx={{
                              fontSize: '0.8rem',
                              color: '#fff',
                              fontWeight: 'bold',
                              lineHeight: 1,
                            }}
                          >
                            ?
                          </Typography>
                        </Tooltip>
                      )}
                    </Box>
                    
                    {/* Add bookmark and reading list buttons */}
                    {isAuthenticated && novelSlug && (
                      <>
                        <BookmarkButton 
                          isBookmarked={!!novel.is_bookmarked} 
                          slug={novelSlug}
                          customSx={{
                            position: 'absolute',
                            right: 8,
                            bottom: 8,
                            zIndex: 10
                          }}
                        />
                        <CompactAddToListButton
                          novelId={novel.id}
                          novelTitle={novel.title}
                          customSx={{
                            position: 'absolute',
                            right: 52,
                            bottom: 8,
                            zIndex: 10
                          }}
                        />
                      </>
                    )}
                  </Box>
                </Zoom>
              </Grid>
              
              <Grid size={{ xs: 12, md: 7, lg: 8 }}>
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
                    {novel.prefered_source.authors.length > 0 && (
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
                          {novel.prefered_source.authors.join(', ')}
                        </Typography>
                      </Box>
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
                      {Math.max(...novel.sources.map(source => source.latest_available_chapter?.chapter_id || 0))} Chapters
                    </Typography>
                  </Box>
                </Box>

                <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                  <Box sx={{ 
                    width: '100%', 
                    display: 'flex', 
                    flexDirection: { xs: 'column', sm: 'row' }, 
                    gap: 1,
                    mb: 1
                  }}></Box>

                  {continue_chapter && novel.prefered_source && (
                    <ActionButton
                      title="Continue Reading"
                      subtitle={getChapterNameWithNumber(continue_chapter.title, continue_chapter.chapter_id)}
                      startIcon={<BookmarkIcon />}
                      backgroundIcon={<BookIcon />}
                      color="warning"
                      to={`/novels/${novelSlug}/${novel.prefered_source.source_slug}/chapter/${continue_chapter.chapter_id}`}
                      tooltip={`Continue from chapter ${continue_chapter.chapter_id}`}
                      tooltipPlacement="top"
                    />
                  )}
                  
                  <ActionButton
                    title="Start Reading"
                    subtitle="From Chapter 1"
                    startIcon={<PlayArrowIcon />}
                    backgroundIcon={<BookIcon />}
                    color="success"
                    to={`/novels/${novelSlug}/${novel.prefered_source.source_slug}/chapter/1`}
                    disabled={novel.prefered_source?.latest_available_chapter?.chapter_id === 0}
                    tooltip="Start reading from chapter 1"
                    tooltipPlacement="top"
                  />

                  <ActionButton
                    title="Go to Prefered Source"
                    subtitle={novel.prefered_source.source_name}
                    startIcon={<LanguageIcon />}
                    backgroundIcon={<LanguageIcon />}
                    color="primary"
                    to={`/novels/${novelSlug}/${novel.prefered_source.source_slug}`}
                    disabled={!novel.prefered_source}
                    tooltip="Our novels are sourced from various sites with different translations, languages, and updates. Click to go to the prefered source for this novel."
                    tooltipPlacement="top"
                  />
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Paper>
      )}

        <SectionContainer title="Tags" icon={<BookmarkIcon />}>
        {/* we merge every novel.sources[].tags[] removing duplicates */}
          <NovelTags 
            tags={novel.sources.reduce((acc: string[], source) => {
              if (source.tags) {
                acc.push(...source.tags);
              }
              return acc;
            }, [])}
            chipSize="medium"
          />
        </SectionContainer>

      {/* Novel Synopsis */}
      {novel.prefered_source && novel.prefered_source.synopsis && (
        <SectionContainer title="Synopsis" icon={<BookmarkIcon />}>
          <NovelSynopsis synopsis={novel.prefered_source.synopsis} />
        </SectionContainer>
      )}

      {/* Reviews Section */}
      {novelSlug && (
        <SectionContainer title="Reviews" icon={<MenuBookIcon />}>
          <Reviews novelSlug={novelSlug} showAddReview={true} />
        </SectionContainer>
      )}

      {/* Reading Lists Section */}
      {novel.reading_lists && novel.reading_lists.length > 0 && (
        <SectionContainer title="In Reading Lists" icon={<PlaylistAddIcon />}>
          <Grid container spacing={2}>
            {novel.reading_lists.map((list) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={list.id}>
                <ReadingListCard list={list} />
              </Grid>
            ))}
          </Grid>
        </SectionContainer>
      )}

      {/* Similar Novels / Recommendations */}
      {novel.similar_novels && novel.similar_novels.length > 0 && (
        <SectionContainer title="Similar Novels" icon={<TrendingUpIcon />}>
          <NovelRecommendation similarNovels={novel.similar_novels} />
        </SectionContainer>
      )}

      {/* Available Sources */}
      {novel && (
        <SectionContainer title="Available Sources" icon={<LanguageIcon />}>
          <NovelSources 
            novel={{...novel, slug: novelSlug}} 
          />
        </SectionContainer>
      )}

      {/* Keep the Snackbar for other potential notifications */}
      <Snackbar 
        open={snackbar.open} 
        autoHideDuration={3000} 
        onClose={handleCloseSnackbar}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
      >
        <Alert 
          onClose={handleCloseSnackbar} 
          severity={snackbar.severity} 
          variant="filled"
          elevation={6}
          sx={{ width: '100%' }}
        >
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Container>
  );
};

export default NovelDetail;
