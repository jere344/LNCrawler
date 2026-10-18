import { alpha, type Theme } from '@mui/material';
import bannerImage from '../../assets/banner.avif';

/**
 * Background of the home intro box: the banner cropped on its horizon (towers
 * and sunlight sit around 55% of its height), under a left-to-right veil in the
 * paper colour so the text reads on the left and the scenery shows on the right.
 * Shared by HomePage and HomeSkeleton so nothing moves when the page loads.
 */
export const introBannerSx = (theme: Theme) => ({
  backgroundImage: `linear-gradient(to right, ${alpha(theme.palette.background.paper, 0.92)} 0%, ${alpha(theme.palette.background.paper, 0.8)} 45%, ${alpha(theme.palette.background.paper, 0.35)} 100%), url(${bannerImage})`,
  backgroundSize: 'cover',
  // Phones show a tall, narrow slice: keep the soldier and towers in it.
  backgroundPosition: { xs: '80% 55%', sm: 'center 55%' },
  backgroundColor: theme.palette.background.paper,
  textShadow: `0 1px 3px ${alpha(theme.palette.background.paper, 0.9)}`,
});
