import { Box, Grid, Skeleton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

/** Reading lists page skeleton: same header, search bar and card grid as the loaded page. */
const ReadingListsSkeleton = () => {
  const { t } = useTranslation();

  return (
    <Box sx={{ py: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1">
          {t('readingLists.heading')}
        </Typography>
        <Skeleton variant="rounded" width={160} height={36} />
      </Box>

      <Box sx={{ mb: 3 }}>
        <Skeleton variant="rounded" height={56} />
      </Box>

      <Grid container spacing={3}>
        {[...Array(4)].map((_, index) => (
          <Grid key={`reading-list-skeleton-${index}`} size={{ xs: 12, sm: 6 }}>
            <Skeleton variant="rounded" height={140} />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default ReadingListsSkeleton;
