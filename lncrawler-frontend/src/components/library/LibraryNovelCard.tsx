import React, { useMemo, useState } from 'react';
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Checkbox,
  Chip,
  Divider,
  IconButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Rating,
  Tooltip,
  Typography,
} from '@mui/material';
import { useSortable } from '@dnd-kit/sortable';
import { useDraggable } from '@dnd-kit/core';
import { CSS } from '@dnd-kit/utilities';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import StickyNote2Icon from '@mui/icons-material/StickyNote2';
import EditNoteIcon from '@mui/icons-material/EditNote';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import defaultCover from '@assets/default-cover.jpg';
import { getNovelSourceLink } from '@utils/Misc';
import { LibraryFolder, Novel } from '@models/novels_types';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

interface LibraryNovelCardProps {
  novel: Novel;
  editable?: boolean;
  selectable?: boolean;
  selected?: boolean;
  selectionActive?: boolean;
  onToggleSelect?: (novel: Novel, opts: { shiftKey: boolean }) => void;
  sortable?: boolean;
  draggable?: boolean;
  showRating?: boolean;
  showNote?: boolean;
  folders?: LibraryFolder[];
  onRate?: (novel: Novel, value: number | null) => void;
  onEditNote?: (novel: Novel) => void;
  onMove?: (novel: Novel, folderId: string | null) => void;
  onRemove?: (novel: Novel) => void;
}

interface DndHandle {
  setNodeRef: (node: HTMLElement | null) => void;
  attributes: Record<string, unknown>;
  listeners: Record<string, unknown> | undefined;
  transform: { x: number; y: number; scaleX: number; scaleY: number } | null;
  transition: string | undefined;
  isDragging: boolean;
}

const CoverOverlays: React.FC<{ novel: Novel }> = ({ novel }) => {
  const unread = useMemo(() => {
    if (novel.reading_history) {
      const latest = novel.reading_history.source_latest_chapter?.chapter_id || 0;
      const last = novel.reading_history.last_read_chapter.chapter_id;
      const diff = latest - last;
      return diff > 0 ? diff : null;
    }
    if (novel.is_bookmarked && novel.prefered_source?.latest_available_chapter) {
      return novel.prefered_source.latest_available_chapter.chapter_id;
    }
    return null;
  }, [novel]);

  return (
    <>
      {unread != null && (
        <Box
          sx={{
            position: 'absolute',
            top: 8,
            left: 8,
            zIndex: 3,
            bgcolor: 'primary.main',
            color: 'primary.contrastText',
            borderRadius: '12px',
            px: 1,
            py: 0.25,
            fontWeight: 'bold',
            fontSize: '0.75rem',
            boxShadow: '0 2px 6px rgba(0,0,0,0.35)',
          }}
        >
          {unread > 999 ? '999+' : unread}
        </Box>
      )}
      {novel.is_dmca && (
        <Chip
          label="DMCA"
          color="error"
          size="small"
          sx={{ position: 'absolute', top: 36, left: 8, zIndex: 3, fontWeight: 'bold' }}
        />
      )}
    </>
  );
};

const CardShell: React.FC<LibraryNovelCardProps & { dnd?: DndHandle; isSortable?: boolean }> = ({
  novel,
  editable = false,
  selectable = false,
  selected = false,
  selectionActive = false,
  onToggleSelect,
  dnd,
  isSortable = false,
  draggable = false,
  showRating = true,
  showNote = true,
  folders = [],
  onRate,
  onEditNote,
  onMove,
  onRemove,
}) => {
  const { t } = useTranslation();
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const preferredSource = novel.reading_source ?? novel.prefered_source;
  const cover = preferredSource?.cover_min_url || defaultCover;
  const linkProps = getNovelSourceLink(novel);
  const canDrag = Boolean(dnd && draggable);

  const style = dnd
    ? {
        transform:
          isSortable && dnd.transform ? CSS.Translate.toString(dnd.transform) : undefined,
        transition: isSortable ? dnd.transition : undefined,
        opacity: dnd.isDragging ? 0.35 : 1,
        height: '100%',
      }
    : { height: '100%' };

  const handleAreaClick = (event: React.MouseEvent) => {
    if (selectable && selectionActive) {
      event.preventDefault();
      event.stopPropagation();
      onToggleSelect?.(novel, { shiftKey: event.shiftKey });
    }
  };

  const handleToggleCheckbox = (event: React.ChangeEvent<HTMLInputElement>) => {
    event.stopPropagation();
    onToggleSelect?.(novel, { shiftKey: (event.nativeEvent as MouseEvent).shiftKey ?? false });
  };

  const menuOpen = Boolean(menuAnchor);
  const hasMenu = editable && (onEditNote || onMove || onRemove);

  return (
    <Box
      ref={dnd?.setNodeRef}
      style={style}
      sx={{ position: 'relative', height: '100%' }}
    >
      <Card
        className="card-root"
        sx={{
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          position: 'relative',
          overflow: 'hidden',
          borderRadius: 2,
          transition: 'transform 0.2s ease, box-shadow 0.2s ease',
          '&:hover': {
            transform: 'translateY(-4px)',
            boxShadow: 6,
          },
          '&:hover .card-quick': { opacity: 1 },
          ...(selected && {
            outline: '3px solid',
            outlineColor: 'primary.main',
            outlineOffset: -1,
          }),
        }}
      >
        {selectable && (
          <Checkbox
            checked={selected}
            onChange={handleToggleCheckbox}
            onClick={(e) => e.stopPropagation()}
            sx={{
              position: 'absolute',
              top: 2,
              left: 2,
              zIndex: 5,
              p: 0.5,
              color: 'common.white',
              bgcolor: 'rgba(0,0,0,0.35)',
              borderRadius: 1,
              opacity: selectionActive ? 1 : 0,
              transition: 'opacity 0.15s ease',
              '&:hover': { bgcolor: 'rgba(0,0,0,0.5)' },
              '&.Mui-checked': { color: 'primary.light' },
              ...(!selectionActive && { '.card-root:hover &': { opacity: 0.85 } }),
            }}
          />
        )}

        {canDrag && (
          <Box
            sx={{
              position: 'absolute',
              top: '50%',
              left: '50%',
              transform: 'translate(-50%, -50%)',
              zIndex: 4,
              color: 'common.white',
              bgcolor: 'rgba(0,0,0,0.45)',
              borderRadius: '50%',
              p: 0.75,
              display: 'flex',
              pointerEvents: 'none',
              opacity: 0,
              transition: 'opacity 0.15s ease',
              '.card-root:hover &': { opacity: 1 },
            }}
          >
            <DragIndicatorIcon />
          </Box>
        )}

        {hasMenu && (
          <IconButton
            className="card-quick"
            size="small"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setMenuAnchor(e.currentTarget);
            }}
            sx={{
              position: 'absolute',
              top: 6,
              right: 6,
              zIndex: 5,
              color: 'common.white',
              bgcolor: 'rgba(0,0,0,0.35)',
              borderRadius: 1,
              opacity: 0,
              transition: 'opacity 0.15s ease',
              '&:hover': { bgcolor: 'rgba(0,0,0,0.55)' },
              '&:focus-visible': { opacity: 1 },
            }}
          >
            <MoreVertIcon fontSize="small" />
          </IconButton>
        )}

        <CardActionArea
          onClick={handleAreaClick}
          component={!selectionActive && linkProps.to ? Link : 'div'}
          to={!selectionActive ? linkProps.to : undefined}
          state={!selectionActive ? linkProps.state : undefined}
          {...(canDrag ? { ...(dnd?.attributes as object), ...(dnd?.listeners as object) } : {})}
          sx={{
            display: 'block',
            cursor: canDrag ? 'grab' : 'pointer',
            ...(canDrag && { touchAction: 'none', '&:active': { cursor: 'grabbing' } }),
          }}
        >
          <Box sx={{ position: 'relative', pt: '150%', overflow: 'hidden' }}>
            <CardMedia
              component="img"
              image={cover}
              alt={novel.title}
              sx={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: novel.is_dmca ? 0.55 : 1,
                filter: novel.is_dmca ? 'grayscale(100%)' : 'none',
              }}
            />
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                background:
                  'linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.35) 28%, rgba(0,0,0,0) 55%)',
              }}
            />
            <Typography
              variant="subtitle1"
              component="div"
              sx={{
                position: 'absolute',
                bottom: 0,
                left: 0,
                right: 0,
                p: 1,
                color: 'common.white',
                fontWeight: 600,
                lineHeight: 1.25,
                textShadow: '0 1px 3px rgba(0,0,0,0.6)',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}
            >
              {novel.title}
            </Typography>
            <CoverOverlays novel={novel} />
          </Box>
        </CardActionArea>

        <CardContent
          sx={{
            p: 1,
            pt: 0.75,
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            flexGrow: 1,
            '&:last-child': { pb: 1 },
          }}
        >
          {showRating && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
              <Rating
                value={novel.user_rating || 0}
                readOnly={!onRate}
                size="small"
                onChange={(_, value) => onRate?.(novel, value)}
              />
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
                {novel.user_rating ? `${novel.user_rating}/5` : t('library.notRated')}
              </Typography>
            </Box>
          )}

          {(editable || (showNote && novel.note)) && (
            <Box
              onClick={editable ? () => onEditNote?.(novel) : undefined}
              sx={{
                mt: 'auto',
                display: 'flex',
                alignItems: 'flex-start',
                gap: 0.5,
                minHeight: 32,
                px: 0.5,
                pt: 0.5,
                borderRadius: 1,
                borderTop: '1px dashed',
                borderColor: 'divider',
                cursor: editable ? 'pointer' : 'default',
                '&:hover': editable ? { bgcolor: 'action.hover' } : undefined,
              }}
            >
              <StickyNote2Icon sx={{ fontSize: 15, color: 'text.secondary', mt: '1px' }} />
              <Tooltip
                title={novel.note || ''}
                disableHoverListener={!novel.note}
                slotProps={{ popper: { sx: { maxWidth: 280 } } }}
              >
                <Typography
                  variant="caption"
                  sx={{
                    color: novel.note ? 'text.secondary' : 'text.disabled',
                    fontStyle: novel.note ? 'normal' : 'italic',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                  }}
                >
                  {novel.note || t('library.addNote')}
                </Typography>
              </Tooltip>
            </Box>
          )}
        </CardContent>
      </Card>

      <Menu
        anchorEl={menuAnchor}
        open={menuOpen}
        onClose={() => setMenuAnchor(null)}
        slotProps={{ paper: { sx: { minWidth: 200 } } }}
      >
        {onEditNote && (
          <MenuItem
            onClick={() => {
              setMenuAnchor(null);
              onEditNote(novel);
            }}
          >
            <ListItemIcon><EditNoteIcon fontSize="small" /></ListItemIcon>
            <ListItemText>{t('library.editNote')}</ListItemText>
          </MenuItem>
        )}
        {onMove && (
          <Divider sx={{ my: 0.5 }} />
        )}
        {onMove && (
          <MenuItem disabled sx={{ opacity: 0.7, fontSize: '0.75rem', minHeight: 28 }}>
            {t('library.moveToFolder')}
          </MenuItem>
        )}
        {onMove &&
          folders.map((folder) => (
            <MenuItem
              key={folder.id}
              selected={novel.folder === folder.id}
              onClick={() => {
                setMenuAnchor(null);
                onMove(novel, folder.id);
              }}
            >
              <ListItemIcon><FolderIcon fontSize="small" /></ListItemIcon>
              <ListItemText>{folder.name}</ListItemText>
            </MenuItem>
          ))}
        {onMove && (
          <MenuItem
            selected={!novel.folder}
            onClick={() => {
              setMenuAnchor(null);
              onMove(novel, null);
            }}
          >
            <ListItemIcon><FolderOffIcon fontSize="small" /></ListItemIcon>
            <ListItemText>{t('library.unfiled')}</ListItemText>
          </MenuItem>
        )}
        {onRemove && (
          <>
            <Divider sx={{ my: 0.5 }} />
            <MenuItem
              onClick={() => {
                setMenuAnchor(null);
                onRemove(novel);
              }}
            >
              <ListItemIcon><DeleteOutlineIcon fontSize="small" color="error" /></ListItemIcon>
              <ListItemText sx={{ color: 'error.main' }}>
                {t('library.removeFromLibrary')}
              </ListItemText>
            </MenuItem>
          </>
        )}
      </Menu>
    </Box>
  );
};

const SortableLibraryCard: React.FC<LibraryNovelCardProps> = (props) => {
  const dnd = useSortable({
    id: props.novel.bookmark_id || props.novel.id,
    disabled: !props.draggable,
  });
  return <CardShell {...props} dnd={dnd as unknown as DndHandle} isSortable />;
};

const DraggableLibraryCard: React.FC<LibraryNovelCardProps> = (props) => {
  const dnd = useDraggable({
    id: props.novel.bookmark_id || props.novel.id,
    disabled: !props.draggable,
  });
  return <CardShell {...props} dnd={dnd as unknown as DndHandle} />;
};

const LibraryNovelCard: React.FC<LibraryNovelCardProps> = (props) => {
  if (props.sortable) return <SortableLibraryCard {...props} />;
  if (props.draggable) return <DraggableLibraryCard {...props} />;
  return <CardShell {...props} />;
};

export default LibraryNovelCard;
