import { Box, ListItemButton, Skeleton, Typography } from '@mui/material';
import type { Chapter } from '@models/novels_types';

// Every row is this tall, so the list can be sized and scrolled by count
export const ROW_HEIGHT = 48;

// Shared by a row and its skeleton, so the two have the same geometry
// The number column fits the longest chapter number; the list sets it from its count
const NUMBER_WIDTH = 'var(--chapter-number-width, 4ch)';

const rowSx = {
  height: ROW_HEIGHT,
  px: 2,
  gap: 1.5,
  display: 'flex',
  alignItems: 'center',
  boxSizing: 'border-box',
  borderInlineStart: '3px solid transparent',
} as const;

interface ChapterRowProps {
  chapter: Chapter;
  // The row's place in the whole list, for the focus that moves between rows
  index: number;
  // Only one row of the list is in the tab order
  tabIndex: number;
  isCurrent: boolean;
  // The first row of a volume: drawn with a divider above it
  volumeStart: boolean;
  onClick: () => void;
}

export const ChapterRow = ({ chapter, index, tabIndex, isCurrent, volumeStart, onClick }: ChapterRowProps) => {
  return (
    <ListItemButton
      data-index={index}
      tabIndex={tabIndex}
      aria-current={isCurrent ? 'true' : undefined}
      disabled={!chapter.has_content}
      onClick={onClick}
      sx={{
        ...rowSx,
        // A shadow rather than a border, so the divider does not change the row height
        boxShadow: volumeStart ? (theme) => `inset 0 1px 0 ${theme.palette.divider}` : undefined,
        bgcolor: isCurrent ? 'action.selected' : undefined,
        // The bar is in rowSx on every row, so the text does not move when the current row changes
        borderInlineStartColor: isCurrent ? (theme) => theme.palette.primary.main : undefined,
        color: chapter.has_content ? 'text.primary' : 'text.disabled',
        fontWeight: isCurrent ? 600 : undefined,
      }}
    >
      <Typography component="span" sx={{ width: NUMBER_WIDTH, flexShrink: 0, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}>
        {chapter.chapter_id}
      </Typography>
      <Typography component="span" noWrap sx={{ flex: 1, minWidth: 0, color: 'inherit', fontWeight: 'inherit' }}>
        {chapter.display_title}
      </Typography>
    </ListItemButton>
  );
};

// Placeholder for a row whose page is not loaded yet: the same geometry as a row
// The widths depend on the index only, so a skeleton does not change between renders
// It takes focus in code only, so the focus can wait on the row's page without leaving the list
export const ChapterRowSkeleton = ({ index }: { index: number }) => (
  <Box aria-hidden data-index={index} tabIndex={-1} sx={rowSx}>
    <Box component="span" sx={{ width: NUMBER_WIDTH, flexShrink: 0 }}>
      <Skeleton variant="text" width={22} sx={{ fontSize: '1rem' }} />
    </Box>
    <Box component="span" sx={{ flex: 1, minWidth: 0 }}>
      <Skeleton variant="text" width={`${45 + ((index * 37) % 40)}%`} sx={{ fontSize: '1rem' }} />
    </Box>
  </Box>
);
