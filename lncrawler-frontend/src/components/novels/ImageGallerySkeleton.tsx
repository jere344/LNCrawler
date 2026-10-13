import { Box, Container, Skeleton } from '@mui/material';

const HEIGHTS = [220, 300, 180, 260, 200, 280, 240, 190, 270];

/** Image gallery skeleton: same heading, toggle and masonry grid as the loaded gallery. */
const ImageGallerySkeleton = () => (
  <Container maxWidth="lg">
    <Skeleton variant="text" width="40%" height={24} sx={{ mt: 2 }} />
    <Skeleton variant="rounded" width={140} height={36} sx={{ mt: 2 }} />

    <Box sx={{ mt: 3 }}>
      <Skeleton variant="text" width="30%" height={48} />
      <Skeleton variant="text" width="45%" height={28} sx={{ mb: 2 }} />
      <Skeleton variant="rounded" width={220} height={24} sx={{ mb: 3 }} />

      <Box sx={{ columnCount: { xs: 2, sm: 3 }, columnGap: '8px' }}>
        {HEIGHTS.map((height, index) => (
          <Skeleton key={`gallery-skeleton-${index}`} variant="rounded" height={height} sx={{ display: 'block', mb: 1, borderRadius: 2, breakInside: 'avoid' }} />
        ))}
      </Box>
    </Box>
  </Container>
);

export default ImageGallerySkeleton;
