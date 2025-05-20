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
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogContentText,
  DialogActions
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { userService } from '@services/user.service';
import { Novel } from '@models/novels_types';
import { useAuth } from '@context/AuthContext';
import BreadcrumbNav from '../common/BreadcrumbNav';
import HistoryIcon from '@mui/icons-material/History';
import ReadingHistoryCard from '../common/novelcardtypes/ReadingHistoryCard';

interface ReadingHistoryResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: Novel[];
}

const ReadingHistoryPage: React.FC = () => {
  const [historyNovels, setHistoryNovels] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [novelToDeleteId, setNovelToDeleteId] = useState<string | null>(null);
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const fetchReadingHistory = async (pageNum = 1) => {
    try {
      setLoading(true);
      setError(null);
      const response: ReadingHistoryResponse = await userService.listReadingHistory(pageNum);
      setHistoryNovels(response.results);
      setTotalPages(response.total_pages);
      setPage(response.current_page);
    } catch (err) {
      console.error('Error fetching reading history:', err);
      setError('Failed to load your reading history. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchReadingHistory(page);
    }
  }, [isAuthenticated, page]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    window.scrollTo(0, 0);
  };

  const openDeleteDialog = (novelId: string) => {
    setNovelToDeleteId(novelId);
    setDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setNovelToDeleteId(null);
  };

  const confirmDelete = async () => {
    if (novelToDeleteId) {
      try {
        const novel = historyNovels.find(n => n.id === novelToDeleteId);
        if (novel?.reading_history) {
          await userService.deleteReadingHistory(novel.reading_history.id);
          setHistoryNovels(prevNovels => 
            prevNovels.filter(novel => novel.id !== novelToDeleteId)
          );
        }
        closeDeleteDialog();
      } catch (err) {
        console.error('Error deleting reading history:', err);
        setError('Failed to delete reading history entry. Please try again later.');
      }
    }
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
        <HistoryIcon sx={{ fontSize: 60, color: 'primary.main', mb: 2 }} />
        <Typography variant="h5" component="h1" gutterBottom>
          Reading History
        </Typography>
        <Typography variant="body1" color="text.secondary" align="center">
          You need to be logged in to access your reading history.
        </Typography>
        <Typography variant="body2" color="text.secondary" align="center">
          Please log in to view your recently read novels.
        </Typography>
      </Paper>
    );
  }

  return (
    <Box sx={{ px: { xs: 2, sm: 3 } }}>
      <BreadcrumbNav
        items={[
          {
            label: "Reading History",
            icon: <HistoryIcon fontSize="inherit" />
          }
        ]}
      />

      <Typography variant="h4" component="h1" gutterBottom>
        Reading History
      </Typography>
      
      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ my: 2 }}>
          {error}
        </Alert>
      ) : historyNovels.length === 0 ? (
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
            Your reading history is empty
          </Typography>
          <Typography variant="body2" color="text.secondary" align="center">
            Start reading novels to track your progress.
          </Typography>
        </Paper>
      ) : (
        <>
          <Box sx={{ mt: 2, mb: 4 }}>
            <Grid container spacing={2}>
              {historyNovels.map((novel) => (
                <Grid key={novel.id} size={12}>
                  <ReadingHistoryCard 
                    novel={novel} 
                    onDelete={openDeleteDialog} 
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

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={closeDeleteDialog}
      >
        <DialogTitle>Remove from history?</DialogTitle>
        <DialogContent>
          <DialogContentText>
            Are you sure you want to remove this novel from your reading history? This action cannot be undone.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDeleteDialog}>Cancel</Button>
          <Button onClick={confirmDelete} color="error" autoFocus>
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingHistoryPage;
