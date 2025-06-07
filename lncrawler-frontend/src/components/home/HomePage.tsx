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
import { Link } from 'react-router-dom';
import { novelService } from '@services/api';
import { Novel, NovelFromSource } from '@models/novels_types';
import { Review } from '@services/review.service';
import CompactNovelCard from '@components/common/novelcardtypes/CompactNovelCard';
import FeaturedNovelCard from '@components/common/novelcardtypes/FeaturedNovelCard';
import ChapterCard from '@components/common/novelcardtypes/ChapterCard';
import NovelItemCard from '@components/common/novelcardtypes/NovelItemCard';
import TrendingNovelCard from '@components/common/novelcardtypes/TrendingNovelCard';
import OverviewReviewsSection from '@components/common/reviews/OverviewReviewsSection';

const HomePage: React.FC = () => {
  const theme = useTheme();
  
  // State for different novel sections
  const [homeData, setHomeData] = useState<{
    top_novels: Novel[];
    trending_novels: Novel[];
    top_rated_novels: Novel[];
    recently_updated: NovelFromSource[];
    featured_novel: any;
    recent_reviews: Review[];
  } | null>(null);
  
  // Loading and error states
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Rankings tab state
  const [rankingTab, setRankingTab] = useState<number>(1);

  const handleRankingTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setRankingTab(newValue);
  };

  useEffect(() => {
    const fetchHomeData = async () => {
      try {
        setLoading(true);
        const data = await novelService.getHomePageData();
        setHomeData(data);
        setError(null);
      } catch (error) {
        console.error('Error fetching home page data:', error);
        setError('Failed to load home page data. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchHomeData();
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

  // Show global error if API call failed
  if (error) {
    return (
      <Container maxWidth="xl">
        <Box sx={{ my: 4 }}>
          {renderErrorMessage(error)}
        </Box>
      </Container>
    );
  }
  
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
          <Button component={Link} to="/novels/search?sort_by=trending&sort_order=desc" variant="text">
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loading ? (
          <Grid container spacing={3}>
            {[...Array(4)].map((_, index) => (
              <Grid size={{ xs: 6, sm: 3 }} key={`trending-skeleton-${index}`}>
                <TrendingNovelCard novel={{} as Novel} isLoading={true} rank={index + 1} />
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={3}>
            {homeData?.trending_novels.slice(0, 4).map((novel, index) => (
              <Grid size={{ xs: 6, sm: 3 }} key={novel.id}>
                <TrendingNovelCard 
                  novel={novel} 
                  to={`/novels/${novel.slug}`}
                  rank={index + 1}
                />
              </Grid>
            )) || []}
          </Grid>
        )}
      </Box>

      {/* Best of All Time Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Best of all time
          </Typography>
          <Button component={Link} to="/novels/search?sort_by=popularity&sort_order=desc" variant="text">
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loading ? (
          <Grid container spacing={2}>
            {[...Array(12)].map((_, index) => (
              <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={`top-skeleton-${index}`}>
                <NovelItemCard novel={{} as Novel} isLoading={true} rank={index + 1} onClick={() => {}} />
              </Grid>
            ))}
          </Grid>
        ) : (
          <Grid container spacing={2}>
            {homeData?.top_novels.slice(0, 12).map((novel, rank) => (
              <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={novel.id}>
                <NovelItemCard 
                  novel={novel} 
                  to={`/novels/${novel.slug}`}
                  rank={rank + 1}
                />
              </Grid>
            )) || []}
          </Grid>
        )}
      </Box>

      {/* Ranking Section with Tabs */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Ranking
          </Typography>
          <Button component={Link} to="/novels/search" variant="text">
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
          {loading ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`most-read-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showClicks onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : (
            <Grid container spacing={1}>
              {homeData?.top_novels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    to={`/novels/${novel.slug}`}
                    showClicks
                  />
                </Grid>
              )) || []}
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
          {loading ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`new-trends-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showTrends onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : (
            <Grid container spacing={1}>
              {homeData?.trending_novels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    to={`/novels/${novel.slug}`}
                    showTrends
                  />
                </Grid>
              )) || []}
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
          {loading ? (
            <Grid container spacing={1}>
              {[...Array(12)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`user-rated-skeleton-${index}`}>
                  <CompactNovelCard novel={{} as Novel} isLoading={true} showRating onClick={() => {}} />
                </Grid>
              ))}
            </Grid>
          ) : (
            <Grid container spacing={1}>
              {homeData?.top_rated_novels.slice(0, 12).map((novel) => (
                <Grid size={{ xs: 6, sm: 4, md: 3 }} key={novel.id}>
                  <CompactNovelCard
                    novel={novel}
                    to={`/novels/${novel.slug}`}
                    showRating
                  />
                </Grid>
              )) || []}
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
          <Button component={Link} to="/novels/search?sort_by=popularity&sort_order=desc" variant="text">
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loading ? (
          <FeaturedNovelCard source={{} as NovelFromSource} isLoading={true} onClick={() => {}} />
        ) : homeData?.featured_novel ? (
          <FeaturedNovelCard 
            source={homeData.featured_novel.novel.prefered_source}
            to={homeData.featured_novel.novel.prefered_source?.novel_slug && homeData.featured_novel.novel.prefered_source?.source_slug ? 
              `/novels/${homeData.featured_novel.novel.prefered_source.novel_slug}/${homeData.featured_novel.novel.prefered_source.source_slug}` : 
              homeData.featured_novel.novel.prefered_source?.novel_slug ? 
                `/novels/${homeData.featured_novel.novel.prefered_source.novel_slug}` : undefined}
          />
        ) : (
          <Typography variant="body1" align="center">No featured novel available</Typography>
        )}
      </Box>

      {/* Recent Reviews Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Latest Reviews
          </Typography>
          <Button component={Link} to="/reviews" variant="text">
            View More
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        <OverviewReviewsSection 
          reviews={homeData?.recent_reviews} 
          isLoading={loading}
          maxItems={4}
        />
      </Box>

      {/* Recently Added Chapters Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" fontWeight="bold">
            Recently Updated Novels
          </Typography>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {!loading && homeData && (
          <Grid container spacing={2}>
            {homeData.recently_updated.slice(0, 12).map((source) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={source.id}>
                <ChapterCard
                  source={source}
                  to={source.source_slug ? `/novels/${source.novel_slug}/${source.source_slug}` : undefined}
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
