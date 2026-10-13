import { Box, Paper, Skeleton } from '@mui/material';

/** Reading list detail skeleton: header card plus the novel rows of the loaded list. */
const ReadingListDetailSkeleton = () => (
  <Box sx={{ maxWidth: 1000, mx: 'auto', px: 3, py: 4 }}>
    <Paper sx={{ p: 3, mb: 3 }}>
      <Skeleton variant="text" width="50%" height={48} />
      <Skeleton variant="text" width="35%" height={24} sx={{ mb: 2 }} />
      <Skeleton variant="text" width="80%" />
      <Skeleton variant="text" width="60%" />
    </Paper>

    {[...Array(5)].map((_, index) => (
      <Skeleton key={`reading-list-item-skeleton-${index}`} variant="rounded" height={72} sx={{ mb: 1.5 }} />
    ))}
  </Box>
);

export default ReadingListDetailSkeleton;
