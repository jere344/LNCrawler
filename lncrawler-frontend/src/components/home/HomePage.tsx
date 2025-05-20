import React, { useState, useEffect } from 'react';
import { 
  Container, 
  Typography, 
  Box, 
  Divider,
  Button,
  useTheme,
  Paper,
  Tabs,
  Tab,
  Grid2 as Grid
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { novelService } from '@services/api';
import { Novel, NovelFromSource } from '@models/novels_types';
import CompactNovelCard from '@components/common/novelcardtypes/CompactNovelCard';
import FeaturedNovelCard from '@components/common/novelcardtypes/FeaturedNovelCard';
import ChapterCard from '@components/common/novelcardtypes/ChapterCard';
import NovelItemCard from '@components/common/novelcardtypes/NovelItemCard';
import TrendingNovelCard from '@components/common/novelcardtypes/TrendingNovelCard';

const HomePage: React.FC = () => {
  const theme = useTheme();
  const navigate = useNavigate();
  
  // State for different novel sections
  const [topNovels, setTopNovels] = useState<Novel[]>([]);
  const [trendingNovels, setTrendingNovels] = useState<Novel[]>([]);
  const [topRatedNovels, setTopRatedNovels] = useState<Novel[]>([]);
  const [recentChapters, setRecentChapters] = useState<NovelFromSource[]>([]);
  const [featuredNovel, setFeaturedNovel] = useState<NovelFromSource | null>(null);
  
  // Loading states
  const [loadingTop, setLoadingTop] = useState<boolean>(true);
  const [loadingTrending, setLoadingTrending] = useState<boolean>(true);
  const [loadingTopRated, setLoadingTopRated] = useState<boolean>(true);
  const [loadingRecent, setLoadingRecent] = useState<boolean>(true);
  const [loadingFeatured, setLoadingFeatured] = useState<boolean>(true);

  // Error states
  const [topError, setTopError] = useState<string | null>(null);
  const [trendingError, setTrendingError] = useState<string | null>(null);
  const [topRatedError, setTopRatedError] = useState<string | null>(null);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [featuredError, setFeaturedError] = useState<string | null>(null);

  // Rankings tab state
  const [rankingTab, setRankingTab] = useState<number>(1);

  const handleNovelClick = (novelSlug: string, sourceSlug?: string) => {
    if (sourceSlug) {
      navigate(`/novels/${novelSlug}/${sourceSlug}`);
    } else {
      navigate(`/novels/${novelSlug}`);
    }
  };

  const handleRankingTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setRankingTab(newValue);
  };

  useEffect(() => {
    // Fetch top novels (best of all time)
    const fetchTopNovels = async () => {
      try {
        setLoadingTop(true);
        const response = await novelService.searchNovels({
          sort_by: 'popularity',
          sort_order: 'desc',
          page_size: 12
        });
        setTopNovels(response.results || []);
        setTopError(null);
      } catch (error) {
        console.error('Error fetching top novels:', error);
        setTopError('Failed to load top novels. Please try again later.');
      } finally {
        setLoadingTop(false);
      }
    };

    // Fetch trending novels (weekly views)
    const fetchTrendingNovels = async () => {
      try {
        setLoadingTrending(true);
        const response = await novelService.searchNovels({
          sort_by: 'trending',
          sort_order: 'desc',
          page_size: 12
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
          page_size: 12
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

    // Fetch recently updated chapters
    const fetchRecentChapters = async () => {
      try {
        setLoadingRecent(true);
        const response = await novelService.searchNovels({
          sort_by: 'last_updated',
          sort_order: 'desc',
          page_size: 12
        });
        setRecentChapters(response.results.map((novel: { prefered_source: any; }) => novel.prefered_source).filter(Boolean) as NovelFromSource[]);
        setRecentError(null);
      } catch (error) {
        console.error('Error fetching recent chapters:', error);
        setRecentError('Failed to load recent chapters. Please try again later.');
      } finally {
        setLoadingRecent(false);
      }
    };

    // Fetch featured novel
    const fetchFeaturedNovel = async () => {
      try {
        setLoadingFeatured(true);
        const response = await novelService.getRandomFeaturedNovel();
        if (response.novel) {
          setFeaturedNovel(response.novel.prefered_source);
        }
        setFeaturedError(null);
      } catch (error) {
        console.error('Error fetching featured novel:', error);
        setFeaturedError('Failed to load featured novel. Please try again later.');
      } finally {
        setLoadingFeatured(false);
      }
    };

    fetchTopNovels();
    fetchTrendingNovels();
    fetchTopRatedNovels();
    fetchRecentChapters();
    fetchFeaturedNovel();
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
  
  return (
    <Container maxWidth="xl">
      <Box sx={{ my: 2 }}>
        <Typography variant="h1" component="h1" gutterBottom sx={{ 
          fontWeight: 'bold',
          textAlign: 'center',
          mb: 3
        }}>
          LNCrawler
        </Typography>
        <Box sx={{ 
          backgroundColor: theme.palette.background.paper,
          padding: 2,
          mx:0,
          borderRadius: 2,
          mb: 4
        }}>
          <Typography paragraph>
            Looking for a great place to read Light Novels?
          </Typography>
          <Typography paragraph>
            LNCrawler is a very special platform where you can read the translated versions of world famous Asian light novels from hundreds of differents sources in multiple languages. 
          </Typography>
          <Typography>
            If you can't find your novel here, you can instantly and automatically add it to our database from the Add Novel page.
          </Typography>
        </Box>
      </Box>

      {/* Weekly Trending Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            This Week's Hottest Novels 🔥
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=weekly_views&sort_order=desc')}>
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loadingTrending ? (
          <Grid container spacing={3}>
            {[...Array(4)].map((_, index) => (
              <Grid size={{ xs: 6, sm: 3 }} key={`trending-skeleton-${index}`}>
                <TrendingNovelCard novel={{} as Novel} isLoading={true} rank={index + 1} />
              </Grid>
            ))}
          </Grid>
        ) : trendingError ? (
          renderErrorMessage(trendingError)
        ) : (
          <Grid container spacing={3}>
            {trendingNovels.slice(0, 4).map((novel, index) => (
              <Grid size={{ xs: 6, sm: 3 }} key={novel.id}>
                <TrendingNovelCard 
                  novel={novel} 
                  onClick={() => handleNovelClick(novel.slug)}
                  rank={index + 1}
                />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Best of All Time Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Best of all time
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=popularity&sort_order=desc')}>
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loadingTop ? (
          <Grid container spacing={2}>
            {[...Array(12)].map((_, index) => (
              <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={`top-skeleton-${index}`}>
                <NovelItemCard novel={{} as Novel} isLoading={true} rank={index + 1} onClick={() => {}} />
              </Grid>
            ))}
          </Grid>
        ) : topError ? (
          renderErrorMessage(topError)
        ) : (
          <Grid container spacing={2}>
            {topNovels.slice(0, 12).map((novel, rank) => (
              <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={novel.id}>
                <NovelItemCard 
                  novel={novel} 
                  onClick={() => handleNovelClick(novel.slug)}
                  rank={rank + 1}
                />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>

      {/* Ranking Section with Tabs */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Ranking
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search')}>
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 1 }} />

        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={rankingTab} onChange={handleRankingTabChange} aria-label="novel rankings">
            <Tab label="Most Read" id="tab-most-read" aria-controls="tabpanel-most-read" />
            <Tab label="New Trends" id="tab-new-trends" aria-controls="tabpanel-new-trends" />
            <Tab label="User Rated" id="tab-user-rated" aria-controls="tabpanel-user-rated" />
          </Tabs>
        </Box>
        
        {/* Most Read Tab Panel */}
        <Box
          role="tabpanel"
          hidden={rankingTab !== 0}
          id="tabpanel-most-read"
          aria-labelledby="tab-most-read"
          sx={{ py: 3 }}
        >
          {loadingTop ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`most-read-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showClicks onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : topError ? (
            renderErrorMessage(topError)
          ) : (
            <Grid container spacing={1}>
              {topNovels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    onClick={() => handleNovelClick(novel.slug)}
                    showClicks
                  />
                </Grid>
              ))}
            </Grid>
          )}
        </Box>

        {/* New Trends Tab Panel */}
        <Box
          role="tabpanel"
          hidden={rankingTab !== 1}
          id="tabpanel-new-trends"
          aria-labelledby="tab-new-trends"
          sx={{ py: 3 }}
        >
          {loadingTrending ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`new-trends-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showTrends onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : trendingError ? (
            renderErrorMessage(trendingError)
          ) : (
            <Grid container spacing={1}>
              {trendingNovels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    onClick={() => handleNovelClick(novel.slug)}
                    showTrends
                  />
                </Grid>
              ))}
            </Grid>
          )}
        </Box>

        {/* User Rated Tab Panel */}
        <Box
          role="tabpanel"
          hidden={rankingTab !== 2}
          id="tabpanel-user-rated"
          aria-labelledby="tab-user-rated"
          sx={{ py: 3 }}
        >
          {loadingTopRated ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`user-rated-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showRating onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : topRatedError ? (
            renderErrorMessage(topRatedError)
          ) : (
            <Grid container spacing={1}>
              {topRatedNovels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    onClick={() => handleNovelClick(novel.slug)}
                    showRating
                  />
                </Grid>
              ))}
            </Grid>
          )}
        </Box>
      </Box>

      {/* Featured Novel Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Featured
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=popularity&sort_order=desc')}>
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loadingFeatured ? (
          <FeaturedNovelCard source={{} as NovelFromSource} isLoading={true} onClick={() => {}} />
        ) : featuredError ? (
          renderErrorMessage(featuredError)
        ) : featuredNovel ? (
          <FeaturedNovelCard 
            source={featuredNovel}
            onClick={() => {
              if (featuredNovel.novel_slug && featuredNovel.source_slug) {
                handleNovelClick(featuredNovel.novel_slug, featuredNovel.source_slug);
              }
            }}
          />
        ) : (
          <Typography variant="body1" align="center">No featured novel available</Typography>
        )}
      </Box>

      {/* Recently Added Chapters Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Recently Added Chapters
          </Typography>
          <Button variant="text" onClick={() => navigate('/novels/search?sort_by=date_added&sort_order=desc')}>
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loadingRecent ? (
          <Grid container spacing={2}>
            {[...Array(12)].map((_, index) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={`recent-skeleton-${index}`}>
                <ChapterCard source={{} as NovelFromSource} isLoading={true} onClick={() => {}} />
              </Grid>
            ))}
          </Grid>
        ) : recentError ? (
          renderErrorMessage(recentError)
        ) : (
          <Grid container spacing={2}>
            {recentChapters.slice(0, 12).map((source) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={source.id}>
                <ChapterCard
                  source={source}
                  onClick={() => {
                    if (source.novel_slug) {
                      handleNovelClick(source.novel_slug);
                    }
                  }}
                />
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Container>
  );
};

export default HomePage;
