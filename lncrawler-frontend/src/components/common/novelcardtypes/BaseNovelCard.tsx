import React, { useState } from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip, Skeleton, Tooltip,
  Grid2 as Grid, IconButton
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import UpdateIcon from '@mui/icons-material/Update';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import PersonIcon from '@mui/icons-material/Person';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import BookmarkBorderIcon from '@mui/icons-material/BookmarkBorder';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { formatTimeAgo, getChapterName, languageCodeToFlag, languageCodeToName, toLocalDate } from '@utils/Misc';
import { userService } from '@services/user.service';
import { useAuth } from '@context/AuthContext';
import { Link } from 'react-router-dom';

export interface BaseNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  to?: string;
}

export function formatCount(count: number): string {
  if (count >= 1000000) {
    return `${(count / 1000000).toFixed(1)}M`;
  } else if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}K`;
  }
  return `${count}`;
}

export const BaseNovelCard: React.FC<BaseNovelCardProps> = ({ 
  novel, 
  onClick, 
  isLoading = false,
  to
}) => {
  const preferredSource = novel.prefered_source;
  const { isAuthenticated } = useAuth();
  const [isBookmarked, setIsBookmarked] = useState<boolean | null>(novel.is_bookmarked || false);
  const [bookmarkLoading, setBookmarkLoading] = useState(false);
  
  let unreadChapters = null;
  if (novel.reading_history && preferredSource?.latest_available_chapter) {
    const latestChapterId = preferredSource.latest_available_chapter.chapter_id;
    const lastReadChapterId = novel.reading_history.last_read_chapter.chapter_id;
    
    const unread = latestChapterId - lastReadChapterId;
    if (unread > 0) {
      unreadChapters = unread;
    }
  }

  let tooltip = "";
  if (unreadChapters) {
    tooltip = `${unreadChapters} unread chapter${unreadChapters > 1 ? 's' : ''}`;
  }
  if (novel.reading_history?.next_chapter) {
    tooltip += `. Next : ${getChapterName(novel.reading_history.next_chapter.title)}`;
  }
  
  const handleBookmarkClick = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    
    if (!isAuthenticated || bookmarkLoading) return;
    
    try {
      setBookmarkLoading(true);
      
      if (isBookmarked) {
        await userService.removeNovelBookmark(novel.slug);
        setIsBookmarked(false);
      } else {
        await userService.addNovelBookmark(novel.slug);
        setIsBookmarked(true);
      }
    } catch (error) {
      console.error('Error toggling bookmark:', error);
    } finally {
      setBookmarkLoading(false);
    }
  };
  
  if (isLoading) {
    return (
      <Card sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column'
      }}>
        <Box sx={{ paddingTop: '150%', position: 'relative' }}>
          <Skeleton 
            variant="rectangular" 
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%'
            }} 
          />
        </Box>
        <CardContent>
          <Skeleton variant="text" height={40} />
          <Skeleton variant="text" width="60%" />
          <Box sx={{ display: 'flex', gap: 1, mt: 1 }}>
            <Skeleton variant="rectangular" width={80} height={24} />
            <Skeleton variant="rectangular" width={80} height={24} />
          </Box>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card 
      sx={{ 
        height: '100%', 
        display: 'flex', 
        flexDirection: 'column',
        transition: 'transform 0.3s ease, box-shadow 0.3s ease',
        '&:hover': {
          transform: 'translateY(-5px)',
          boxShadow: '0px 10px 15px -3px rgba(0,0,0,0.1)',
        },
        position: 'relative',
        overflow: 'visible',
      }}
    >
      {unreadChapters && (
        <Tooltip title={tooltip} arrow>
          <Box
            sx={{
              position: 'absolute',
              top: -8,
              left: -8,
              zIndex: 2,
              backgroundColor: 'primary.main',
              color: 'primary.contrastText',
              borderRadius: '12px',
              padding: '2px 8px',
              fontWeight: 'bold',
              boxShadow: '0 4px 4px rgba(0,0,0,0.2)',
            }}
          >
            {unreadChapters > 999 ? '999+' : unreadChapters}
          </Box>
        </Tooltip>
      )}

      {isAuthenticated && (
        <Box
          sx={{
            position: 'absolute',
            right: 8,
            top: 'calc(50% - 8px)',
            zIndex: 10
          }}
        >
          <IconButton
            size="small"
            onClick={handleBookmarkClick}
            sx={{
              bgcolor: 'rgba(0, 0, 0, 0.6)',
              color: 'white',
              '&:hover': {
                bgcolor: 'rgba(0, 0, 0, 0.8)',
              },
              width: 36,
              height: 36,
            }}
          >
            {isBookmarked ? <BookmarkIcon /> : <BookmarkBorderIcon />}
          </IconButton>
        </Box>
      )}

      <CardActionArea 
        sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
        onClick={onClick}
        component={to ? Link : 'div'}
        to={to}
      >
        <Box sx={{ position: 'relative', paddingTop: '150%' }}>
          <CardMedia
            component="img"
            image={novel.prefered_source?.cover_url || defaultCover}
            alt={novel.title}
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover'
            }}
          />
          {/* Language flags */}
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              right: 8,
              display: 'flex',
              gap: 0.5,
              backgroundColor: 'rgba(0, 0, 0, 0.6)',
              borderRadius: 1,
              padding: '2px 4px',
            }}
          >
            {novel.languages.length > 0 ? (
              novel.languages.map((lang) => (
                <Tooltip key={lang} title={languageCodeToName(lang)}>
                  <Typography
                    sx={{
                      fontSize: '1.2rem',
                      lineHeight: 1.2,
                      cursor: 'default',
                    }}
                  >
                    {languageCodeToFlag(lang)}
                  </Typography>
                </Tooltip>
              ))
            ) : (
              <Tooltip title="Unknown language">
                <Typography
                  sx={{
                    fontSize: '1rem',
                    color: '#fff',
                    fontWeight: 'bold',
                  }}
                >
                  ?
                </Typography>
              </Tooltip>
            )}
          </Box>
        </Box>
        <CardContent sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', pt: 1.5, pb: 1 }}>
          <Typography 
            gutterBottom 
            variant="subtitle1" 
            component="div" 
            sx={{ 
              fontWeight: 'medium',
              lineHeight: 1.2,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: 2,
              WebkitBoxOrient: 'vertical',
              mb: 0.5
            }}
          >
            {novel.title}
          </Typography>
          
          {/* Author */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Tooltip title="Authors">
              <PersonIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 16, height: 16 }} />
            </Tooltip>
            <Typography variant="body2" color="text.secondary" noWrap>
              {preferredSource?.authors && preferredSource.authors.length > 0 
                ? preferredSource.authors.join(', ') 
                : 'Unknown'}
            </Typography>
          </Box>
          
          {/* Tags */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Tooltip title="Tags">
              <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 16, height: 16 }} />
            </Tooltip>
            <Typography variant="body2" color="text.secondary" noWrap>
              {preferredSource?.tags && preferredSource.tags.length > 0 ? 
                `${preferredSource.tags.slice(0, 3).join(', ')}${preferredSource.tags.length > 3 ? '...' : ''}` 
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
            <Typography variant="body2" color="text.secondary" 
            sx={{ 
              ml: 0.25,
              fontSize: '0.875rem',
            }}>
              {novel.avg_rating ? novel.avg_rating.toFixed(1) : '0.0'}
              {` (${novel.rating_count > 0 ? formatCount(novel.rating_count) : '0'})`}
            </Typography>
          </Box>
          
          {/* Metadata grid using a proper Grid for alignment */}
          <Grid 
            container 
            spacing={1} 
            sx={{ 
              mt: 'auto', 
              '& .MuiChip-root': { 
                width: '100%',
                height: '24px',
                '& .MuiChip-label': { 
                  px: 0.5, 
                  fontSize: '0.7rem',
                  width: '100%',
                  textAlign: 'center'
                },
                '& .MuiChip-icon': { 
                  fontSize: '0.9rem',
                  ml: 0.5,
                  mr: -0.25
                }
              } 
            }}
          >
            <Grid size={6}>
              <Tooltip title="Total Chapters">
                <Chip 
                  icon={<MenuBookIcon />}
                  label={novel.prefered_source?.chapters_count ? formatCount(novel.prefered_source.chapters_count) : 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>

            <Grid size={6}>
              <Tooltip title="Views">
                <Chip 
                  icon={<VisibilityIcon />}
                  label={novel.total_views !== undefined ? formatCount(novel.total_views) : 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>
            
            <Grid size={12}>
              <Tooltip title="Last Updated">
                <Chip 
                  icon={<UpdateIcon />}
                  label={preferredSource?.last_chapter_update ? formatTimeAgo(toLocalDate(preferredSource?.last_chapter_update)) : 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>
          </Grid>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default BaseNovelCard;
