import React, { useState, useEffect } from 'react';
import { 
  Container, 
  Typography, 
  Box, 
  Grid, 
  Divider,
  CircularProgress,
  Button,
  useTheme,
  useMediaQuery,
  Paper
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { novelService } from '@services/api';
import { Novel } from '@models/novels_types';
import TrendingNovelCard from '@components/novels/novelcardtypes/TrendingNovelCard';
import DetailedNovelCard from '@components/novels/novelcardtypes/DetailedNovelCard';
import BaseNovelCard from '@components/novels/novelcardtypes/BaseNovelCard';
import CompactNovelCard from '@components/novels/novelcardtypes/CompactNovelCard';

const HomePage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const isTablet = useMediaQuery(theme.breakpoints.between('sm', 'md'));

  // State for different novel sections
  const [trendingNovels, setTrendingNovels] = useState<Novel[]>([]);
  const [topRatedNovels, setTopRatedNovels] = useState<Novel[]>([]);
  const [recentNovels, setRecentNovels] = useState<Novel[]>([]);
  
  // Loading states
  const [loadingTrending, setLoadingTrending] = useState<boolean>(true);
  const [loadingTopRated, setLoadingTopRated] = useState<boolean>(true);
  const [loadingRecent, setLoadingRecent] = useState<boolean>(true);

  // Error states
  const [trendingError, setTrendingError] = useState<string | null>(null);
  const [topRatedError, setTopRatedError] = useState<string | null>(null);
  const [recentError, setRecentError] = useState<string | null>(null);

  const handleNovelClick = (novelSlug: string) => {
    navigate(`/novels/${novelSlug}`);
  };

  useEffect(() => {
    // Fetch trending novels (highest weekly views)
    const fetchTrendingNovels = async () => {
      try {
        setLoadingTrending(true);
        const response = await novelService.searchNovels({
          sort_by: 'popularity',
          sort_order: 'desc',
          page_size: 10
        });
        setTrendingNovels(response.results || []);
        setTrendingError(null);
      } catch (error) {
        console.error('Error fetching trending novels:', error);
        setTrendingError('Failed to load trending novels. Please try again later.');
      } finally {
        setLoadingTrending(false);
      }
    };

    // Fetch top rated novels
    const fetchTopRatedNovels = async () => {
      try {
        setLoadingTopRated(true);
        const response = await novelService.searchNovels({
          sort_by: 'rating',
          sort_order: 'desc',
          min_rating: 4.0,
          page_size: 6
        });
        setTopRatedNovels(response.results || []);
        setTopRatedError(null);
      } catch (error) {
        console.error('Error fetching top rated novels:', error);
        setTopRatedError('Failed to load top rated novels. Please try again later.');
      } finally {
        setLoadingTopRated(false);
      }
    };

    // Fetch recently added novels
    const fetchRecentNovels = async () => {
      try {
        setLoadingRecent(true);
        const response = await novelService.searchNovels({
          sort_by: 'date_added',
          sort_order: 'desc',
          page_size: 12
        });
        setRecentNovels(response.results || []);
        setRecentError(null);
      } catch (error) {
        console.error('Error fetching recent novels:', error);
        setRecentError('Failed to load recent novels. Please try again later.');
      } finally {
        setLoadingRecent(false);
      }
    };

    fetchTrendingNovels();
    fetchTopRatedNovels();
    fetchRecentNovels();
  }, []);

  // Helper function for error display
  const renderErrorMessage = (message: string) => (
    <Paper 
      sx={{ 
        p: 3, 
        textAlign: 'center', 
        color: 'error.main',
        backgroundColor: 'error.light',
        borderRadius: 2
      }}
    >
      <Typography>{message}</Typography>
    </Paper>
  );
  
  // Helper function for loading spinner
  const renderLoading = () => (
    <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
      <CircularProgress />
    </Box>
  );

  return (
    <Container maxWidth="xl" sx={{ mt: 4, mb: 8 }}>
      <Box sx={{ mb: 6, textAlign: 'center' }}>
        <Typography variant="h3" component="h1" gutterBottom fontWeight="bold">
          Welcome to LNCrawler
        </Typography>
        <Typography variant="h6" color="text.secondary" sx={{ mb: 3 }}>
          Discover thousands of web novels, light novels and more
        </Typography>
        <Button 
          variant="contained" 
          size="large" 
          onClick={() => navigate('/novels/search')}
          sx={{ mt: 2 }}
        >
          Search Novels
        </Button>
      </Box>

      {/* Trending Novels Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h4" component="h2" fontWeight="bold">
            Trending Now
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=popularity')}>
            See All
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {trendingError ? (
          renderErrorMessage(trendingError)
        ) : loadingTrending ? (
          renderLoading()
        ) : (
          <Grid container spacing={3}>
            {trendingNovels.slice(0, 5).map((novel, index) => (
              <Grid item xs={12} sm={6} md={4} lg={2.4} key={novel.id}>
                <TrendingNovelCard 
                  novel={novel} 
                  rank={index + 1}
                  onClick={() => handleNovelClick(novel.slug)}
                />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Top Rated Novels Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h4" component="h2" fontWeight="bold">
            Top Rated
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=rating&sort_order=desc')}>
            See All
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {topRatedError ? (
          renderErrorMessage(topRatedError)
        ) : loadingTopRated ? (
          renderLoading()
        ) : (
          <Grid container spacing={3}>
            {topRatedNovels.slice(0, 6).map((novel) => (
              <Grid item xs={12} md={6} key={novel.id}>
                <DetailedNovelCard 
                  novel={novel} 
                  onClick={() => handleNovelClick(novel.slug)}
                />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Recent Additions Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h4" component="h2" fontWeight="bold">
            Recently Added
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=date_added&sort_order=desc')}>
            See All
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {recentError ? (
          renderErrorMessage(recentError)
        ) : loadingRecent ? (
          renderLoading()
        ) : (
          <Grid container spacing={3}>
            {isMobile ? (
              // Compact layout for mobile
              recentNovels.slice(0, 6).map((novel) => (
                <Grid item xs={12} key={novel.id}>
                  <CompactNovelCard 
                    novel={novel} 
                    onClick={() => handleNovelClick(novel.slug)}
                  />
                </Grid>
              ))
            ) : (
              // Regular layout for larger screens
              recentNovels.slice(0, isTablet ? 6 : 12).map((novel) => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={novel.id}>
                  <BaseNovelCard 
                    novel={novel} 
                    onClick={() => handleNovelClick(novel.slug)}
                  />
                </Grid>
              ))
            )}
          </Grid>
        )}
      </Box>
    </Container>
  );
};

export default HomePage;
