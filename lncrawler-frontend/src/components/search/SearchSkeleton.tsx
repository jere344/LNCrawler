import { Box, Container, Grid, Paper, Skeleton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseNovelCard from '../common/novelcardtypes/BaseNovelCard';
import type { Novel } from '@models/novels_types';

/**
 * Search page skeleton. Mirrors the loaded page by default: the advanced filter
 * panel is hidden until the Filters button opens it, so only the search row,
 * the active-filter chips and the result grid are drawn.
 */
const SearchSkeleton = () => {
  const { t } = useTranslation();

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        {t('search.heading')}
      </Typography>

      <Paper sx={{ p: 2, mb: 3, display: 'flex', flexWrap: { xs: 'wrap', sm: 'nowrap' }, alignItems: 'center', gap: { xs: 1, sm: 0 } }}>
        <Skeleton variant="rounded" height={56} sx={{ flex: 1, minWidth: { xs: '100%', sm: 0 } }} />
        <Skeleton variant="rounded" height={36} sx={{ width: { xs: '100%', sm: 110 }, ml: { xs: 0, sm: 2 } }} />
        <Skeleton variant="rounded" height={36} sx={{ width: { xs: '100%', sm: 110 }, ml: { xs: 0, sm: 2 } }} />
      </Paper>

      <Box sx={{ mb: 3, display: 'flex', gap: 1 }}>
        <Skeleton variant="rounded" width={150} height={32} sx={{ borderRadius: 4 }} />
      </Box>

      <Skeleton variant="text" width={160} height={28} sx={{ mb: 2 }} />

      <Grid container spacing={3}>
        {[...Array(12)].map((_, index) => (
          <Grid key={`search-result-skeleton-${index}`} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
            <BaseNovelCard novel={{} as Novel} isLoading />
          </Grid>
        ))}
      </Grid>
    </Container>
  );
};

export default SearchSkeleton;
