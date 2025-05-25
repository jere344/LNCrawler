import React from 'react';
import { SimilarNovel } from '@models/novels_types';
import BaseNovelCard from './novelcardtypes/BaseNovelCard';
import { Carousel } from 'react-responsive-carousel';
import { Box, Typography, Skeleton, useTheme, useMediaQuery, alpha } from '@mui/material';
import "react-responsive-carousel/lib/styles/carousel.min.css";

interface NovelRecommendationProps {
  similarNovels?: SimilarNovel[];
  loading?: boolean;
}

const NovelRecommendation: React.FC<NovelRecommendationProps> = ({ 
  similarNovels = [], 
  loading = false 
}) => {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const isTablet = useMediaQuery(theme.breakpoints.between('sm', 'md'));
  const isDesktop = useMediaQuery(theme.breakpoints.between('md', 'lg'));
  const isLargeDesktop = useMediaQuery(theme.breakpoints.up('lg'));
  
  // Determine items per slide based on screen size
  const getItemsPerSlide = () => {
    if (isMobile) return 1;
    if (isTablet) return 2;
    if (isDesktop) return 3;
    if (isLargeDesktop) return 4;
    return 4;
  };
  
  const itemsPerSlide = getItemsPerSlide();
  
  // Create array of novel groups for the carousel
  const novelGroups = React.useMemo(() => {
    if (loading || !similarNovels.length) return [];
    
    const groups = [];
    for (let i = 0; i < similarNovels.length; i += itemsPerSlide) {
      groups.push(similarNovels.slice(i, i + itemsPerSlide));
    }
    return groups;
  }, [similarNovels, itemsPerSlide, loading]);

  if (loading) {
    return (
      <Box sx={{ px: 2, py: 2, display: 'flex', gap: 2 }}>
        {Array.from(new Array(itemsPerSlide)).map((_, index) => (
          <Box key={index} sx={{ flex: 1 }}>
            <Skeleton variant="rectangular" width="100%" height={180} />
            <Skeleton variant="text" width="80%" sx={{ mt: 1 }} />
            <Skeleton variant="text" width="60%" />
          </Box>
        ))}
      </Box>
    );
  }

  if (!similarNovels.length) {
    return (
      <Box sx={{ px: 2, py: 1 }}>
        <Typography variant="body1" color="text.secondary">
          No recommendations available for this novel.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ px: 2, pt: 1 }}>
      <Carousel
        showArrows={true}
        showThumbs={false}
        showStatus={false}
        infiniteLoop={novelGroups.length > 1}
        autoPlay={false}
        showIndicators={novelGroups.length > 1}
        emulateTouch={true}
        swipeable={true}
        renderArrowPrev={(clickHandler, hasPrev) => 
          hasPrev && (
            <button
              type="button"
              onClick={clickHandler}
              className="control-arrow control-prev"
              style={{ 
                background: alpha(theme.palette.primary.main, 0.9),
                borderRadius: '50%',
                width: 40,
                height: 40,
                position: 'absolute',
                top: '50%',
                transform: 'translateY(-50%)',
                zIndex: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            />
          )
        }
        renderArrowNext={(clickHandler, hasNext) => 
          hasNext && (
            <button
              type="button"
              onClick={clickHandler}
              className="control-arrow control-next"
              style={{ 
                background: alpha(theme.palette.primary.main, 0.9),
                borderRadius: '50%',
                width: 40,
                height: 40,
                position: 'absolute',
                top: '50%',
                transform: 'translateY(-50%)',
                zIndex: 2,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
              }}
            />
          )
        }
      >
        {novelGroups.map((group, groupIndex) => (
          <Box 
            key={groupIndex} 
            sx={{ 
              display: 'flex', 
              justifyContent: 'center',
              gap: 3,
              px: 1,
              pb: 4
            }}
          >
            {group.map((novel) => (
              <Box key={novel.id} sx={{ flex: 1, maxWidth: `${90/itemsPerSlide}%` }}>
                <BaseNovelCard 
                  novel={novel}
                  to={`/novels/${novel.slug}`} // Add link to novel page
                />
              </Box>
            ))}
          </Box>
        ))}
      </Carousel>
    </Box>
  );
};

export default NovelRecommendation;
