import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import { 
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, CircularProgress,
  Paper, Stack,
  Avatar,
  useTheme,
  useMediaQuery,
  IconButton
} from '@mui/material';
import {
  DndContext, 
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  DragEndEvent
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { readingListService } from '@services/api';
import { ReadingList, ReadingListItem } from '@models/readinglist_types';
import { useAuth } from '@context/AuthContext';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import ShareIcon from '@mui/icons-material/Share';
import ReadingListCard from '@components/common/novelcardtypes/ReadingListItemCard';
import { formatTimeAgo } from '@utils/Misc';

// Sortable novel item component
const SortableNovelItem = ({ item, isOwner, onEditNote, onRemoveItem }: { 
  item: ReadingListItem; 
  index: number;
  isOwner: boolean;
  onEditNote: (itemId: string, note?: string) => void;
  onRemoveItem: (itemId: string) => void;
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({
    id: item.id,
    disabled: !isOwner
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
    zIndex: isDragging ? 1000 : 1,
  };

  return (
    <Box
      ref={setNodeRef}
      style={style}
      sx={{
        mb: 2,
        display: 'flex',
        gap: 1,
        alignItems: 'stretch',
        width: '100%',
        minWidth: 0,
      }}
    >
      {isOwner && (
        <Box 
          sx={{ 
            width: 40,
            flexShrink: 0,
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            bgcolor: 'action.hover',
            borderRadius: 1,
            cursor: 'grab',
            touchAction: 'none',
            '&:active': {
              cursor: 'grabbing'
            }
          }} 
          {...attributes} 
          {...listeners}
        >
          <DragIndicatorIcon color="action" />
        </Box>
      )}

      <Box sx={{ 
        flex: 1,
        minWidth: 0,
        overflow: 'hidden'
      }}>
        <ReadingListCard 
          novel={item.novel} 
          to={`/novels/${item.novel.slug}`} 
          note={item.note}
          isOwner={isOwner}
          onEditNote={onEditNote}
          onRemoveItem={onRemoveItem}
          itemId={item.id}
        />
      </Box>
    </Box>
  );
};

const ReadingListDetail = () => {
  const { listId } = useParams<{ listId: string }>();
  const [readingList, setReadingList] = useState<ReadingList | null>(null);
  const [loading, setLoading] = useState(true);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false);
  const [currentItemId, setCurrentItemId] = useState<string>('');
  const [editingNote, setEditingNote] = useState('');
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  // Configure drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8,
      }
    }),
    useSensor(TouchSensor, {
      activationConstraint: {
        delay: 250,
        tolerance: 5,
      }
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const isOwner = useCallback(() => {
    return isAuthenticated && readingList?.user.id === user?.id;
  }, [isAuthenticated, readingList, user]);

  useEffect(() => {
    if (listId) {
      fetchReadingList();
    }
  }, [listId]);

  const fetchReadingList = async () => {
    if (!listId) return;

    try {
      setLoading(true);
      const data = await readingListService.getReadingListDetail(listId);
      setReadingList(data);
      setEditTitle(data.title);
      setEditDescription(data.description || '');
    } catch (error) {
      console.error('Error fetching reading list:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleUpdateList = async () => {
    if (!listId || !readingList || !isOwner()) return;

    try {
      await readingListService.updateReadingList(listId, {
        title: editTitle,
        description: editDescription
      });
      setEditDialogOpen(false);
      fetchReadingList();
    } catch (error) {
      console.error('Error updating reading list:', error);
    }
  };

  const handleDeleteList = async () => {
    if (!listId || !readingList || !isOwner()) return;

    try {
      await readingListService.deleteReadingList(listId);
      setDeleteDialogOpen(false);
      navigate('/reading-lists');
    } catch (error) {
      console.error('Error deleting reading list:', error);
    }
  };

  const handleOpenNoteDialog = (itemId: string, note: string = '') => {
    setCurrentItemId(itemId);
    setEditingNote(note);
    setEditNoteDialogOpen(true);
  };

  const handleSaveNote = async () => {
    if (!listId || !currentItemId || !isOwner()) return;

    try {
      await readingListService.updateListItem(listId, currentItemId, { note: editingNote });
      setEditNoteDialogOpen(false);
      fetchReadingList();
    } catch (error) {
      console.error('Error updating note:', error);
    }
  };

  const handleRemoveNovel = async (itemId: string) => {
    if (!listId || !isOwner()) return;

    try {
      await readingListService.removeNovelFromList(listId, itemId);
      fetchReadingList();
    } catch (error) {
      console.error('Error removing novel:', error);
    }
  };

  const handleShareList = () => {
    if (navigator.share) {
      navigator.share({
        title: readingList?.title || 'Reading List',
        text: readingList?.description || 'Check out this reading list!',
        url: window.location.href,
      }).catch((error) => console.log('Error sharing:', error));
    } else {
      // Fallback for browsers that don't support the Web Share API
      navigator.clipboard.writeText(window.location.href)
        .then(() => alert('Link copied to clipboard!'))
        .catch((error) => console.error('Error copying link:', error));
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (!over || active.id === over.id || !readingList?.items || !listId || !isOwner()) {
      return;
    }
    
    // Find the indices of the dragged item and the target position
    const oldIndex = readingList.items.findIndex(item => item.id === active.id);
    const newIndex = readingList.items.findIndex(item => item.id === over.id);
    
    if (oldIndex === -1 || newIndex === -1) return;
    
    // Update the list locally first for immediate UI update
    const updatedItems = arrayMove([...readingList.items], oldIndex, newIndex);
    
    // Update positions
    const updatedItemsWithPositions = updatedItems.map((item, index) => ({
      ...item,
      position: index
    }));
    
    setReadingList({
      ...readingList,
      items: updatedItemsWithPositions
    });
    
    // Send the update to the server
    try {
      const positionUpdates = updatedItemsWithPositions.map((item, index) => ({
        id: item.id,
        position: index
      }));
      
      await readingListService.reorderListItems(listId, positionUpdates);
    } catch (error) {
      console.error('Error reordering items:', error);
      // If there's an error, refresh the list to get the correct order
      fetchReadingList();
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '50vh' }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!readingList) {
    return (
      <Box sx={{ textAlign: 'center', my: 4 }}>
        <Typography variant="h6">Reading list not found</Typography>
        <Button component={RouterLink} to="/reading-lists" sx={{ mt: 2 }}>
          Back to Reading Lists
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: 3, py: 4 }}>
      {/* Header Section */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h4" component="h1" gutterBottom>
              {readingList?.title}
            </Typography>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
              <Box sx={{ display: "flex", alignItems: "center" }}>
                <Avatar
                    sx={{
                        width: 24,
                        height: 24,
                        mr: 1,
                        bgcolor: "primary.main",
                        fontSize: "0.8rem",
                    }}
                    alt={readingList?.user.username}
                    title={readingList?.user.username}
                    src={readingList?.user.profile_pic || undefined}
                >
                    {readingList?.user.username[0].toUpperCase()}
                </Avatar>
                <Typography variant="body2" color="text.secondary">
                    {readingList?.user.username}
                </Typography>
              </Box>
              <Typography variant="body2" color="text.secondary" sx={{ mx: 1 }}>•</Typography>
              <Typography variant="body2" color="text.secondary">
                {readingList && formatTimeAgo(new Date(readingList.updated_at))}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mx: 1 }}>•</Typography>
              <Typography variant="body2" color="text.secondary">
                {readingList?.items?.length || 0} novels
              </Typography>
            </Box>
            {readingList?.description && (
              <Typography variant="body1" color="text.secondary">
                {readingList.description}
              </Typography>
            )}
          </Box>

          <Stack direction="row" spacing={1}>
            {isMobile ? (
              <>
                <IconButton
                  onClick={handleShareList}
                  color="primary"
                  title="Share"
                >
                  <ShareIcon />
                </IconButton>
                {isOwner() && (
                  <>
                    <IconButton
                      onClick={() => setEditDialogOpen(true)}
                      color="primary"
                      title="Edit"
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      color="error"
                      onClick={() => setDeleteDialogOpen(true)}
                      title="Delete"
                    >
                      <DeleteIcon />
                    </IconButton>
                  </>
                )}
              </>
            ) : (
              <>
                <Button
                  startIcon={<ShareIcon />}
                  onClick={handleShareList}
                  variant="outlined"
                >
                  Share
                </Button>
                {isOwner() && (
                  <>
                    <Button
                      startIcon={<EditIcon />}
                      onClick={() => setEditDialogOpen(true)}
                      variant="outlined"
                    >
                      Edit
                    </Button>
                    <Button
                      startIcon={<DeleteIcon />}
                      color="error"
                      onClick={() => setDeleteDialogOpen(true)}
                      variant="outlined"
                    >
                      Delete
                    </Button>
                  </>
                )}
              </>
            )}
          </Stack>
        </Box>
      </Paper>

      {/* List Items Section */}
      {readingList?.items?.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="h6" gutterBottom>
            This reading list is empty
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {isOwner() ? 
              "Start adding novels by clicking the 'Add to Reading List' button on any novel page." :
              "No novels have been added to this list yet."}
          </Typography>
        </Paper>
      ) : (
        <DndContext 
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext 
            items={readingList?.items?.map(item => item.id) || []} 
            strategy={verticalListSortingStrategy}
          >
            {readingList?.items?.map((item, index) => (
              <SortableNovelItem 
                key={item.id}
                item={item} 
                index={index}
                isOwner={isOwner()}
                onEditNote={handleOpenNoteDialog}
                onRemoveItem={handleRemoveNovel}
              />
            ))}
          </SortableContext>
        </DndContext>
      )}

      {/* Edit List Dialog */}
      <Dialog 
        open={editDialogOpen} 
        onClose={() => setEditDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Edit Reading List</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="edit-title"
            label="List Title"
            type="text"
            fullWidth
            variant="outlined"
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            required
            sx={{ mb: 2 }}
          />
          <TextField
            margin="dense"
            id="edit-description"
            label="Description (Optional)"
            type="text"
            fullWidth
            variant="outlined"
            multiline
            rows={4}
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setEditDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleUpdateList} 
            variant="contained"
            disabled={!editTitle.trim()}
          >
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete List Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
      >
        <DialogTitle>Delete Reading List</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete "{readingList.title}"? This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleDeleteList} 
            variant="contained" 
            color="error"
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Note Dialog */}
      <Dialog 
        open={editNoteDialogOpen} 
        onClose={() => setEditNoteDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>Edit Note</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="note"
            label="Your Note"
            type="text"
            fullWidth
            variant="outlined"
            multiline
            rows={4}
            value={editingNote}
            onChange={(e) => setEditingNote(e.target.value)}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setEditNoteDialogOpen(false)}>Cancel</Button>
          <Button 
            onClick={handleSaveNote} 
            variant="contained"
          >
            Save Note
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingListDetail;
