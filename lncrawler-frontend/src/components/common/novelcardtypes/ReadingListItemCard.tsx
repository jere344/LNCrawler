import React, { useState, useRef, useEffect } from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip, Skeleton, Tooltip,
  IconButton, Paper, Menu, MenuItem, ListItemIcon, ListItemText,
  Dialog, DialogTitle, DialogContent, DialogActions, Button,
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import UpdateIcon from '@mui/icons-material/Update';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import PersonIcon from '@mui/icons-material/Person';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { formatTimeAgo, getChapterName, languageCodeToFlag, languageCodeToName } from '@utils/Misc';
import { useAuth } from '@context/AuthContext';
import { Link } from 'react-router-dom';
import { formatCount } from './BaseNovelCard';
import BookmarkButton from '@components/common/BookmarkButton';

export interface ReadingListCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  to?: string;
  note?: string;
  isOwner?: boolean;
  onEditNote?: (itemId: string, note?: string) => void;
  onRemoveItem?: (itemId: string) => void;
  itemId?: string;
}

export const ReadingListCard: React.FC<ReadingListCardProps> = ({ 
  novel, 
  onClick, 
  isLoading = false,
  to,
  note,
  isOwner = false,
  onEditNote,
  onRemoveItem,
  itemId
}) => {
  const preferredSource = novel.prefered_source;
  const { isAuthenticated } = useAuth();
  const [menuAnchorEl, setMenuAnchorEl] = useState<null | HTMLElement>(null);
  const [isNoteModalOpen, setIsNoteModalOpen] = useState(false);
  const [isNoteTruncated, setIsNoteTruncated] = useState(false);
  const noteRef = useRef<HTMLDivElement>(null);

  let tooltip = "";
  if (novel.reading_history?.next_chapter) {
    tooltip += `. Next : ${getChapterName(novel.reading_history.next_chapter.title)}`;
  }
  
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

  if (isLoading) {
    return (
      <Paper sx={{ 
        display: 'flex', 
        height: 180,
        overflow: 'hidden'
      }}>
        <Box sx={{ width: 120, flexShrink: 0 }}>
          <Skeleton variant="rectangular" width="100%" height="100%" />
        </Box>
        <CardContent sx={{ flex: 1 }}>
          <Skeleton variant="text" height={32} />
          <Skeleton variant="text" width="60%" />
          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Skeleton variant="rectangular" width={80} height={24} />
            <Skeleton variant="rectangular" width={80} height={24} />
          </Box>
        </CardContent>
      </Paper>
    );
  }

  return (
    <Card 
      sx={{ 
        display: 'flex',
        height: 180,
        transition: 'transform 0.2s ease, box-shadow 0.2s ease',
        '&:hover': {
          transform: 'translateY(-2px)',
          boxShadow: '0px 6px 12px -2px rgba(0,0,0,0.15)',
        },
        position: 'relative',
        overflow: 'hidden',
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

          {isOwner && onEditNote && onRemoveItem && itemId && (
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
          onClick={onClick}
          component={to ? Link : 'div'}
          to={to}
        >
          <CardMedia
            component="img"
            image={preferredSource?.cover_min_url || defaultCover}
            alt={novel.title}
            sx={{ 
              width: '100%',
              height: '100%',
              objectFit: 'cover',
            }}
          />
          {/* Language flags */}
          <Box
            sx={{
              position: 'absolute',
              bottom: 4,
              right: 4,
              display: 'flex',
              gap: 0.25,
              alignItems: 'center',
            }}
          >
            {novel.languages.length > 0 ? (
              novel.languages.slice(0, 2).map((lang) => (
                <Tooltip key={lang} title={languageCodeToName(lang)}>
                  <img 
                    src={`/flags/${languageCodeToFlag(lang)}.svg`} 
                    alt={languageCodeToName(lang)}
                    style={{ 
                      width: '20px',
                      height: '14px',
                      objectFit: 'cover',
                      borderRadius: '2px',
                      boxShadow: '0 1px 2px rgba(0,0,0,0.3)',
                    }}
                  />
                </Tooltip>
              ))
            ) : (
              <Tooltip title="Unknown language">
                <Box
                  sx={{
                    width: '20px',
                    height: '14px',
                    bgcolor: 'rgba(0,0,0,0.6)',
                    color: 'white',
                    fontSize: '0.7rem',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    borderRadius: '2px',
                  }}
                >
                  ?
                </Box>
              </Tooltip>
            )}
          </Box>
        </CardActionArea>
      </Box>

      {/* Metadata Content */}
      <CardActionArea 
        sx={{ flex: 1, alignItems: 'stretch' }}
        onClick={onClick}
        component={to ? Link : 'div'}
        to={to}
      >
        <CardContent sx={{ 
          height: '100%', 
          display: 'flex', 
          flexDirection: 'column',
          py: 1,
          px: 2,
          '&:last-child': { pb: 2 }
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
            }}
          >
            {novel.title}
          </Typography>
          
          {/* Author */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <PersonIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 14, height: 14 }} />
            <Typography variant="body2" color="text.secondary" noWrap>
              {preferredSource?.authors && preferredSource.authors.length > 0 
                ? preferredSource.authors.slice(0, 2).join(', ')
                : 'Unknown'}
            </Typography>
          </Box>
          
          {/* Tags */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 14, height: 14 }} />
            <Typography variant="body2" color="text.secondary" noWrap>
              {preferredSource?.tags && preferredSource.tags.length > 0 ? 
                `${preferredSource.tags.slice(0, 2).join(', ')}${preferredSource.tags.length > 2 ? '...' : ''}` 
                : 'Unknown'}
            </Typography>
          </Box>
          
          {/* Rating */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Rating 
              value={novel.avg_rating || 0} 
              precision={0.5} 
              readOnly 
              size="small" 
            />
            <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5, overflow: 'hidden', height: '1.2em' }}>
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
              '& .MuiChip-root': { 
                height: '20px',
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
            <Tooltip title="Total Chapters">
              <Chip 
                icon={<MenuBookIcon />}
                label={preferredSource?.chapters_count ? formatCount(preferredSource.chapters_count) : '?'}
                size="small"
                variant="outlined"
              />
            </Tooltip>

            <Tooltip title="Views">
              <Chip 
                icon={<VisibilityIcon />}
                label={novel.total_views !== undefined ? formatCount(novel.total_views) : '?'}
                size="small"
                variant="outlined"
              />
            </Tooltip>
            
            <Tooltip title="Last Updated">
              <Chip 
                icon={<UpdateIcon />}
                label={preferredSource?.last_chapter_update ? formatTimeAgo(new Date(preferredSource?.last_chapter_update)) : '?'}
                size="small"
                variant="outlined"
              />
            </Tooltip>
          </Box>
        </CardContent>
      </CardActionArea>

      {/* Note Section */}
      {note && (
        <Box 
          sx={{ 
            flex: 2,
            display: 'flex',
            flexDirection: 'column',
            borderLeft: '1px solid',
            borderColor: 'divider',
            minWidth: 0, // Allows text truncation
          }}
        >
          <CardContent sx={{ 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column',
            py: 1,
            px: 2,
            '&:last-child': { pb: 2 }
          }}>
            <Typography 
              variant="body2" 
              sx={{ 
                fontSize: '0.75rem',
                color: 'text.secondary',
                mb: 0.5,
                fontWeight: 'medium',
                textTransform: 'uppercase',
                letterSpacing: '0.5px'
              }}
            >
              Note
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
                  }}
                >
                  See more
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
          <ListItemText primary={note ? "Edit Note" : "Add Note"} />
        </MenuItem>
        <MenuItem onClick={handleRemoveItem}>
          <ListItemIcon>
            <DeleteIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary="Remove from List" />
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
          <Typography variant="h6">Note</Typography>
          <Typography variant="subtitle2" color="text.secondary">
            {novel.title}
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
          <Button onClick={handleNoteModalClose}>Close</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
};

export default ReadingListCard;
