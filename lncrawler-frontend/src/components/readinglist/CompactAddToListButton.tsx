import React, { useState } from 'react';
import { 
  Box, IconButton, Dialog, DialogTitle, DialogContent, List, ListItem, ListItemText,
  ListItemButton, DialogActions, TextField, CircularProgress, Typography,
  ListItemAvatar, Avatar, Tooltip
} from '@mui/material';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import AddIcon from '@mui/icons-material/Add';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import BookIcon from '@mui/icons-material/Book';
import { Button } from '@mui/material';
import { readingListService } from '@services/api';
import { ReadingList } from '@models/readinglist_types';
import { useAuth } from '@context/AuthContext';
import { useNavigate } from 'react-router-dom';

interface CompactAddToListButtonProps {
  novelId: string;
  novelTitle: string;
  customSx?: React.CSSProperties | Record<string, any>;
}

const CompactAddToListButton: React.FC<CompactAddToListButtonProps> = ({ 
  novelId,
  novelTitle,
  customSx = {}
}) => {
  const [open, setOpen] = useState(false);
  const [userLists, setUserLists] = useState<ReadingList[]>([]);
  const [loading, setLoading] = useState(false);
  const [newListTitle, setNewListTitle] = useState('');
  const [showCreateForm, setShowCreateForm] = useState(false);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const fetchUserLists = async () => {
    try {
      setLoading(true);
      const response = await readingListService.getUserReadingLists();
      setUserLists(response.results);
    } catch (error) {
      console.error('Error fetching user reading lists:', error);
    }
    setLoading(false);
  };

  const handleOpen = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    
    if (!isAuthenticated) {
      navigate('/login?redirect=' + encodeURIComponent(window.location.pathname));
      return;
    }
    
    setOpen(true);
    fetchUserLists();
  };

  const handleClose = () => {
    setOpen(false);
    setShowCreateForm(false);
    setNewListTitle('');
  };

  const handleCreateList = async () => {
    if (!newListTitle.trim()) return;

    try {
      setLoading(true);
      const newList = await readingListService.createReadingList(newListTitle);
      await addNovelToList(newList.id);
      handleClose();
    } catch (error) {
      console.error('Error creating list:', error);
      setLoading(false);
    }
  };

  const addNovelToList = async (listId: string) => {
    try {
      await readingListService.addNovelToList(listId, novelId);
      return true;
    } catch (error) {
      console.error('Error adding novel to list:', error);
      return false;
    }
  };

  const handleAddToList = async (listId: string) => {
    setLoading(true);
    const success = await addNovelToList(listId);
    if (success) {
      handleClose();
    } else {
      setLoading(false);
    }
  };

  const handleRemoveFromList = async (e: React.MouseEvent, listId: string) => {
    e.stopPropagation();
    e.preventDefault();
    
    try {
      setLoading(true);
      
      // Find the novel's item ID in the list
      const list = userLists.find(l => l.id === listId);
      if (!list || !list.items) {
        // Get list details to find the item ID
        const listDetails = await readingListService.getReadingListDetail(listId);
        const item = listDetails.items?.find(item => item.novel.id === novelId);
        
        if (item) {
          await readingListService.removeNovelFromList(listId, item.id);
          // Update the lists to reflect removal
          fetchUserLists();
        }
      } else {
        const item = list.items.find(item => item.novel.id === novelId);
        if (item) {
          await readingListService.removeNovelFromList(listId, item.id);
          // Update the lists to reflect removal
          fetchUserLists();
        }
      }
    } catch (error) {
      console.error('Error removing novel from list:', error);
    } finally {
      setLoading(false);
    }
  };

  const isNovelInList = (list: ReadingList) => {
    return list.items_names?.includes(novelTitle);
  };

  if (!isAuthenticated) return null;

  return (
    <>
      <Box sx={customSx}>
        <IconButton
          size="small"
          onClick={handleOpen}
          sx={{
            bgcolor: 'rgba(0, 0, 0, 0.6)',
            color: 'white',
            '&:hover': {
              bgcolor: 'rgba(0, 0, 0, 0.8)',
            },
            width: 36,
            height: 36,
          }}
        >
          <PlaylistAddIcon />
        </IconButton>
      </Box>

      <Dialog open={open} onClose={handleClose} fullWidth maxWidth="xs">
        <DialogTitle>Add "{novelTitle}" to Reading List</DialogTitle>
        
        <DialogContent dividers>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 3 }}>
              <CircularProgress size={32} />
            </Box>
          ) : showCreateForm ? (
            <Box sx={{ p: 1 }}>
              <TextField
                autoFocus
                fullWidth
                label="New List Title"
                value={newListTitle}
                onChange={(e) => setNewListTitle(e.target.value)}
                variant="outlined"
                margin="normal"
              />
              <Box sx={{ mt: 2, display: 'flex', justifyContent: 'flex-end' }}>
                <Button 
                  onClick={() => setShowCreateForm(false)} 
                  sx={{ mr: 1 }}
                >
                  Cancel
                </Button>
                <Button 
                  variant="contained" 
                  onClick={handleCreateList}
                  disabled={!newListTitle.trim()}
                >
                  Create & Add
                </Button>
              </Box>
            </Box>
          ) : userLists.length === 0 ? (
            <Box sx={{ p: 2, textAlign: 'center' }}>
              <Typography variant="body1" gutterBottom>
                You don't have any reading lists yet.
              </Typography>
              <Button 
                variant="contained" 
                startIcon={<AddIcon />}
                onClick={() => setShowCreateForm(true)}
                sx={{ mt: 1 }}
              >
                Create Your First List
              </Button>
            </Box>
          ) : (
            <>
              <List sx={{ pt: 0 }}>
                {userLists.map((list) => {
                  const alreadyInList = isNovelInList(list);
                  return (
                    <ListItem 
                      disablePadding 
                      key={list.id}
                      secondaryAction={
                        alreadyInList && (
                          <Tooltip title="Click to remove from this list">
                            <IconButton 
                              edge="end" 
                              onClick={(e) => handleRemoveFromList(e, list.id)}
                              size="small"
                              color="success"
                            >
                              <CheckCircleIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )
                      }
                    >
                      <ListItemButton 
                        onClick={() => handleAddToList(list.id)}
                        disabled={alreadyInList}
                      >
                        <ListItemAvatar>
                          {list.first_item?.novel.prefered_source?.cover_min_url ? (
                            <Avatar 
                              src={list.first_item.novel.prefered_source.cover_min_url}
                              alt={list.title}
                              variant="rounded"
                            />
                          ) : (
                            <Avatar sx={{ bgcolor: 'primary.main' }} variant="rounded">
                              <BookIcon />
                            </Avatar>
                          )}
                        </ListItemAvatar>
                        <ListItemText 
                          primary={list.title} 
                          secondary={`${list.items_count || 0} novels`}
                          primaryTypographyProps={{
                            style: {
                              fontWeight: alreadyInList ? 'bold' : 'normal',
                            }
                          }}
                        />
                      </ListItemButton>
                    </ListItem>
                  );
                })}
              </List>
              
              <Box sx={{ mt: 2, textAlign: 'center' }}>
                <Button 
                  onClick={() => setShowCreateForm(true)} 
                  startIcon={<AddIcon />}
                >
                  Create New List
                </Button>
              </Box>
            </>
          )}
        </DialogContent>
        
        <DialogActions>
          <Button onClick={handleClose}>Close</Button>
        </DialogActions>
      </Dialog>
    </>
  );
};

export default CompactAddToListButton;
