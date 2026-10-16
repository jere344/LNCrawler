import React, { useState, useEffect } from 'react';
import { 
  Box, 
  Typography, 
  Grid as Grid,
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
import { useTranslation } from 'react-i18next';

interface ReadingHistoryResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: Novel[];
}

const ReadingHistoryPage: React.FC = () => {
  const { t } = useTranslation();
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
      setError(t('history.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchReadingHistory(page);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t intentionally omitted; page/auth are the inputs
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
        setError(t('history.deleteFailed'));
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
          {t('history.headingLoggedOut')}
        </Typography>
        <Typography variant="body1" align="center" sx={{
          color: "text.secondary"
        }}>
          {t('history.needLogin')}
        </Typography>
        <Typography variant="body2" align="center" sx={{
          color: "text.secondary"
        }}>
          {t('history.loginPrompt')}
        </Typography>
      </Paper>
    );
  }

  return (
    <Box sx={{ px: { xs: 2, sm: 3 } }}>
      <BreadcrumbNav
        items={[
          {
            label: t('history.heading'),
            icon: <HistoryIcon fontSize="inherit" />
          }
        ]}
      />

      <Typography variant="h4" component="h1" gutterBottom>
        {t('history.heading')}
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
          <Typography variant="h6" align="center" sx={{
            color: "text.secondary"
          }}>
            {t('history.empty')}
          </Typography>
          <Typography variant="body2" align="center" sx={{
            color: "text.secondary"
          }}>
            {t('history.emptyHint')}
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
        <DialogTitle>{t('history.removeTitle')}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('history.removeBody')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDeleteDialog}>{t('common.cancel')}</Button>
          <Button onClick={confirmDelete} color="error" autoFocus>
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingHistoryPage;
