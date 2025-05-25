import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Typography, 
  Grid2 as Grid,
  Pagination,
  Alert,
  CircularProgress,
  useMediaQuery,
  Paper,
  Divider
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { userService } from '@services/user.service';
import BaseNovelCard from '@components/common/novelcardtypes/BaseNovelCard';
import { Novel, NovelListResponse } from '@models/novels_types';
import { useAuth } from '@context/AuthContext';
import BreadcrumbNav from '../common/BreadcrumbNav';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import NovelRecommendation from '@components/common/NovelRecommendation';

const LibraryPage: React.FC = () => {
  const [bookmarkedNovels, setBookmarkedNovels] = useState<Novel[]>([]);
  const [recommendations, setRecommendations] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const fetchBookmarkedNovels = async (pageNum = 1) => {
    try {
      setLoading(true);
      setError(null);
      const response: NovelListResponse = await userService.listBookmarkedNovels(pageNum);
      setBookmarkedNovels(response.results);
      setRecommendations(response.recommendations || []);
      setTotalPages(response.total_pages);
      setPage(response.current_page);
    } catch (err) {
      console.error('Error fetching bookmarks:', err);
      setError('Failed to load your bookmarked novels. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchBookmarkedNovels(page);
    }
  }, [isAuthenticated, page]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    window.scrollTo(0, 0);
  };


  if (!isAuthenticated) {
    return (
      <Paper 
        elevation={3}
        sx={{ 
          p: 4, 
          display: 'flex', 
          flexDirection: 'column', 
          alignItems: 'center',
          gap: 2,
          mx: 'auto',
          maxWidth: 'md',
          my: 4
        }}
      >
        <LibraryBooksIcon sx={{ fontSize: 60, color: 'primary.main', mb: 2 }} />
        <Typography variant="h5" component="h1" gutterBottom>
          Your Library
        </Typography>
        <Typography variant="body1" color="text.secondary" align="center">
          You need to be logged in to access your library.
        </Typography>
        <Typography variant="body2" color="text.secondary" align="center">
          Please log in to view your bookmarked novels.
        </Typography>
      </Paper>
    );
  }

  return (
    <Box sx={{ px: { xs: 2, sm: 3 } }}>
      <BreadcrumbNav
        items={[
          {
            label: "Library",
            icon: <LibraryBooksIcon fontSize="inherit" />
          }
        ]}
      />

      <Typography variant="h4" component="h1" gutterBottom>
        Your Library
      </Typography>
      
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ my: 2 }}>
          {error}
        </Alert>
      ) : (
        <>
          {bookmarkedNovels.length === 0 ? (
            <Paper 
              elevation={2}
              sx={{ 
                p: 4, 
                display: 'flex', 
                flexDirection: 'column', 
                alignItems: 'center',
                gap: 2,
                my: 4
              }}
            >
              <Typography variant="h6" color="text.secondary" align="center">
                Your library is empty
              </Typography>
              <Typography variant="body2" color="text.secondary" align="center">
                Bookmark novels to add them to your library.
              </Typography>
            </Paper>
          ) : (
            <>
              <Box sx={{ mt: 2, mb: 4 }}>
                <Typography variant="h5" sx={{ mb: 2 }}>Your Bookmarks</Typography>
                <Grid container spacing={3}>
                  {bookmarkedNovels.map((novel) => (
                    <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                      <BaseNovelCard 
                        novel={novel} 
                        to={`/novels/${novel.slug}`}
                      />
                    </Grid>
                  ))}
                </Grid>
              </Box>
              
              {totalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
                  <Pagination 
                    count={totalPages} 
                    page={page} 
                    onChange={handlePageChange}
                    color="primary"
                    size={isMobile ? "small" : "medium"}
                  />
                </Box>
              )}
            </>
          )}

          <Divider sx={{ my: 8 }} />

          {/* Display recommendations if available */}
          {recommendations.length > 0 && (
            <Box sx={{ mt: 4 }}>
              <Typography variant="h5" sx={{ mb: 2 }}>Recommended for You</Typography>
            </Box>
          )}
          {recommendations.length > 0 && (
            <NovelRecommendation 
              similarNovels={recommendations.map(novel => ({...novel, similarity: 0}))} 
              loading={false}
            />
          )}
        </>
      )}
    </Box>
  );
};

export default LibraryPage;
