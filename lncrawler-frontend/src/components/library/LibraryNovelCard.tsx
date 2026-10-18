import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  CardMedia,
  Button,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
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
import MoreVertIcon from '@mui/icons-material/MoreVert';
import StickyNote2Icon from '@mui/icons-material/StickyNote2';
import EditNoteIcon from '@mui/icons-material/EditNote';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import defaultCover from '@assets/default-cover.jpg';
import { getNovelSourceLink, getNovelDisplayTitle } from '@utils/Misc';
import { LibraryFolder, Novel } from '@models/novels_types';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import {
  getMarkAsReadTarget,
  hasUnreadChapters,
} from '@components/common/MarkAsReadButton';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';

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
  onMarkedAsRead?: (novel: Novel) => void;
  onLongPress?: (novel: Novel) => void;
}

const LONG_PRESS_MS = 500;
const LONG_PRESS_MOVE_PX = 10;

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
      // Only chapters with content count (backend supplies the count), so
      // gaps left by failed downloads don't inflate the badge.
      const unread = novel.reading_history.unread_chapters;
      if (unread === undefined || unread === null) return null;
      return unread > 0 ? unread : null;
    }
    if (novel.is_bookmarked && novel.prefered_source) {
      const available = novel.prefered_source.available_chapters_count
        ?? novel.prefered_source.latest_available_chapter?.chapter_id;
      return available && available > 0 ? available : null;
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
  onMarkedAsRead,
  onLongPress,
}) => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const pressTimerRef = useRef<number | null>(null);
  const pressStartRef = useRef<{ x: number; y: number } | null>(null);
  const longPressFiredRef = useRef(false);
  const { isBlurred, revealHandler } = useAdultContent();
  const blurred = isBlurred(novel.is_adult, novel.id);
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [markReadOpen, setMarkReadOpen] = useState(false);
  const [markReadBusy, setMarkReadBusy] = useState(false);
  const canMarkRead = Boolean(isAuthenticated && hasUnreadChapters(novel));
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

  // Stable across renders so the scroll listener can always be removed.
  const clearPress = useCallback(() => {
    if (pressTimerRef.current !== null) {
      window.clearTimeout(pressTimerRef.current);
      pressTimerRef.current = null;
    }
    pressStartRef.current = null;
    window.removeEventListener('scroll', clearPress, true);
  }, []);

  // Clear any pending long-press timer on unmount.
  useEffect(() => clearPress, [clearPress]);

  const handleTouchStart = (event: React.TouchEvent) => {
    if (!onLongPress || event.touches.length !== 1) return;
    longPressFiredRef.current = false;
    const touch = event.touches[0];
    pressStartRef.current = { x: touch.clientX, y: touch.clientY };
    window.addEventListener('scroll', clearPress, { capture: true, passive: true });
    pressTimerRef.current = window.setTimeout(() => {
      pressTimerRef.current = null;
      pressStartRef.current = null;
      window.removeEventListener('scroll', clearPress, true);
      longPressFiredRef.current = true;
      onLongPress(novel);
    }, LONG_PRESS_MS);
  };

  const handleTouchMove = (event: React.TouchEvent) => {
    const start = pressStartRef.current;
    if (!start) return;
    const touch = event.touches[0];
    if (
      Math.abs(touch.clientX - start.x) > LONG_PRESS_MOVE_PX ||
      Math.abs(touch.clientY - start.y) > LONG_PRESS_MOVE_PX
    ) {
      clearPress();
    }
  };

  const handleTouchEnd = () => {
    clearPress();
  };

  // Suppress the native context menu while a long press is in progress or just fired.
  const handleContextMenu = (event: React.MouseEvent) => {
    if (pressTimerRef.current !== null || longPressFiredRef.current) {
      event.preventDefault();
    }
  };

  const handleAreaClick = (event: React.MouseEvent) => {
    if (longPressFiredRef.current) {
      // The press already selected this card; swallow the click that follows.
      longPressFiredRef.current = false;
      event.preventDefault();
      event.stopPropagation();
      return;
    }
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
  const hasMenu = (editable && (onEditNote || onMove || onRemove)) || canMarkRead;

  const handleConfirmMarkRead = async () => {
    const target = getMarkAsReadTarget(novel);
    setMarkReadOpen(false);
    if (!target) return;
    try {
      setMarkReadBusy(true);
      await userService.markChapterAsRead(novel.slug, target.sourceSlug, target.chapterNumber);
      onMarkedAsRead?.(novel);
    } catch (error) {
      console.error('Error marking novel as read:', error);
    } finally {
      setMarkReadBusy(false);
    }
  };

  return (
    <Box
      ref={dnd?.setNodeRef}
      style={style}
      sx={{ position: 'relative', height: '100%' }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
      onTouchCancel={handleTouchEnd}
      onContextMenu={handleContextMenu}
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
            zIndex: 2,
          },
          '&:hover .card-quick': { opacity: 1 },
          '@media (hover: none)': {
            '& .card-quick': { opacity: 1 },
          },
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
              alt={getNovelDisplayTitle(novel)}
              onClick={blurred ? revealHandler(novel.id) : undefined}
              sx={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                opacity: novel.is_dmca ? 0.55 : 1,
                cursor: blurred ? 'pointer' : undefined,
                filter: [
                  novel.is_dmca ? 'grayscale(100%)' : null,
                  blurred ? 'blur(16px)' : null,
                ].filter(Boolean).join(' ') || 'none',
              }}
            />
            <AdultBadge isAdult={novel.is_adult} novelId={novel.id} />
            <Box
              sx={{
                position: 'absolute',
                inset: 0,
                pointerEvents: 'none',
                background:
                  'linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.35) 28%, rgba(0,0,0,0) 55%)',
              }}
            />
            <Typography
              variant="subtitle1"
              component="div"
              sx={{
                position: 'absolute',
                bottom: 6,
                left: 0,
                right: 0,
                p: 1,
                color: 'common.white',
                fontWeight: 600,
                lineHeight: 1.25,
                textShadow: '0 1px 3px rgba(0,0,0,0.6)',
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                wordBreak: 'break-word',
              }}
            >
              {getNovelDisplayTitle(novel)}
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
                minHeight: 48,
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
                    WebkitLineClamp: 4,
                    WebkitBoxOrient: 'vertical',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
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
        {canMarkRead && (
          <MenuItem
            disabled={markReadBusy}
            onClick={() => {
              setMenuAnchor(null);
              setMarkReadOpen(true);
            }}
          >
            <ListItemIcon><DoneAllIcon fontSize="small" /></ListItemIcon>
            <ListItemText>{t('markAsRead.tooltip')}</ListItemText>
          </MenuItem>
        )}
        {canMarkRead && (editable && (onEditNote || onMove || onRemove)) && (
          <Divider sx={{ my: 0.5 }} />
        )}
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

      <Dialog
        open={markReadOpen}
        onClose={() => setMarkReadOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('markAsRead.confirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('markAsRead.confirmBody', { title: getNovelDisplayTitle(novel) })}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setMarkReadOpen(false)} color="inherit">
            {t('common.cancel')}
          </Button>
          <Button
            onClick={handleConfirmMarkRead}
            color="primary"
            variant="contained"
            disabled={markReadBusy}
          >
            {t('markAsRead.confirm')}
          </Button>
        </DialogActions>
      </Dialog>
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
