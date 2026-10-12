import { Box, Typography, Divider, Grid, Tabs, Tab, Skeleton } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Novel, NovelFromSource } from '@models/novels_types';
import CompactNovelCard from '@components/common/novelcardtypes/CompactNovelCard';
import ChapterCard from '@components/common/novelcardtypes/ChapterCard';
import NovelItemCard from '@components/common/novelcardtypes/NovelItemCard';
import TrendingNovelCard from '@components/common/novelcardtypes/TrendingNovelCard';
import NovelRecommendation from '@components/common/NovelRecommendation';
import { useAuth } from '@context/AuthContext';

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <Box sx={{ mb: 6 }}>
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
      <Typography variant="h5" component="h2" sx={{ fontWeight: 'bold' }}>
        {title}
      </Typography>
    </Box>
    <Divider sx={{ mb: 3 }} />
    {children}
  </Box>
);

/**
 * Full-page home skeleton. Used both as the route's HydrateFallback (cold load)
 * and while the page revalidates, so the layout matches the loaded page and the
 * sections that used to appear only after load no longer shift the layout.
 */
const HomeSkeleton = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();

  return (
    <>
      <Box sx={{ my: 2 }}>
        <Typography variant="h1" component="h1" gutterBottom sx={{ fontWeight: 'bold', textAlign: 'center', mb: 3 }}>
          LNCrawler
        </Typography>
        <Box sx={{ backgroundColor: 'background.paper', padding: 2, mx: 0, borderRadius: 2, mb: 4 }}>
          <Typography sx={{ marginBottom: '16px' }}>{t('home.introHeading')}</Typography>
          <Typography sx={{ marginBottom: '16px' }}>{t('home.introBody')}</Typography>
          <Typography>{t('home.introAddNovel')}</Typography>
        </Box>
      </Box>

      {/* Recommendations only exist for logged-in users. */}
      {isAuthenticated && (
        <Section title={t('library.recommended')}>
          <NovelRecommendation similarNovels={[]} loading />
        </Section>
      )}

      <Section title={t('home.hottest')}>
        <Grid container spacing={3}>
          {[...Array(4)].map((_, index) => (
            <Grid size={{ xs: 6, sm: 3 }} key={`trending-skeleton-${index}`}>
              <TrendingNovelCard novel={{} as Novel} isLoading={true} rank={index + 1} />
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section title={t('home.bestOfAllTime')}>
        <Grid container spacing={2}>
          {[...Array(12)].map((_, index) => (
            <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={`top-skeleton-${index}`}>
              <NovelItemCard novel={{} as Novel} isLoading={true} rank={index + 1} onClick={() => {}} />
            </Grid>
          ))}
        </Grid>
      </Section>

      <Box sx={{ mb: 6 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
          <Typography variant="h5" component="h2" sx={{ fontWeight: 'bold' }}>
            {t('home.ranking')}
          </Typography>
        </Box>
        <Divider sx={{ mb: 1 }} />
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
          <Tabs value={1} onChange={() => {}} aria-label={t('home.rankingsAria')}>
            <Tab label={t('home.mostRead')} />
            <Tab label={t('home.newTrends')} />
            <Tab label={t('home.userRated')} />
          </Tabs>
        </Box>
        <Box sx={{ py: 3 }}>
          <Grid container spacing={1}>
            {[...Array(12)].map((_, index) => (
              <Grid size={{ xs: 6, sm: 4, md: 3 }} key={`ranking-skeleton-${index}`}>
                <CompactNovelCard novel={{} as Novel} isLoading={true} showTrends onClick={() => {}} />
              </Grid>
            ))}
          </Grid>
        </Box>
      </Box>

      <Section title={t('home.latestReviews')}>
        <Grid container spacing={2}>
          {[...Array(4)].map((_, index) => (
            <Grid size={{ xs: 12, sm: 6 }} key={`reviews-skeleton-${index}`}>
              <Box sx={{ p: 2, border: 1, borderColor: 'divider', borderRadius: 2 }}>
                <Skeleton variant="text" width="40%" height={24} />
                <Skeleton variant="text" width="90%" />
                <Skeleton variant="text" width="75%" />
              </Box>
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section title={t('home.recentlyAdded')}>
        <Grid container spacing={2}>
          {[...Array(12)].map((_, index) => (
            <Grid size={{ xs: 4, sm: 3, md: 2, lg: 2 }} key={`recently-added-skeleton-${index}`}>
              <NovelItemCard novel={{} as Novel} isLoading={true} onClick={() => {}} />
            </Grid>
          ))}
        </Grid>
      </Section>

      <Section title={t('home.recentlyUpdated')}>
        <Grid container spacing={2}>
          {[...Array(12)].map((_, index) => (
            <Grid size={{ xs: 12, sm: 6, md: 4 }} key={`recently-updated-skeleton-${index}`}>
              <ChapterCard source={{} as NovelFromSource} isLoading={true} />
            </Grid>
          ))}
        </Grid>
      </Section>
    </>
  );
};

export default HomeSkeleton;
