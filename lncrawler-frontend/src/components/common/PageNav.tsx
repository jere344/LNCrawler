import React from 'react';
import { Box, Pagination } from '@mui/material';
import type { PaginationProps, SxProps, Theme } from '@mui/material';

interface PageNavProps {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
  size?: PaginationProps['size'];
  siblingCount?: number;
  showEdgeButtons?: boolean;
  sx?: SxProps<Theme>;
}

// Centered MUI pagination, rendered only when there is more than one page.
const PageNav: React.FC<PageNavProps> = ({ page, totalPages, onChange, size, siblingCount, showEdgeButtons, sx }) => {
  if (totalPages <= 1) return null;
  return (
    <Box sx={{ display: 'flex', justifyContent: 'center', ...sx }}>
      <Pagination
        count={totalPages}
        page={page}
        onChange={(_, value) => onChange(value)}
        color="primary"
        size={size}
        siblingCount={siblingCount}
        showFirstButton={showEdgeButtons}
        showLastButton={showEdgeButtons}
      />
    </Box>
  );
};

export default PageNav;
