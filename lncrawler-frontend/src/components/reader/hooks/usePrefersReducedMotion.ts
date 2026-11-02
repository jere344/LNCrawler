import { useMediaQuery } from '@mui/material';

// True when the system asks for less motion. Transitions and animations in the reader check it.
export function usePrefersReducedMotion(): boolean {
  return useMediaQuery('(prefers-reduced-motion: reduce)');
}
