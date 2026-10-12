import { Box, CircularProgress } from '@mui/material';

/** Initial-load fallback while a route loader runs (React Router HydrateFallback). */
const RouteSpinner = () => (
  <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
    <CircularProgress />
  </Box>
);

export default RouteSpinner;
