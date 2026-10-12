import { useEffect } from 'react';
import { Box, Button, Typography } from '@mui/material';
import { useRouteError } from 'react-router-dom';
import { reportError } from '@services/errorReporter';

/**
 * Route-level errorElement for unexpected loader/render failures. Expected
 * failures (e.g. a missing novel) are returned as result objects instead, so
 * the page keeps its own translated message and inline layout.
 */
const RouteError = () => {
  const error = useRouteError();

  useEffect(() => {
    reportError(error, { context: 'route error' });
  }, [error]);

  return (
    <Box sx={{ textAlign: 'center', py: 8 }}>
      <Typography variant="h5" gutterBottom>
        Something went wrong.
      </Typography>
      <Button variant="contained" onClick={() => window.location.reload()}>
        Reload
      </Button>
    </Box>
  );
};

export default RouteError;
