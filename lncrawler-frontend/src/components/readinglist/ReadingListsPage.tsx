import { useState, use } from 'react';
import { useLoaderData, useRevalidator } from 'react-router-dom';
import { useUrlListState, useUrlSearch } from '@utils/useUrlListState';
import {
    Typography,
  Box,
  Grid,
  Alert, Button, 
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Pagination, InputAdornment, FormControlLabel, Switch
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { readingListService } from '@services/api';
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import { useAuth } from '@context/AuthContext';
import { useTranslation } from 'react-i18next';
import ReadingListCard from './ReadingListCard';
import type { AsyncData, ReadingListsLoaderData } from '../../router/loaders';

const ReadingListsPage = () => {
  const { data: readingListsPromise } = useLoaderData() as AsyncData<ReadingListsLoaderData>;
  const loaderData = use(readingListsPromise);
  const revalidator = useRevalidator();
  const { searchParams, setParams } = useUrlListState();

  const searchQueryParam = searchParams.get('q') || '';
  const page = Number(searchParams.get('page')) || 1;
  const readingLists = loaderData.ok ? loaderData.data.results : [];
  const totalPages = loaderData.ok ? loaderData.data.total_pages : 1;

  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newListTitle, setNewListTitle] = useState('');
  const [newListDescription, setNewListDescription] = useState('');
  const [newListIsPublic, setNewListIsPublic] = useState(true);
  // The debounced search is mirrored into the URL so the loader owns the request.
  const [searchQuery, setSearchQuery] = useUrlSearch('q');
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();

  const handleCreateList = async () => {
    if (!newListTitle.trim()) return;
    
    try {
      await readingListService.createReadingList(newListTitle, newListDescription, newListIsPublic);
      setCreateDialogOpen(false);
      setNewListTitle('');
      setNewListDescription('');
      setNewListIsPublic(true);
      revalidator.revalidate();
    } catch (error) {
      console.error('Error creating reading list:', error);
    }
  };

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setParams({ page: String(value) });
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

      {!loaderData.ok ? (
        <Alert severity="error" sx={{ my: 4 }}>
          {t('readingLists.loadFailed', 'Failed to load reading lists. Please try again later.')}
        </Alert>
      ) : readingLists.length === 0 ? (
        <Box sx={{ textAlign: 'center', my: 4 }}>
          <Typography variant="h6">
            {searchQueryParam 
              ? t('readingLists.noResultsQuery', { query: searchQueryParam })
              : t('readingLists.noResults')}
          </Typography>
          {isAuthenticated && !searchQueryParam && (
            <Button 
              variant="contained" 
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
              sx={{ mt: 2 }}
            >
              {t('readingLists.createFirst')}
            </Button>
          )}
          {!isAuthenticated && !searchQueryParam && (
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
