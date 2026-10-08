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
  Grid as Grid
} from '@mui/material';
import { Link } from 'react-router-dom';
import { novelService } from '@services/api';
import { Novel, NovelFromSource, NovelFeaturedResponse } from '@models/novels_types';
import { Review } from '@services/review.service';
import CompactNovelCard from '@components/common/novelcardtypes/CompactNovelCard';
import FeaturedNovelCard from '@components/common/novelcardtypes/FeaturedNovelCard';
import ChapterCard from '@components/common/novelcardtypes/ChapterCard';
import NovelItemCard from '@components/common/novelcardtypes/NovelItemCard';
import TrendingNovelCard from '@components/common/novelcardtypes/TrendingNovelCard';
import OverviewReviewsSection from '@components/common/reviews/OverviewReviewsSection';
import NovelRecommendation from '@components/common/NovelRecommendation';
import { getNovelSourceLink, getSourceLink } from '@utils/Misc';
import { useLanguage } from '@context/LanguageContext';
import { useTranslation } from 'react-i18next';

const HomePage: React.FC = () => {
  const theme = useTheme();
  const { t } = useTranslation();
  const { contentLanguages, languageFilterEnabled } = useLanguage();
  
  // State for different novel sections
  const [homeData, setHomeData] = useState<{
    top_novels: Novel[];
    trending_novels: Novel[];
    top_rated_novels: Novel[];
    recently_updated: NovelFromSource[];
    featured_novel: NovelFeaturedResponse | null;
    recent_reviews: Review[];
    recommended_novels: Novel[];
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
        const languages = languageFilterEnabled ? contentLanguages : [];
        const data = await novelService.getHomePageData(languages);
        setHomeData(data);
        setError(null);
      } catch (error) {
        console.error('Error fetching home page data:', error);
        setError(t('home.loadFailed'));
      } finally {
        setLoading(false);
      }
    };

    fetchHomeData();
  }, [contentLanguages, languageFilterEnabled, t]);

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
          <Typography sx={{
            marginBottom: "16px"
          }}>
            {t('home.introHeading')}
          </Typography>
          <Typography sx={{
            marginBottom: "16px"
          }}>
            {t('home.introBody')}
          </Typography>
          <Typography>
            {t('home.introAddNovel')}
          </Typography>
        </Box>
      </Box>

      {!loading && (homeData?.recommended_novels?.length ?? 0) > 0 && (
        <Box sx={{ mb: 6 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h5" component="h2" sx={{
              fontWeight: "bold"
            }}>
              {t('library.recommended')}
            </Typography>
          </Box>
          <Divider sx={{ mb: 3 }} />

          <NovelRecommendation
            similarNovels={homeData!.recommended_novels.map((novel) => ({ ...novel, similarity: 0 }))}
            loading={false}
          />
        </Box>
      )}

      {/* Weekly Trending Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.hottest')}
          </Typography>
          <Button component={Link} to="/novels/search?sort_by=trending&sort_order=desc" variant="text">
            {t('common.viewMore')}
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
                  {...getNovelSourceLink(novel)}
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
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.bestOfAllTime')}
          </Typography>
          <Button component={Link} to="/novels/search?sort_by=popularity&sort_order=desc" variant="text">
            {t('common.viewMore')}
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
                  {...getNovelSourceLink(novel)}
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
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.ranking')}
          </Typography>
          <Button component={Link} to="/novels/search" variant="text">
            {t('common.viewMore')}
          </Button>
        </Box>
        <Divider sx={{ mb: 1 }} />

        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={rankingTab} onChange={handleRankingTabChange} aria-label={t('home.rankingsAria')}>
            <Tab label={t('home.mostRead')} id="tab-most-read" aria-controls="tabpanel-most-read" />
            <Tab label={t('home.newTrends')} id="tab-new-trends" aria-controls="tabpanel-new-trends" />
            <Tab label={t('home.userRated')} id="tab-user-rated" aria-controls="tabpanel-user-rated" />
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
                    {...getNovelSourceLink(novel)}
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
                    {...getNovelSourceLink(novel)}
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
                    {...getNovelSourceLink(novel)}
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
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.featured')}
          </Typography>
          <Button component={Link} to="/novels/search?sort_by=popularity&sort_order=desc" variant="text">
            {t('common.viewMore')}
          </Button>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {loading ? (
          <FeaturedNovelCard source={{} as NovelFromSource} isLoading={true} onClick={() => {}} />
        ) : homeData?.featured_novel ? (
          <FeaturedNovelCard 
            source={(homeData.featured_novel.novel.reading_source ?? homeData.featured_novel.novel.prefered_source) as NovelFromSource}
            isBookmarked={homeData.featured_novel.novel.is_bookmarked}
            {...getNovelSourceLink(homeData.featured_novel.novel)}
          />
        ) : (
          <Typography variant="body1" align="center">{t('home.noFeatured')}</Typography>
        )}
      </Box>

      {/* Recent Reviews Section */}
      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.latestReviews')}
          </Typography>
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
          <Typography variant="h5" component="h2" sx={{
            fontWeight: "bold"
          }}>
            {t('home.recentlyUpdated')}
          </Typography>
        </Box>
        <Divider sx={{ mb: 3 }} />
        
        {!loading && homeData && (
          <Grid container spacing={2}>
            {homeData.recently_updated.slice(0, 12).map((source) => (
              <Grid size={{ xs: 12, sm: 6, md: 4 }} key={source.id}>
                <ChapterCard
                  source={source}
                  {...getSourceLink(source)}
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
