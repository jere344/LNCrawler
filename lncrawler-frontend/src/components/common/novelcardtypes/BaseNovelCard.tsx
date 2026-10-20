import React, { useState } from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Skeleton, Tooltip,
  Grid as Grid
} from '@mui/material';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import PersonIcon from '@mui/icons-material/Person';
import { Novel } from '@models/novels_types';
import { formatCount, getChapterName, languageFlagUrl, languageCodeToName, getNovelDisplayTitle, novelCoverUrl } from '@utils/Misc';
import { useAuth } from '@context/AuthContext';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { DmcaBadge } from '@components/common/DmcaBadge';
import { Link } from 'react-router-dom';
import type { To } from 'react-router-dom';
import BookmarkButton from '@components/common/BookmarkButton';
import MarkAsReadButton from '@components/common/MarkAsReadButton';
import CompactAddToListButton from '@components/readinglist/CompactAddToListButton';
import NovelStatsChips from './NovelStatsChips';
import { useTranslation } from 'react-i18next';

export interface BaseNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
  to?: To;
  state?: unknown;
  hideUserState?: boolean;
  // Show the per-user rating instead of the community average (library views).
  ratingMode?: 'average' | 'user';
  // When provided, the rating becomes interactive and calls back with the value.
  onRate?: (value: number | null) => void;
  ratingLabel?: string;
  // Hide the rating row entirely (e.g. public mirror when ratings are private).
  showRating?: boolean;
}

export const BaseNovelCard: React.FC<BaseNovelCardProps> = ({ 
  novel, 
  onClick, 
  isLoading = false,
  to,
  state,
  hideUserState = false,
  ratingMode = 'average',
  onRate,
  ratingLabel,
  showRating = true
}) => {
  const preferredSource = novel.reading_source ?? novel.prefered_source;
  const { isAuthenticated } = useAuth();
  const { isBlurred, revealHandler } = useAdultContent();
  const blurred = isBlurred(novel.is_adult, novel.id);
  const { t } = useTranslation();
  const [localUnreadChapters, setLocalUnreadChapters] = useState<number | null>(() => {
    if (novel.reading_history) {
      // Only chapters with content count (backend supplies the count), so
      // gaps left by failed downloads don't inflate the badge.
      const unread = novel.reading_history.unread_chapters;
      if (unread === undefined || unread === null) {
        return null;
      }
      return unread > 0 ? unread : null;
    }
    else if (novel.is_bookmarked && novel.prefered_source) {
      const available = novel.prefered_source.available_chapters_count
        ?? novel.prefered_source.latest_available_chapter?.chapter_id;
      return available && available > 0 ? available : null;
    }
    return null;
  });
  
  const unreadChapters = localUnreadChapters;

  const handleMarkAsRead = () => {
    setLocalUnreadChapters(null);
  };

  let tooltip = "";
  if (unreadChapters) {
    const unreadLabel = t('units.unreadChapters', { count: unreadChapters });
    tooltip = novel.reading_history?.next_chapter
      ? t('cards.unreadTooltip', { unread: unreadLabel, next: getChapterName(novel.reading_history.next_chapter.title) })
      : unreadLabel;
  }
  
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

  // Define button positions
  const bookmarkButtonSx = {
    position: 'absolute',
    right: 8,
    top: 'calc(50%)',
    zIndex: 10
  };
  
  const markAsReadButtonSx = {
    position: 'absolute',
    right: '88px',
    top: 'calc(50%)',
    zIndex: 10
  };
  
  const addToListButtonSx = {
    position: 'absolute',
    right: '48px',
    top: 'calc(50%)',
    zIndex: 10
  };

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
          zIndex: 2,
        },
        position: 'relative',
        overflow: 'visible',
      }}
    >
      {unreadChapters && !hideUserState && (
        <Tooltip title={tooltip} arrow>
          <Box
            sx={{
              position: 'absolute',
              top: 8,
              left: 8,
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

      {isAuthenticated && !hideUserState && (
        <>
          <BookmarkButton 
            isBookmarked={novel.is_bookmarked || false}
            slug={novel.slug}
            customSx={bookmarkButtonSx}
          />
          <MarkAsReadButton
            novel={novel}
            onMarkAsRead={handleMarkAsRead}
            customSx={markAsReadButtonSx}
          />
          <CompactAddToListButton
            novelId={novel.id}
            novelTitle={novel.title}
            displayTitle={getNovelDisplayTitle(novel)}
            customSx={addToListButtonSx}
          />
        </>
      )}

      <CardActionArea 
        sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
        onClick={onClick}
        component={to ? Link : 'div'}
        to={to}
        state={to ? state : undefined}
      >
        <Box sx={{ position: 'relative', paddingTop: '150%' }}>
          <CardMedia
            component="img"
            image={novelCoverUrl(preferredSource)}
            alt={getNovelDisplayTitle(novel)}
            onClick={blurred ? revealHandler(novel.id) : undefined}
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
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
          {novel.is_dmca && <DmcaBadge bottom={8} />}
          {/* Language flags */}
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              right: 0,
              display: 'flex',
              gap: 0.5,
              boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
              border: '1px solid rgb(0, 0, 0)',
              borderRadius: 1,
              alignItems: 'center', // Align items vertically
            }}
          >
            {novel.languages.length > 0 ? (
              novel.languages.map((lang) => (
                <Tooltip key={lang} title={languageCodeToName(t, lang)}>
                  <img 
                    src={languageFlagUrl(lang)} 
                    alt={languageCodeToName(t, lang)}
                    style={{ 
                      width: '30px',
                      height: '20px',
                      objectFit: 'cover',
                      borderRadius: '2px',
                    }}
                  />
                </Tooltip>
              ))
            ) : (
              <Tooltip title={t('cards.unknownLanguage')}>
                <Typography
                  sx={{
                    fontSize: '0.8rem', // Adjusted size for consistency
                    color: '#fff',
                    fontWeight: 'bold',
                    lineHeight: 1, // Ensure '?' is vertically centered if it's taller
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
              mb: 0.5,
              textAlign: 'left',
            }}
          >
            {getNovelDisplayTitle(novel)}
          </Typography>
          
          {/* Author */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Tooltip title={t('cards.authors')}>
              <PersonIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 16, height: 16 }} />
            </Tooltip>
            <Typography variant="body2" noWrap sx={{
              color: "text.secondary"
            }}>
              {preferredSource?.authors && preferredSource.authors.length > 0 
                ? preferredSource.authors.join(', ') 
                : t('common.unknown')}
            </Typography>
          </Box>
          
          {/* Tags */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Tooltip title={t('cards.tags')}>
              <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 16, height: 16 }} />
            </Tooltip>
            <Typography variant="body2" noWrap sx={{
              color: "text.secondary"
            }}>
              {preferredSource?.tags && preferredSource.tags.length > 0 ? 
                `${preferredSource.tags.slice(0, 3).join(', ')}${preferredSource.tags.length > 3 ? '...' : ''}` 
                : t('common.unknown')}
            </Typography>
          </Box>
          
          {/* Rating */}
          {showRating && (
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            {ratingMode === 'user' ? (
              <>
                <Rating
                  value={novel.user_rating || 0}
                  readOnly={!onRate}
                  size="small"
                  onChange={(_, value) => onRate?.(value)}
                />
                <Typography
                  variant="body2"
                  sx={{
                    color: "text.secondary",
                    ml: 0.25,
                    fontSize: '0.75rem',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    height: '1.2em'
                  }}>
                  {novel.user_rating ? `${novel.user_rating}/5` : (ratingLabel ?? '—')}
                </Typography>
              </>
            ) : (
              <>
                <Rating 
                  value={novel.avg_rating || 0} 
                  precision={0.5} 
                  readOnly 
                  size="small" 
                />
                <Typography
                  variant="body2"
                  sx={{
                    color: "text.secondary",
                    ml: 0.25,
                    fontSize: '0.875rem',
                    overflow: 'hidden',
                    height: '1.2em'
                  }}>
                  {novel.avg_rating ? novel.avg_rating.toFixed(1) : '0.0'}
                  {` (${novel.rating_count > 0 ? formatCount(novel.rating_count) : '0'})`}
                </Typography>
              </>
            )}
          </Box>
          )}
          
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
            <NovelStatsChips novel={novel} source={preferredSource} asGrid />
          </Grid>
        </CardContent>
      </CardActionArea>
    </Card>
  );
};

export default BaseNovelCard;
