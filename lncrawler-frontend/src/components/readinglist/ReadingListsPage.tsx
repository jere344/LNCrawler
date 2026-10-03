import { useState, useEffect } from 'react';
import { useDebounce } from '@utils/useDebounce';
import { 
  Typography, Box, Grid, Button, 
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Pagination, InputAdornment, FormControlLabel, Switch
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { readingListService } from '@services/api';
import { ReadingList } from '@models/readinglist_types';
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import CircularProgress from '@mui/material/CircularProgress';
import { useAuth } from '@context/AuthContext';
import { useTranslation } from 'react-i18next';
import ReadingListCard from './ReadingListCard';

const ReadingListsPage = () => {
  const [readingLists, setReadingLists] = useState<ReadingList[]>([]);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newListTitle, setNewListTitle] = useState('');
  const [newListDescription, setNewListDescription] = useState('');
  const [newListIsPublic, setNewListIsPublic] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearchQuery = useDebounce(searchQuery);
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [debouncedSearchQuery]);

  useEffect(() => {
    fetchReadingLists();
  }, [page, debouncedSearchQuery]);

  const fetchReadingLists = async () => {
    try {
      setLoading(true);
      const response = await readingListService.getAllReadingLists(page, 20, debouncedSearchQuery);
      setReadingLists(response.results);
      setTotalPages(response.total_pages);
    } catch (error) {
      console.error('Error fetching reading lists:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateList = async () => {
    if (!newListTitle.trim()) return;
    
    try {
      await readingListService.createReadingList(newListTitle, newListDescription, newListIsPublic);
      setCreateDialogOpen(false);
      setNewListTitle('');
      setNewListDescription('');
      setNewListIsPublic(true);
      fetchReadingLists();
    } catch (error) {
      console.error('Error creating reading list:', error);
    }
  };

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
  };

  const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(event.target.value);
  };

  return (
    <Box sx={{ py: 2 }}>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Typography variant="h4" component="h1">
          {t('readingLists.heading')}
        </Typography>
        {isAuthenticated && (
          <Button 
            variant="contained" 
            startIcon={<AddIcon />}
            onClick={() => setCreateDialogOpen(true)}
          >
            {t('readingLists.createList')}
          </Button>
        )}
      </Box>

      {/* Search Bar */}
      <Box sx={{ mb: 3 }}>
        <TextField
          fullWidth
          placeholder={t('readingLists.searchPlaceholder')}
          variant="outlined"
          value={searchQuery}
          onChange={handleSearchChange}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }
          }}
        />
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : readingLists.length === 0 ? (
        <Box sx={{ textAlign: 'center', my: 4 }}>
          <Typography variant="h6">
            {debouncedSearchQuery 
              ? t('readingLists.noResultsQuery', { query: debouncedSearchQuery })
              : t('readingLists.noResults')}
          </Typography>
          {isAuthenticated && !debouncedSearchQuery && (
            <Button 
              variant="contained" 
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
              sx={{ mt: 2 }}
            >
              {t('readingLists.createFirst')}
            </Button>
          )}
          {!isAuthenticated && !debouncedSearchQuery && (
            <Button 
              variant="contained" 
              component={RouterLink} 
              to="/login"
              sx={{ mt: 2 }}
            >
              {t('readingLists.loginToCreate')}
            </Button>
          )}
        </Box>
      ) : (
        <>
          <Grid container spacing={3}>
            {readingLists.map((list) => (
              <Grid
                key={list.id}
                size={{
                  xs: 12,
                  sm: 6
                }}>
                <ReadingListCard list={list} />
              </Grid>
            ))}
          </Grid>

          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
              <Pagination 
                count={totalPages} 
                page={page} 
                onChange={handlePageChange}
                color="primary"
              />
            </Box>
          )}
        </>
      )}

      {/* Create New List Dialog */}
      <Dialog 
        open={createDialogOpen} 
        onClose={() => setCreateDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{t('readingLists.createTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="title"
            label={t('readingLists.listTitle')}
            type="text"
            fullWidth
            variant="outlined"
            value={newListTitle}
            onChange={(e) => setNewListTitle(e.target.value)}
            required
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            id="description"
            label={t('readingLists.descriptionOptional')}
            type="text"
            fullWidth
            variant="outlined"
            multiline
            rows={4}
            value={newListDescription}
            onChange={(e) => setNewListDescription(e.target.value)}
          />
          <FormControlLabel
            sx={{ mt: 1 }}
            control={
              <Switch
                checked={newListIsPublic}
                onChange={(e) => setNewListIsPublic(e.target.checked)}
              />
            }
            label={newListIsPublic ? t('readingLists.public') : t('readingLists.private')}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreateDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button 
            onClick={handleCreateList} 
            variant="contained"
            disabled={!newListTitle.trim()}
          >
            {t('readingLists.create')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingListsPage;
