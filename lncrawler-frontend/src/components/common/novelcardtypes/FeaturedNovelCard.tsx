import React from 'react';
import { Box, Card, Typography, useMediaQuery, useTheme, ButtonBase, Skeleton, Grid2 as Grid } from '@mui/material'; 
import VisibilityIcon from '@mui/icons-material/Visibility';
import CommentIcon from '@mui/icons-material/Comment';
import StarIcon from '@mui/icons-material/Star';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import EditIcon from '@mui/icons-material/Edit';
import { NovelFromSource } from '@models/novels_types';
import { formatTimeAgo, getChapterNameWithNumber } from '@utils/Misc';
import defaultCover from '@assets/default-cover.jpg';
import { Link } from 'react-router-dom';

interface FeaturedNovelCardProps {
  source: NovelFromSource;
  onClick?: () => void;
  isLoading?: boolean;
  to?: string;
}

const FeaturedNovelCard: React.FC<FeaturedNovelCardProps> = ({ source, onClick, isLoading = false, to }) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  
  const coverHeight = isMobile ? 180 : 270;
  const coverWidth = coverHeight * 2/3;

  if (isLoading) {
    return (
      <Grid container spacing={2}>
        <Grid size={{ xs: 4, md: 4, lg: 2 }}>
          <Skeleton variant="rectangular" sx={{ borderRadius: 1.5, width: coverWidth, height: coverHeight, mx: 'auto' }} />
        </Grid>
        <Grid size={{ xs: 8, md: 8, lg: 10 }}>
          <Box sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Skeleton variant="text" height={isMobile ? 28 : 32} width="70%" sx={{ mb: 1 }} />
            <Skeleton variant="text" height={20} sx={{ mb: 0.5 }} />
            <Skeleton variant="text" height={20} sx={{ mb: 0.5 }} />
            <Skeleton variant="text" height={20} width="80%" sx={{ mb: 2 }} />
            
            <Grid container spacing={1} sx={{ mt: 'auto' }}>
              {[...Array(isMobile ? 4 : 6)].map((_, index) => (
                <Grid size={{ xs: 6, sm: 4 }} key={index}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Skeleton variant="circular" width={16} height={16} />
                    <Skeleton variant="text" width="80%" height={18} />
                  </Box>
                </Grid>
              ))}
            </Grid>
          </Box>
        </Grid>
      </Grid>
    );
  }

  const formatter = Intl.NumberFormat('en', { notation: 'compact' });

  return (
    <ButtonBase 
      onClick={onClick}
      component={to ? Link : 'button'}
      to={to}
      sx={{
        width: '100%',
        display: 'block',
        textAlign: 'left',
        transition: 'transform 0.2s',
        '&:hover': {
          transform: 'translateY(-5px)',
        }
      }}
    >
      <Grid container spacing={2}>
        <Grid size={{ xs: 4, md: 4, lg: 2 }}>
          <Card sx={{ 
            borderRadius: 1.5, 
            overflow: 'hidden',
            boxShadow: 2,
            width: coverWidth,
            height: coverHeight,
            mx: 'auto'
          }}>
            <Box
              component="img"
              src={source.cover_min_url || defaultCover}
              alt={source.title}
              sx={{
                height: '100%',
                width: '100%',
                objectFit: 'cover',
              }}
            />
          </Card>
        </Grid>
        <Grid size={{ xs: 8, md: 8, lg: 10 }}>
          <Box sx={{ height: '100%' }}>
            <Typography variant="h6" component="h2" sx={{ fontWeight: 'bold', mb: 1 }}>
              {source.title}
            </Typography>
            
            <Typography 
              variant="body2" 
              sx={{ 
                mb: 2,
                maxHeight: isMobile ? '100px' : '140px',
                overflow: 'auto',
                color: 'text.secondary'
              }}
              dangerouslySetInnerHTML={{ __html: source.synopsis }}
            />
            
            <Grid container spacing={1}>
              <Grid size={{ xs: 6, sm: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <VisibilityIcon fontSize="small" />
                  <Typography variant="caption">
                    {formatter.format(source.novel_id ? 100 : 0)} (All times)
                  </Typography>
                </Box>
              </Grid>
              
              <Grid size={{ xs: 6, sm: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <VisibilityIcon fontSize="small" />
                  <Typography variant="caption">
                    {formatter.format(source.novel_id ? 50 : 0)} (This week)
                  </Typography>
                </Box>
              </Grid>
              
              {!isMobile && (
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <CommentIcon fontSize="small" />
                    <Typography variant="caption">
                      {formatter.format(0)} comments
                    </Typography>
                  </Box>
                </Grid>
              )}
              
              <Grid size={{ xs: 6, sm: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <StarIcon fontSize="small" />
                  <Typography variant="caption">
                    {source.novel_id ? '4.5' : '0'} (Votes: {formatter.format(source.novel_id ? 42 : 0)})
                  </Typography>
                </Box>
              </Grid>
              
              <Grid size={{ xs: 6, sm: 4 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                  <EditIcon fontSize="small" />
                  <Typography variant="caption">
                    {source.last_chapter_update ? formatTimeAgo(new Date(source.last_chapter_update)) : 'Unknown'}
                  </Typography>
                </Box>
              </Grid>
              
              {!isMobile && (
                <Grid size={{ xs: 6, sm: 4 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <BookmarkIcon fontSize="small" />
                    <Typography variant="caption">
                      {getChapterNameWithNumber(source.latest_available_chapter?.title, source.latest_available_chapter?.chapter_id)}
                    </Typography>
                  </Box>
                </Grid>
              )}
            </Grid>
          </Box>
        </Grid>
      </Grid>
    </ButtonBase>
  );
};

export default FeaturedNovelCard;
