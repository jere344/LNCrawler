import React from 'react';
import { Box, IconButton, Tooltip, Typography } from '@mui/material';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import EditNoteIcon from '@mui/icons-material/EditNote';
import StickyNote2Icon from '@mui/icons-material/StickyNote2';
import BaseNovelCard from '@components/common/novelcardtypes/BaseNovelCard';
import { getNovelSourceLink } from '@utils/Misc';
import { Novel } from '@models/novels_types';
import { useTranslation } from 'react-i18next';

interface LibraryNovelCardProps {
  novel: Novel;
  editable?: boolean;
  sortable?: boolean;
  showRating?: boolean;
  onRate?: (novel: Novel, value: number | null) => void;
  onEditNote?: (novel: Novel) => void;
}

const LibraryNovelCard: React.FC<LibraryNovelCardProps> = ({
  novel,
  editable = false,
  sortable = false,
  showRating = true,
  onRate,
  onEditNote,
}) => {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: novel.bookmark_id || novel.id,
    disabled: !sortable,
  });

  const style = sortable
    ? {
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 1000 : 1,
      }
    : undefined;

  return (
    <Box ref={sortable ? setNodeRef : undefined} style={style} sx={{ position: 'relative', height: '100%' }}>
      {sortable && (
        <Box
          {...attributes}
          {...listeners}
          sx={{
            position: 'absolute',
            top: 8,
            left: 8,
            zIndex: 11,
            bgcolor: 'action.hover',
            borderRadius: 1,
            cursor: 'grab',
            touchAction: 'none',
            display: 'flex',
            '&:active': { cursor: 'grabbing' },
          }}
        >
          <DragIndicatorIcon fontSize="small" color="action" />
        </Box>
      )}

      {editable && onEditNote && (
        <Tooltip title={t('library.editNote')}>
          <IconButton
            size="small"
            onClick={(event) => {
              event.preventDefault();
              event.stopPropagation();
              onEditNote(novel);
            }}
            sx={{ position: 'absolute', top: 6, right: 6, zIndex: 11, bgcolor: 'action.hover' }}
          >
            <EditNoteIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      )}

      <BaseNovelCard
        novel={novel}
        hideUserState={!editable}
        showRating={showRating}
        ratingMode="user"
        ratingLabel={t('library.notRated')}
        onRate={editable && onRate ? (value) => onRate(novel, value) : undefined}
        {...getNovelSourceLink(novel)}
      />

      {novel.note && (
        <Tooltip title={novel.note}>
          <Box
            sx={{
              mt: 0.5,
              px: 1,
              py: 0.5,
              borderRadius: 1,
              bgcolor: 'action.hover',
              display: 'flex',
              alignItems: 'flex-start',
              gap: 0.5,
            }}
          >
            <StickyNote2Icon fontSize="inherit" color="action" sx={{ mt: '2px' }} />
            <Typography
              variant="caption"
              sx={{
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {novel.note}
            </Typography>
          </Box>
        </Tooltip>
      )}
    </Box>
  );
};

export default LibraryNovelCard;
