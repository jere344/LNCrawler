import { Container, Paper, Skeleton } from '@mui/material';

/** Chapter list skeleton: same title block, search box and chapter rows as the loaded page. */
const ChapterListSkeleton = () => (
  <Container maxWidth="md">
    <Skeleton variant="text" width="45%" height={24} sx={{ mt: 2 }} />
    <Skeleton variant="rounded" width={140} height={36} sx={{ mt: 2 }} />

    <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
      <Skeleton variant="text" width="70%" height={48} />
      <Skeleton variant="text" width="40%" height={28} sx={{ mb: 3 }} />

      <Skeleton variant="rounded" height={56} sx={{ mb: 3 }} />

      <Skeleton variant="text" width={200} height={28} sx={{ mb: 2 }} />

      {[...Array(10)].map((_, index) => (
        <Skeleton key={`chapter-skeleton-${index}`} variant="rounded" height={48} sx={{ mb: 1 }} />
      ))}
    </Paper>
  </Container>
);

export default ChapterListSkeleton;
