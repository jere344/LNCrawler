import React from 'react';
import { Box, Skeleton } from '@mui/material';

interface CoverRowSkeletonProps {
  coverHeight: number;
  children: React.ReactNode;
}

// Loading placeholder of a row card: the cover on the left, the text of the card on the right.
const CoverRowSkeleton: React.FC<CoverRowSkeletonProps> = ({ coverHeight, children }) => {
  const coverWidth = coverHeight * 2/3;

  return (
    <Box sx={{ display: 'flex', justifyContent: 'flex-start', alignItems: 'flex-start', height: coverHeight + 'px', width: '100%' }}>
      <Skeleton variant="rectangular" sx={{ width: coverWidth, minWidth: coverWidth, height: '100%', borderRadius: 1.5, flexShrink: 0, boxShadow: 2 }} />
      <Box sx={{ flexGrow: 1, flexShrink: 1, overflow: 'hidden', p: 1.5, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', height: '100%' }}>
        {children}
      </Box>
    </Box>
  );
};

export default CoverRowSkeleton;
