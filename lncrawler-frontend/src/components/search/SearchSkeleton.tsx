import { Container, Grid, Paper, Skeleton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import BaseNovelCard from '../common/novelcardtypes/BaseNovelCard';
import type { Novel } from '@models/novels_types';

/** Search page skeleton: same search box, filter panel and result grid as the loaded page. */
const SearchSkeleton = () => {
  const { t } = useTranslation();

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h4" component="h1" gutterBottom>
        {t('search.heading')}
      </Typography>

      <Paper sx={{ p: 2, mb: 3 }}>
        <Skeleton variant="rounded" height={56} />
      </Paper>

      <Paper sx={{ p: 3, mb: 3 }}>
        <Grid container spacing={3}>
          {[...Array(4)].map((_, index) => (
            <Grid key={`search-filter-skeleton-${index}`} size={{ xs: 12, md: 6 }}>
              <Skeleton variant="rounded" height={48} />
            </Grid>
          ))}
        </Grid>
      </Paper>

      <Skeleton variant="text" width={180} height={28} sx={{ mb: 2 }} />

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
