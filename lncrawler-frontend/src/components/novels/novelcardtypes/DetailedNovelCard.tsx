import React from 'react';
import { 
  Card, CardActionArea, CardMedia, CardContent, 
  Typography, Box, Rating, Chip, Divider
} from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import LanguageIcon from '@mui/icons-material/Language';
import SourceIcon from '@mui/icons-material/Source';
import defaultCover from '@assets/default-cover.jpg';
import { Novel } from '@models/novels_types';
import { formatCount } from './BaseNovelCard';

interface DetailedNovelCardProps {
  novel: Novel;
  onClick?: () => void;
  isLoading?: boolean;
}

const DetailedNovelCard: React.FC<DetailedNovelCardProps> = ({ novel, onClick }) => {
  const preferredSource = novel.prefered_source;
  
  return (
    <Card 
      sx={{ 
        display: 'flex',
        flexDirection: 'column',
        transition: 'box-shadow 0.3s ease',
        '&:hover': {
          boxShadow: '0px 8px 15px -5px rgba(0,0,0,0.2)',
        },
        height: 180,
      }}
    >
      <CardActionArea onClick={onClick}>
        <Box sx={{ display: 'flex', height: '100%' }}>
          <Box sx={{ width: 120, position: 'relative' }}>
            <CardMedia
              component="img"
              sx={{ 
                width: 120, 
                height: '180px', // 2:3 aspect ratio
                objectFit: 'cover' 
              }}
              image={preferredSource?.cover_url || defaultCover}
              alt={novel.title}
            />
          </Box>
          <CardContent sx={{ flex: '1' }}>
            <Typography 
              variant="h6" 
              component="div" 
              sx={{ 
                fontWeight: 'bold',
                mb: 1
              }}
            >
              {novel.title}
            </Typography>
            
            {preferredSource && (
              <Box sx={{ mb: 1 }}>
                {preferredSource.authors?.length > 0 && (
                  <Typography variant="body2" color="text.secondary">
                    By: {preferredSource.authors.join(", ")}
                  </Typography>
                )}
                
                <Box sx={{ display: 'flex', alignItems: 'center', mt: 0.5 }}>
                  <Rating 
                    value={novel.avg_rating || 0} 
                    precision={0.5} 
                    readOnly 
                    size="small" 
                  />
                  <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                    {novel.avg_rating?.toFixed(1) || 'N/A'}
                    {novel.rating_count > 0 && ` (${formatCount(novel.rating_count)})`}
                  </Typography>
                </Box>
                
                {preferredSource.synopsis && (
                  <Typography 
                    variant="body2" 
                    sx={{ 
                      mt: 1,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      display: '-webkit-box',
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: 'vertical'
                    }}
                    dangerouslySetInnerHTML={{ __html: preferredSource.synopsis || 'No synopsis available' }} />
                )}
              </Box>
            )}

            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
              {preferredSource?.status && (
                <Chip 
                  label={preferredSource.status}
                  size="small"
                  color={preferredSource.status.toLowerCase() === 'completed' ? 'success' : 'default'}
                />
              )}
              
              {novel.total_views !== undefined && (
                <Chip 
                  icon={<VisibilityIcon fontSize="small" />}
                  label={`${formatCount(novel.total_views)}`}
                  size="small"
                  variant="outlined"
                />
              )}
              
              {novel.weekly_views !== undefined && novel.weekly_views > 0 && (
                <Chip 
                  icon={<TrendingUpIcon fontSize="small" />}
                  label={`${formatCount(novel.weekly_views)} weekly`}
                  size="small"
                  color="primary"
                  variant="outlined"
                />
              )}
              
              {novel.sources_count > 0 && (
                <Chip 
                  icon={<SourceIcon fontSize="small" />}
                  label={`${novel.sources_count} sources`}
                  size="small"
                  variant="outlined"
                />
              )}
              
              {novel.total_chapters > 0 && (
                <Chip 
                  icon={<MenuBookIcon fontSize="small" />}
                  label={`${novel.total_chapters} chapters`}
                  size="small"
                  variant="outlined"
                />
              )}
              
              {preferredSource?.language && (
                <Chip 
                  icon={<LanguageIcon fontSize="small" />}
                  label={preferredSource.language}
                  size="small"
                  variant="outlined"
                />
              )}
            </Box>
            
            {preferredSource?.genres && preferredSource.genres.length > 0 && (
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, mt: 1.5 }}>
                {preferredSource.genres.slice(0, 3).map((genre, index) => (
                  <Chip 
                    key={index}
                    label={genre}
                    size="small"
                    color="secondary"
                    variant="outlined"
                  />
                ))}
                {preferredSource.genres.length > 3 && (
                  <Typography variant="caption" sx={{ alignSelf: 'center' }}>
                    +{preferredSource.genres.length - 3} more
                  </Typography>
                )}
              </Box>
            )}
          </CardContent>
        </Box>
      </CardActionArea>
    </Card>
  );
};

export default DetailedNovelCard;
