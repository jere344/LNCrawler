import React from 'react';
import { Novel, SimilarNovel } from '@models/novels_types';
import BaseNovelCard from './novelcardtypes/BaseNovelCard';
import { Box, Typography, useTheme, useMediaQuery, IconButton, alpha } from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import { getNovelSourceLink } from '@utils/Misc';
import { useTranslation } from 'react-i18next';

interface NovelRecommendationProps {
  similarNovels?: SimilarNovel[];
  loading?: boolean;
}

const NovelRecommendation: React.FC<NovelRecommendationProps> = ({ 
  similarNovels = [], 
  loading = false 
}) => {
  const theme = useTheme();
  const { t } = useTranslation();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const isTablet = useMediaQuery(theme.breakpoints.between('sm', 'md'));
  const isDesktop = useMediaQuery(theme.breakpoints.between('md', 'lg'));

  // Determine items per view based on screen size
  const getItemsPerSlide = () => {
    if (isMobile || isTablet) return 2;
    if (isDesktop) return 4;
    return 5;
  };

  const itemsPerSlide = getItemsPerSlide();

  const scrollRef = React.useRef<HTMLDivElement>(null);
  const [canScrollPrev, setCanScrollPrev] = React.useState(false);
  const [canScrollNext, setCanScrollNext] = React.useState(false);

  const updateScrollState = React.useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    setCanScrollPrev(el.scrollLeft > 1);
    setCanScrollNext(el.scrollLeft + el.clientWidth < el.scrollWidth - 1);
  }, []);

  React.useEffect(() => {
    updateScrollState();
    const el = scrollRef.current;
    if (!el || !window.ResizeObserver) return;
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(el);
    return () => observer.disconnect();
  }, [loading, similarNovels.length, updateScrollState]);

  const scrollByCards = (direction: 1 | -1) => {
    const el = scrollRef.current;
    const first = el?.firstElementChild as HTMLElement | null;
    if (!el || !first) return;
    const gap = parseFloat(getComputedStyle(el).columnGap) || 0;
    const cardStep = first.offsetWidth + gap;
    const cards = Math.max(1, Math.floor(el.clientWidth / cardStep) - 1);
    el.scrollBy({ left: direction * cards * cardStep, behavior: 'smooth' });
  };

  if (loading) {
    return (
      <Box sx={{ px: 2, pt: 1, position: 'relative' }}>
        <Box sx={{ display: 'flex', gap: 3, overflowX: 'hidden', px: 1, pb: 4 }}>
          {Array.from(new Array(itemsPerSlide)).map((_, index) => (
            <Box
              key={index}
              sx={{
                flexShrink: 0,
                width: { xs: '50%', sm: '50%', md: '25%', lg: '20%' },
                marginTop: 1,
              }}
            >
              <BaseNovelCard novel={{} as Novel} isLoading />
            </Box>
          ))}
        </Box>
      </Box>
    );
  }

  if (!similarNovels.length) {
    return (
      <Box sx={{ px: 2, py: 1 }}>
        <Typography variant="body1" sx={{
          color: "text.secondary"
        }}>
          {t('recommendation.empty')}
        </Typography>
      </Box>
    );
  }

  const arrowSx = {
    position: 'absolute',
    top: '42%',
    transform: 'translateY(-50%)',
    zIndex: 3,
    backgroundColor: alpha(theme.palette.primary.main, 0.9),
    color: theme.palette.primary.contrastText,
    transition: 'opacity 0.2s',
    '&:hover': { backgroundColor: theme.palette.primary.main },
    '&.Mui-disabled': { opacity: 0, pointerEvents: 'none' },
  } as const;

  return (
    <Box sx={{ px: 2, pt: 1, position: 'relative' }}>
      {!isMobile && (
        <IconButton
          onClick={() => scrollByCards(-1)}
          disabled={!canScrollPrev}
          sx={{ ...arrowSx, left: 0 }}
          aria-label={t('common.previous', 'Previous')}
        >
          <ChevronLeftIcon />
        </IconButton>
      )}
      <Box
        ref={scrollRef}
        onScroll={updateScrollState}
        sx={{
          display: 'flex',
          gap: 3,
          overflowX: 'auto',
          scrollSnapType: 'x mandatory',
          px: 1,
          pb: 4,
          scrollbarWidth: 'none',
          '&::-webkit-scrollbar': { display: 'none' },
        }}
      >
        {similarNovels.map((novel) => (
          <Box
            key={novel.id}
            sx={{
              flexShrink: 0,
              width: { xs: '50%', sm: '50%', md: '25%', lg: '20%' },
              scrollSnapAlign: 'start',
              marginTop: 1,
            }}
          >
            <BaseNovelCard 
              novel={novel}
              {...getNovelSourceLink(novel)}
            />
          </Box>
        ))}
      </Box>
      {!isMobile && (
        <IconButton
          onClick={() => scrollByCards(1)}
          disabled={!canScrollNext}
          sx={{ ...arrowSx, right: 0 }}
          aria-label={t('common.next', 'Next')}
        >
          <ChevronRightIcon />
        </IconButton>
      )}
    </Box>
  );
};

export default NovelRecommendation;
