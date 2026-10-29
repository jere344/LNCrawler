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
  Stack,
  ToggleButton,
  ToggleButtonGroup,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import { userService } from '@services/user.service';
import { Novel } from '@models/novels_types';
import type { HistoryKind, ListeningHistoryEntry } from '@models/audiobook_types';
import { useAuth } from '@context/AuthContext';
import { useUrlListState } from '@utils/useUrlListState';
import BreadcrumbNav from '../common/BreadcrumbNav';
import HistoryIcon from '@mui/icons-material/History';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import ReadingHistoryCard from '../common/novelcardtypes/ReadingHistoryCard';
import ListeningHistoryCard from './ListeningHistoryCard';
import LoginRequiredPanel from '@components/common/LoginRequiredPanel';
import ConfirmDialog from '@components/common/ConfirmDialog';
import { useTranslation } from 'react-i18next';

// A read entry is a novel card with the kind and the time of the last read.
interface ReadHistoryEntry extends Novel {
  kind: 'read';
  at: string;
}

type HistoryItem = ReadHistoryEntry | ListeningHistoryEntry;

interface ReadingHistoryResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: HistoryItem[];
}

const HISTORY_KINDS: HistoryKind[] = ['all', 'read', 'listen'];

const isHistoryKind = (value: string | null): value is HistoryKind =>
  HISTORY_KINDS.includes(value as HistoryKind);

const ReadingHistoryPage: React.FC = () => {
  const { t } = useTranslation();
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [itemToDelete, setItemToDelete] = useState<HistoryItem | null>(null);
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const { searchParams, setParams } = useUrlListState();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const kindParam = searchParams.get('kind');
  const kind: HistoryKind = isHistoryKind(kindParam) ? kindParam : 'all';

  const fetchReadingHistory = async (pageNum = 1) => {
    try {
      setLoading(true);
      setError(null);
      const response: ReadingHistoryResponse = await userService.listReadingHistory(pageNum, 24, kind);
      setHistoryItems(response.results);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t intentionally omitted; page/auth/kind are the inputs
  }, [isAuthenticated, page, kind]);

  const handleKindChange = (_: React.MouseEvent<HTMLElement>, value: HistoryKind | null) => {
    if (!value || value === kind) return;
    setPage(1);
    setParams({ kind: value === 'all' ? null : value }, { replace: true });
  };

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    window.scrollTo(0, 0);
  };

  const openDeleteDialog = (item: HistoryItem) => {
    setItemToDelete(item);
    setDeleteDialogOpen(true);
  };

  const closeDeleteDialog = () => {
    setDeleteDialogOpen(false);
    setItemToDelete(null);
  };

  const confirmDelete = async () => {
    const target = itemToDelete;
    if (target) {
      try {
        let deleted = false;
        if (target.kind === 'listen') {
          await userService.deleteListeningHistory(target.id);
          deleted = true;
        } else if (target.reading_history) {
          await userService.deleteReadingHistory(target.reading_history.id);
          deleted = true;
        }
        if (deleted) {
          setHistoryItems(prevItems => prevItems.filter(item => item !== target));
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
      <LoginRequiredPanel
        icon={HistoryIcon}
        title={t('history.headingLoggedOut')}
        description={t('history.needLogin')}
        hint={t('history.loginPrompt')}
      />
    );
  }

  const emptyText = kind === 'read'
    ? { title: t('history.emptyRead'), hint: t('history.emptyHint') }
    : kind === 'listen'
      ? { title: t('history.emptyListen'), hint: t('history.emptyListenHint') }
      : { title: t('history.empty'), hint: t('history.emptyHint') };

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

      <ToggleButtonGroup
        exclusive
        size="small"
        value={kind}
        onChange={handleKindChange}
        aria-label={t('history.filterLabel')}
        sx={{ mt: 1 }}
      >
        <ToggleButton value="all">{t('history.filterAll')}</ToggleButton>
        <ToggleButton value="read">{t('history.filterRead')}</ToggleButton>
        <ToggleButton value="listen">{t('history.filterListen')}</ToggleButton>
      </ToggleButtonGroup>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Alert severity="error" sx={{ my: 2 }}>
          {error}
        </Alert>
      ) : historyItems.length === 0 ? (
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
            {emptyText.title}
          </Typography>
          <Typography variant="body2" align="center" sx={{
            color: "text.secondary"
          }}>
            {emptyText.hint}
          </Typography>
        </Paper>
      ) : (
        <>
          <Box sx={{ mt: 2, mb: 4 }}>
            <Grid container spacing={2}>
              {historyItems.map((item) => (
                item.kind === 'listen' ? (
                  <Grid key={`listen-${item.id}`} size={12}>
                    <ListeningHistoryCard
                      entry={item}
                      onDelete={() => openDeleteDialog(item)}
                    />
                  </Grid>
                ) : (
                  <Grid key={`read-${item.id}`} size={12}>
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: 'center', mb: 0.5, color: 'text.secondary' }}>
                      <Box role="img" aria-label={t('history.kindRead')} sx={{ display: 'flex' }}>
                        <MenuBookIcon fontSize="small" />
                      </Box>
                      <Typography variant="caption">{t('history.kindRead')}</Typography>
                    </Stack>
                    <ReadingHistoryCard
                      novel={item}
                      onDelete={() => openDeleteDialog(item)}
                    />
                  </Grid>
                )
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
      <ConfirmDialog
        open={deleteDialogOpen}
        title={t('history.removeTitle')}
        message={itemToDelete?.kind === 'listen' ? t('history.removeListenBody') : t('history.removeBody')}
        confirmLabel={t('common.delete')}
        confirmColor="error"
        onConfirm={confirmDelete}
        onClose={closeDeleteDialog}
      />
    </Box>
  );
};

export default ReadingHistoryPage;
