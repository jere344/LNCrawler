import { Box, Container, Grid, Skeleton } from '@mui/material';

// Placeholder grid of covers, shared by the route fallback and the in-page loading state.
export const AudiobookGridSkeleton = ({ count = 12 }: { count?: number }) => (
  <Grid container spacing={2}>
    {Array.from({ length: count }, (_, index) => (
      <Grid key={index} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
        <Skeleton variant="rounded" sx={{ aspectRatio: '1 / 1', height: 'auto', borderRadius: 2 }} />
        <Skeleton width="80%" sx={{ mt: 1 }} />
        <Skeleton width="50%" />
      </Grid>
    ))}
  </Grid>
);

// Placeholder of the audiobook page: hero (cover, title, actions) above the parts.
export const AudiobookPageSkeleton = () => (
  <Container maxWidth="lg" sx={{ py: 3 }}>
    <Skeleton width="40%" />
    <Grid container spacing={3} sx={{ mt: 1 }}>
      <Grid size={{ xs: 12, sm: 4, md: 3 }}>
        <Skeleton variant="rounded" sx={{ aspectRatio: '1 / 1', height: 'auto', borderRadius: 2 }} />
      </Grid>
      <Grid size={{ xs: 12, sm: 8, md: 9 }}>
        <Skeleton width="70%" height={48} />
        <Skeleton width="40%" />
        <Skeleton width="30%" />
        <Box sx={{ display: 'flex', gap: 1, mt: 2, flexWrap: 'wrap' }}>
          <Skeleton variant="rounded" width={140} height={36} />
          <Skeleton variant="rounded" width={120} height={36} />
          <Skeleton variant="rounded" width={120} height={36} />
        </Box>
        <Skeleton width="100%" sx={{ mt: 3 }} />
        <Skeleton width="90%" />
      </Grid>
    </Grid>
  </Container>
);

const AudiobooksSkeleton = () => (
  <Container maxWidth="lg" sx={{ py: 3 }}>
    <Skeleton width={220} height={44} />
    <Skeleton width="60%" />
    <Box sx={{ display: 'flex', gap: 2, my: 2, flexWrap: 'wrap' }}>
      <Skeleton variant="rounded" width={240} height={40} />
      <Skeleton variant="rounded" width={160} height={40} />
      <Skeleton variant="rounded" width={200} height={40} />
    </Box>
    <AudiobookGridSkeleton />
  </Container>
);

export default AudiobooksSkeleton;
