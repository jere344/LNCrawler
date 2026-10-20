import { Container, Box, Paper, Skeleton, Grid, alpha, useTheme } from '@mui/material';

const SourceDetailSkeleton = () => {
  const theme = useTheme();
  return (
    <Container maxWidth="lg">
      <Box sx={{ mb: 3, mt: 1 }}>
        <Skeleton variant="text" width={220} height={24} animation="wave" />
      </Box>

      <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
        <Skeleton variant="rectangular" width={120} height={36} sx={{ borderRadius: '20px' }} />
      </Box>

      <Paper 
        elevation={0}
        sx={{ 
          p: 0,
          overflow: 'hidden',
          borderRadius: 3,
          mb: 4,
          position: 'relative',
          background: `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.3)} 0%, ${alpha(theme.palette.primary.main, 0.1)} 100%)`,
        }}
      >
        <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
          <Grid container spacing={3}>
            <Grid size={{ xs: 12, md: 4, lg: 3 }}>
              <Box
                sx={{
                  position: 'relative',
                  width: '100%',
                  paddingTop: '150%',
                  borderRadius: 2,
                  overflow: 'hidden',
                  boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
                  border: `4px solid ${theme.palette.common.white}`,
                }}
              >
                <Skeleton 
                  variant="rectangular" 
                  width="100%" 
                  height="100%" 
                  sx={{ position: 'absolute', top: 0, left: 0 }} 
                  animation="wave"
                />
              </Box>
            </Grid>
              
            <Grid size={{ xs: 12, md: 8, lg: 9 }}>
              <Skeleton variant="text" width="80%" height={60} sx={{ mb: 1 }} animation="wave" />
              <Skeleton variant="text" width="60%" height={40} sx={{ mb: 3 }} animation="wave" />
                
              <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
                  <Skeleton variant="rectangular" width={150} height={36} sx={{ borderRadius: 6 }} animation="wave" />
                  <Skeleton variant="rectangular" width={100} height={36} sx={{ borderRadius: 6 }} animation="wave" />
                </Box>
                  
                <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
                  <Skeleton variant="rectangular" width={200} height={30} animation="wave" />
                </Box>
              </Box>
                
              <Box 
                sx={{ 
                  height: '2px', 
                  background: `linear-gradient(to right, ${alpha(theme.palette.common.white, 0.8)}, transparent)`,
                  mb: 2.5,
                  mt: 0.5,
                }} 
              />
                
              <Grid container spacing={2} sx={{ mb: 3 }}>
                <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                  <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 2 }} animation="wave" />
                </Grid>
                  
                <Grid size={{ xs: 12, sm: 6, md: 6 }}>
                  <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 2 }} animation="wave" />
                </Grid>
              </Grid>
                
              <Box sx={{ mb: 3 }}>
                <Skeleton variant="text" width={150} height={20} sx={{ mb: 1 }} animation="wave" />
                <Box sx={{ display: 'flex', gap: 2 }}>
                  <Skeleton variant="rectangular" width={150} height={40} sx={{ borderRadius: '20px' }} animation="wave" />
                  <Skeleton variant="rectangular" width={150} height={40} sx={{ borderRadius: '20px' }} animation="wave" />
                </Box>
              </Box>
                
              <Box sx={{ 
                width: '100%', 
                display: 'flex', 
                flexDirection: { xs: 'column', sm: 'row' }, 
                gap: 1,
                mb: 1
              }}>
                <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
                <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
                <Skeleton variant="rectangular" width="100%" height={70} sx={{ borderRadius: '12px' }} animation="wave" />
              </Box>
            </Grid>
          </Grid>
        </Box>
      </Paper>
        
      {/* Update Button Section Skeleton */}
      <Paper 
        elevation={3} 
        sx={{ 
          p: { xs: 2, md: 3 }, 
          mb: 4, 
          borderRadius: 3,
          background: theme.palette.mode === 'dark' 
            ? alpha(theme.palette.background.paper, 0.95)
            : theme.palette.background.default,
        }}
      >
        <Skeleton variant="rectangular" width="100%" height={100} sx={{ borderRadius: 2 }} animation="wave" />
      </Paper>

      {/* Tags Section Skeleton */}
      <Paper 
        elevation={3} 
        sx={{ 
          p: 3, 
          mb: 4, 
          borderRadius: 3,
          background: theme.palette.mode === 'dark' 
            ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
            : theme.palette.background.paper,
        }}
      >
        <Grid container spacing={3}>
          <Grid size={{ xs: 12, md: 6 }}>
            <Skeleton variant="text" width={100} height={30} sx={{ mb: 2 }} animation="wave" />
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {[...Array(5)].map((_, i) => (
                <Skeleton key={i} variant="rectangular" width={80} height={32} sx={{ borderRadius: 4 }} animation="wave" />
              ))}
            </Box>
          </Grid>
            
          <Grid size={{ xs: 12, md: 6 }}>
            <Skeleton variant="text" width={100} height={30} sx={{ mb: 2 }} animation="wave" />
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
              {[...Array(7)].map((_, i) => (
                <Skeleton key={i} variant="rectangular" width={60} height={32} sx={{ borderRadius: 4 }} animation="wave" />
              ))}
            </Box>
          </Grid>
        </Grid>
      </Paper>
        
      {/* Synopsis Section Skeleton */}
      <Paper 
        elevation={3} 
        sx={{ 
          p: 3, 
          mb: 4, 
          borderRadius: 3,
          background: theme.palette.mode === 'dark' 
            ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
            : theme.palette.background.paper,
        }}
      >
        <Skeleton variant="text" width={150} height={40} sx={{ mb: 2 }} animation="wave" />
        {[...Array(6)].map((_, i) => (
          <Skeleton key={i} variant="text" width="100%" height={20} sx={{ mb: 1 }} animation="wave" />
        ))}
      </Paper>

      {/* Comments Section Skeleton */}
      <Paper 
        elevation={3} 
        sx={{ 
          p: 3,
          mb: 4, 
          borderRadius: 3,
          background: theme.palette.mode === 'dark' 
            ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
            : theme.palette.background.paper,
        }}
      >
        <Skeleton variant="text" width={150} height={40} sx={{ mb: 2 }} animation="wave" />
        <Skeleton variant="rectangular" width="100%" height={150} sx={{ mb: 2, borderRadius: 2 }} animation="wave" />
        {[...Array(3)].map((_, i) => (
          <Box key={i} sx={{ mb: 3 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
              <Skeleton variant="circular" width={40} height={40} sx={{ mr: 2 }} animation="wave" />
              <Box>
                <Skeleton variant="text" width={120} height={24} animation="wave" />
                <Skeleton variant="text" width={80} height={16} animation="wave" />
              </Box>
            </Box>
            <Skeleton variant="rectangular" width="100%" height={60} sx={{ borderRadius: 1 }} animation="wave" />
          </Box>
        ))}
      </Paper>
    </Container>
  );
};

export default SourceDetailSkeleton;
