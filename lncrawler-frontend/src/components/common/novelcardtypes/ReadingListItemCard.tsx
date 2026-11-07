import React, { useState, useRef, useEffect } from 'react';
import { 
  Card, CardActionArea, CardContent,
  Typography, Box, Rating,
  IconButton, Menu, MenuItem, ListItemIcon, ListItemText,
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
  useMediaQuery, useTheme,
} from '@mui/material';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import PersonIcon from '@mui/icons-material/Person';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { Novel } from '@models/novels_types';
import { formatCount, getNovelDisplayTitle, novelCoverUrl } from '@utils/Misc';
import { useAuth } from '@context/AuthContext';
import { Link } from 'react-router-dom';
import type { To } from 'react-router-dom';
import BookmarkButton from '@components/common/BookmarkButton';
import { useTranslation } from 'react-i18next';
import { NovelCover } from '@components/common/NovelCover';
import { NovelLanguageFlags } from '@components/common/NovelLanguageFlags';
import NovelStatsChips from './NovelStatsChips';

export interface ReadingListCardProps {
  novel: Novel;
  to?: To;
  state?: unknown;
  note?: string;
  canEdit?: boolean;
  onEditNote?: (itemId: string, note?: string) => void;
  onRemoveItem?: (itemId: string) => void;
  itemId?: string;
}

export const ReadingListNovelCard: React.FC<ReadingListCardProps> = ({
  novel,
  to,
  state,
  note,
  canEdit = false,
  onEditNote,
  onRemoveItem,
  itemId
}) => {
  const preferredSource = novel.reading_source ?? novel.prefered_source;
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const [isNoteModalOpen, setIsNoteModalOpen] = useState(false);
  const [isNoteTruncated, setIsNoteTruncated] = useState(false);
  const noteRef = useRef<HTMLDivElement>(null);

  const handleMenuOpen = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    e.preventDefault();
    setMenuAnchorEl(e.currentTarget);
  };

  const handleMenuClose = () => {
    setMenuAnchorEl(null);
  };

  const handleEditNote = () => {
    if (onEditNote && itemId) {
      onEditNote(itemId, note);
    }
    handleMenuClose();
  };

  const handleRemoveItem = () => {
    if (onRemoveItem && itemId) {
      onRemoveItem(itemId);
    }
    handleMenuClose();
  };

  const handleNoteModalOpen = () => {
    setIsNoteModalOpen(true);
  };

  const handleNoteModalClose = () => {
    setIsNoteModalOpen(false);
  };

  useEffect(() => {
    if (noteRef.current && note) {
      const element = noteRef.current;
      setIsNoteTruncated(element.scrollHeight > element.clientHeight);
    }
  }, [note]);

  return (
    <Card 
      sx={{ 
        display: 'flex',
        height: 180,
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: '0px 6px 12px -2px rgba(0,0,0,0.15)',
          zIndex: 2,
        },
        position: 'relative',
        overflow: 'hidden',
        width: '100%',
        minWidth: 0,
      }}
    >

      {isAuthenticated && (
        <Box
          sx={{
            position: 'absolute',
            right: 8,
            top: 8,
            zIndex: 10,
            display: 'flex',
            gap: 0.5,
          }}
        >
          <BookmarkButton 
            isBookmarked={novel.is_bookmarked || false} 
            slug={novel.slug}
            customSx={{
              '& .MuiIconButton-root': {
                width: 32,
                height: 32,
              },
              '& .MuiSvgIcon-root': {
                fontSize: 'medium',
              }
            }}
          />

          {canEdit && onEditNote && onRemoveItem && itemId && (
            <IconButton
              size="small"
              onClick={handleMenuOpen}
              sx={{
                bgcolor: 'rgba(0, 0, 0, 0.6)',
                color: 'white',
                '&:hover': {
                  bgcolor: 'rgba(0, 0, 0, 0.8)',
                },
                width: 32,
                height: 32,
              }}
            >
              <MoreVertIcon fontSize="small" />
            </IconButton>
          )}
        </Box>
      )}

      {/* Cover Image */}
      <Box sx={{ width: 120, flexShrink: 0, position: 'relative' }}>
        <CardActionArea
          sx={{ height: '100%' }}
          component={to ? Link : 'div'}
          to={to}
          state={to ? state : undefined}
        >
          <NovelCover
            src={novelCoverUrl(preferredSource)}
            alt={getNovelDisplayTitle(novel)}
            novelId={novel.id}
            isAdult={novel.is_adult}
            isDmca={novel.is_dmca}
            dmcaBadgeProps={{ top: 4, left: 4 }}
            sx={{ width: '100%', height: '100%' }}
          >
            {/* Language flags */}
            <NovelLanguageFlags languages={novel.languages} size="small" />
          </NovelCover>
        </CardActionArea>
      </Box>

      {/* Metadata Content - Hide on mobile when note exists */}
      {(!isMobile || !note) && (
        <CardActionArea 
          sx={{ 
            flex: 1, 
            alignItems: 'stretch',
            minWidth: 0,
          }}
          component={to ? Link : 'div'}
          to={to}
          state={to ? state : undefined}
        >
          <CardContent sx={{ 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column',
            py: 1,
            px: 2,
            '&:last-child': { pb: 2 },
            minWidth: 0,
            overflow: 'hidden',
          }}>
            <Typography 
              variant="h6" 
              component="div" 
              sx={{ 
                fontWeight: 'medium',
                lineHeight: 1.1,
                textOverflow: 'ellipsis',
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                mb: '6px',
                overflow: 'hidden',
                minWidth: 0,
              }}
            >
              {getNovelDisplayTitle(novel)}
            </Typography>
            
            {/* Author */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5, minWidth: 0 }}>
              <PersonIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 14, height: 14, flexShrink: 0 }} />
              <Typography
                variant="body2"
                noWrap
                sx={{
                  color: "text.secondary",
                  minWidth: 0
                }}>
                {preferredSource?.authors && preferredSource.authors.length > 0 
                  ? preferredSource.authors.join(', ')
                  : t('common.unknown')}
              </Typography>
            </Box>
            
            {/* Tags */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5, minWidth: 0 }}>
              <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 14, height: 14, flexShrink: 0 }} />
              <Typography
                variant="body2"
                noWrap
                sx={{
                  color: "text.secondary",
                  minWidth: 0
                }}>
                {preferredSource?.tags && preferredSource.tags.length > 0 ? 
                  `${preferredSource.tags.join(', ')}` 
                  : t('common.unknown')}
              </Typography>
            </Box>
            
            {/* Rating */}
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1, minWidth: 0 }}>
              <Rating 
                value={novel.avg_rating || 0} 
                precision={0.5} 
                readOnly 
                size="small"
                sx={{ flexShrink: 0 }}
              />
              <Typography
                variant="body2"
                sx={{
                  color: "text.secondary",
                  ml: 0.5,
                  overflow: 'hidden',
                  height: '1.2em',
                  minWidth: 0
                }}>
                {novel.avg_rating ? novel.avg_rating.toFixed(1) : '0.0'}
                {` (${novel.rating_count > 0 ? formatCount(novel.rating_count) : '0'})`}
              </Typography>
            </Box>
            
            {/* Metadata chips */}
            <Box 
              sx={{ 
                mt: 'auto',
                display: 'flex',
                gap: 0.5,
                flexWrap: 'wrap',
                minWidth: 0,
                '& .MuiChip-root': { 
                  height: '20px',
                  flexShrink: 0,
                  '& .MuiChip-label': { 
                    px: 0.5, 
                    fontSize: '0.8rem',
                  },
                  '& .MuiChip-icon': { 
                    ml: 0.25,
                    mr: -0.25
                  }
                } 
              }}
            >
              <NovelStatsChips novel={novel} source={preferredSource} />
            </Box>
          </CardContent>
        </CardActionArea>
      )}

      {/* Note Section */}
      {note && (
        <Box 
          sx={{ 
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            borderLeft: isMobile ? 'none' : '1px solid',
            borderColor: 'divider',
            minWidth: 0,
            maxWidth: isMobile ? 'none' : '300px',
          }}
        >
          <CardContent sx={{ 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column',
            py: 1,
            px: 2,
            '&:last-child': { pb: 2 },
            minWidth: 0,
            overflow: 'hidden',
          }}>
            {/* Show title on mobile */}
            {isMobile && (
              <Typography 
                variant="h6" 
                component="div" 
                sx={{ 
                  fontWeight: 'medium',
                  lineHeight: 1.1,
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  mb: 1,
                  overflow: 'hidden',
                  minWidth: 0,
                }}
              >
                {getNovelDisplayTitle(novel)}
              </Typography>
            )}
            
            <Typography 
              variant="body2" 
              sx={{ 
                fontSize: '0.75rem',
                color: 'text.secondary',
                mb: 0.5,
                fontWeight: 'medium',
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
                flexShrink: 0,
              }}
            >
              {t('cards.note')}
            </Typography>
            <Box 
              sx={{ 
                flex: 1,
                p: 1,
                bgcolor: 'action.hover',
                borderRadius: 1,
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                minWidth: 0,
              }}
            >
              <Typography 
                ref={noteRef}
                variant="body2" 
                sx={{ 
                  fontSize: '0.8rem',
                  fontStyle: 'italic',
                  lineHeight: 1.3,
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 6,
                  WebkitBoxOrient: 'vertical',
                  wordBreak: 'break-word',
                  whiteSpace: 'pre-wrap',
                  flex: 1,
                  minWidth: 0,
                }}
              >
                {note}
              </Typography>
              {isNoteTruncated && (
                <Button
                  size="small"
                  onClick={handleNoteModalOpen}
                  sx={{
                    alignSelf: 'flex-end',
                    fontSize: '0.75rem',
                    minHeight: 'auto',
                    py: 0,
                    px: 1,
                    flexShrink: 0,
                  }}
                >
                  {t('common.seeMore')}
                </Button>
              )}
            </Box>
          </CardContent>
        </Box>
      )}

      {/* Item Menu */}
      <Menu
        anchorEl={menuAnchorEl}
        open={Boolean(menuAnchorEl)}
        onClose={handleMenuClose}
      >
        <MenuItem onClick={handleEditNote}>
          <ListItemIcon>
            <EditIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={note ? t('cards.editNote') : t('cards.addNote')} />
        </MenuItem>
        <MenuItem onClick={handleRemoveItem}>
          <ListItemIcon>
            <DeleteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t('cards.removeFromList')} />
        </MenuItem>
      </Menu>

      {/* Note Modal */}
      <Dialog
        open={isNoteModalOpen}
        onClose={handleNoteModalClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Typography variant="h6">{t('cards.note')}</Typography>
          <Typography variant="subtitle2" sx={{
            color: "text.secondary"
          }}>
            {getNovelDisplayTitle(novel)}
          </Typography>
        </DialogTitle>
        <DialogContent>
          <Typography
            variant="body2"
            sx={{
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              lineHeight: 1.5,
            }}
          >
            {note}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleNoteModalClose}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default ReadingListNovelCard;
