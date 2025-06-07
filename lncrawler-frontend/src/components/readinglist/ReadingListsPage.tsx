import { useState, useEffect } from 'react';
import { 
  Typography, Box, Grid, Button, 
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Pagination, InputAdornment
} from '@mui/material';
import { Link as RouterLink } from 'react-router-dom';
import { readingListService } from '@services/api';
import { ReadingList } from '@models/readinglist_types';
import AddIcon from '@mui/icons-material/Add';
import SearchIcon from '@mui/icons-material/Search';
import CircularProgress from '@mui/material/CircularProgress';
import { useAuth } from '@context/AuthContext';
import ReadingListCard from './ReadingListCard';

const ReadingListsPage = () => {
  const [readingLists, setReadingLists] = useState<ReadingList[]>([]);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [newListTitle, setNewListTitle] = useState('');
  const [newListDescription, setNewListDescription] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearchQuery, setDebouncedSearchQuery] = useState('');
  const { isAuthenticated } = useAuth();

  // Handle search debounce
  useEffect(() => {
    const timerId = setTimeout(() => {
      setDebouncedSearchQuery(searchQuery);
      if (page !== 1) setPage(1); // Reset to page 1 when search changes
    }, 500);

    return () => {
      clearTimeout(timerId);
    };
  }, [searchQuery]);

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
      await readingListService.createReadingList(newListTitle, newListDescription);
      setCreateDialogOpen(false);
      setNewListTitle('');
      setNewListDescription('');
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
          Reading Lists
        </Typography>
        {isAuthenticated && (
          <Button 
            variant="contained" 
            startIcon={<AddIcon />}
            onClick={() => setCreateDialogOpen(true)}
          >
            Create List
          </Button>
        )}
      </Box>
      
      {/* Search Bar */}
      <Box sx={{ mb: 3 }}>
        <TextField
          fullWidth
          placeholder="Search reading lists..."
          variant="outlined"
          value={searchQuery}
          onChange={handleSearchChange}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon />
              </InputAdornment>
            ),
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
              ? `No reading lists found matching "${debouncedSearchQuery}"`
              : "No reading lists found"}
          </Typography>
          {isAuthenticated && !debouncedSearchQuery && (
            <Button 
              variant="contained" 
              startIcon={<AddIcon />}
              onClick={() => setCreateDialogOpen(true)}
              sx={{ mt: 2 }}
            >
              Create Your First List
            </Button>
          )}
          {!isAuthenticated && !debouncedSearchQuery && (
            <Button 
              variant="contained" 
              component={RouterLink} 
              to="/login"
              sx={{ mt: 2 }}
            >
              Login to Create Lists
            </Button>
          )}
        </Box>
      ) : (
        <>
          <Grid container spacing={3}>
            {readingLists.map((list) => (
              <Grid item xs={12} sm={6} key={list.id}>
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
        <DialogTitle>Create New Reading List</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="title"
            label="List Title"
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
            label="Description (Optional)"
            type="text"
            fullWidth
            variant="outlined"
            multiline
            rows={4}
            value={newListDescription}
            onChange={(e) => setNewListDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCreateDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleCreateList} 
            variant="contained"
            disabled={!newListTitle.trim()}
          >
            Create
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingListsPage;
