import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip, Skeleton, Grid, Tooltip
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import UpdateIcon from '@mui/icons-material/Update';
import LocalOfferIcon from '@mui/icons-material/LocalOffer';
import PersonIcon from '@mui/icons-material/Person';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { formatTimeAgo, languageCodeToFlag, languageCodeToName, toLocalDate } from '@utils/Misc';

export interface BaseNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
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
  isLoading = false 
}) => {
  const preferredSource = novel.prefered_source;
  
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
        }
      }}
    >
      <CardActionArea 
        sx={{ height: '100%', display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
        onClick={onClick}
      >
        <Box sx={{ position: 'relative', paddingTop: '150%' /* 2:3 aspect ratio */ }}>
          <CardMedia
            component="img"
            loading="lazy"
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
          
          {/* Genres */}
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 0.5 }}>
            <Tooltip title="Genres">
              <LocalOfferIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary', width: 16, height: 16 }} />
            </Tooltip>
            <Typography variant="body2" color="text.secondary" noWrap>
              {preferredSource?.genres && preferredSource.genres.length > 0
                ? `${preferredSource.genres.slice(0, 3).join(', ')}${preferredSource.genres.length > 3 ? '...' : ''}`
                : (
                    preferredSource?.tags && preferredSource.tags.length > 0
                      ? `${preferredSource.tags.slice(0, 3).join(', ')}${preferredSource.tags.length > 3 ? '...' : ''}`
                      : 'Unknown'
                )
              }
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
            <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
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
            <Grid item xs={5}>
              <Tooltip title="Total Chapters">
                <Chip 
                  icon={<MenuBookIcon />}
                  label={novel.total_chapters > 0 ? formatCount(novel.total_chapters) : 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>
            
            <Grid item xs={7}>
              <Tooltip title="Status">
                <Chip 
                  label={preferredSource?.status || 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>

            <Grid item xs={5}>
              <Tooltip title="Views">
                <Chip 
                  icon={<VisibilityIcon />}
                  label={novel.total_views !== undefined ? formatCount(novel.total_views) : 'Unknown'}
                  size="small"
                  variant="outlined"
                />
              </Tooltip>
            </Grid>
            
            <Grid item xs={7}>
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
