import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, Link as RouterLink } from 'react-router-dom';
import { 
  Box, Typography, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, CircularProgress,
  Paper, Stack,
  Avatar,
  useTheme,
  useMediaQuery,
  IconButton,
  Chip,
  Switch,
  FormControlLabel,
  Autocomplete,
  Select,
  MenuItem,
  List,
  ListItem,
  ListItemAvatar,
  ListItemText,
  Divider,
  FormControl,
  InputLabel,
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
import LockIcon from '@mui/icons-material/Lock';
import PublicIcon from '@mui/icons-material/Public';
import GroupIcon from '@mui/icons-material/Group';
import ReadingListCard from '@components/common/novelcardtypes/ReadingListItemCard';
import { formatTimeAgo, getNovelSourceLink } from '@utils/Misc';
import { useTranslation } from 'react-i18next';
import { ReadingListCollaborator } from '@models/readinglist_types';
import { User } from '@models/user_types';
import { useDebounce } from '@utils/useDebounce';

// Sortable novel item component
const SortableNovelItem = ({ item, canEdit, onEditNote, onRemoveItem }: { 
  item: ReadingListItem; 
  index: number;
  canEdit: boolean;
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
    disabled: !canEdit
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
      {canEdit && (
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
          {...getNovelSourceLink(item.novel)} 
          note={item.note}
          canEdit={canEdit}
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
  const [editIsPublic, setEditIsPublic] = useState(true);
  const [collaboratorsDialogOpen, setCollaboratorsDialogOpen] = useState(false);
  const [userOptions, setUserOptions] = useState<User[]>([]);
  const [userSearchInput, setUserSearchInput] = useState('');
  const debouncedUserSearchInput = useDebounce(userSearchInput);
  const [newCollaboratorRole, setNewCollaboratorRole] = useState<'editor' | 'reader'>('editor');
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editNoteDialogOpen, setEditNoteDialogOpen] = useState(false);
  const [currentItemId, setCurrentItemId] = useState<string>('');
  const [editingNote, setEditingNote] = useState('');
  const { isAuthenticated } = useAuth();
  const { t } = useTranslation();
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
    return isAuthenticated && readingList?.user_role === 'owner';
  }, [isAuthenticated, readingList]);

  const canEdit = useCallback(() => {
    return isAuthenticated && (readingList?.user_role === 'owner' || readingList?.user_role === 'editor');
  }, [isAuthenticated, readingList]);

  useEffect(() => {
    if (listId) {
      fetchReadingList();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t intentionally omitted; listId is the only input
  }, [listId]);

  const fetchReadingList = async (silent = false) => {
    if (!listId) return;

    try {
      if (!silent) setLoading(true);
      const data = await readingListService.getReadingListDetail(listId);
      setReadingList(data);
      setEditTitle(data.title);
      setEditDescription(data.description || '');
      setEditIsPublic(data.is_public);
    } catch (error) {
      console.error('Error fetching reading list:', error);
    } finally {
      if (!silent) setLoading(false);
    }
  };

  const handleUpdateList = async () => {
    if (!listId || !readingList || !canEdit()) return;

    try {
      await readingListService.updateReadingList(listId, {
        title: editTitle,
        description: editDescription,
        ...(isOwner() ? { is_public: editIsPublic } : {}),
      });
      setEditDialogOpen(false);
      fetchReadingList(true);
    } catch (error) {
      console.error('Error updating reading list:', error);
    }
  };

  useEffect(() => {
    if (debouncedUserSearchInput.trim().length < 2) {
      setUserOptions([]);
      return;
    }
    let cancelled = false;
    readingListService.searchUsers(debouncedUserSearchInput.trim())
      .then((users) => { if (!cancelled) setUserOptions(users); })
      .catch((error) => {
        console.error('Error searching users:', error);
        if (!cancelled) setUserOptions([]);
      });
    return () => { cancelled = true; };
  }, [debouncedUserSearchInput]);

  const handleAddCollaborator = async (selected: User | null) => {
    if (!listId || !selected) return;
    try {
      await readingListService.addCollaborator(listId, {
        username: selected.username,
        role: newCollaboratorRole,
      });
      setUserSearchInput('');
      setUserOptions([]);
      fetchReadingList(true);
    } catch (error) {
      console.error('Error adding collaborator:', error);
    }
  };

  const handleUpdateCollaboratorRole = async (collaboratorId: string, role: 'editor' | 'reader') => {
    if (!listId) return;
    try {
      await readingListService.updateCollaborator(listId, collaboratorId, role);
      fetchReadingList(true);
    } catch (error) {
      console.error('Error updating collaborator:', error);
    }
  };

  const handleRemoveCollaborator = async (collaboratorId: string) => {
    if (!listId) return;
    try {
      await readingListService.removeCollaborator(listId, collaboratorId);
      fetchReadingList(true);
    } catch (error) {
      console.error('Error removing collaborator:', error);
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
    if (!listId || !currentItemId || !canEdit()) return;

    try {
      await readingListService.updateListItem(listId, currentItemId, { note: editingNote });
      setEditNoteDialogOpen(false);
      fetchReadingList();
    } catch (error) {
      console.error('Error updating note:', error);
    }
  };

  const handleRemoveNovel = async (itemId: string) => {
    if (!listId || !canEdit()) return;

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
        title: readingList?.title || t('readingLists.shareTitle'),
        text: readingList?.description || t('readingLists.shareText'),
        url: window.location.href,
      }).catch((error) => console.log('Error sharing:', error));
    } else {
      // Fallback for browsers that don't support the Web Share API
      navigator.clipboard.writeText(window.location.href)
        .then(() => alert(t('readingLists.linkCopied')))
        .catch((error) => console.error('Error copying link:', error));
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    
    if (!over || active.id === over.id || !readingList?.items || !listId || !canEdit()) {
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
        <Typography variant="h6">{t('readingLists.notFound')}</Typography>
        <Button component={RouterLink} to="/reading-lists" sx={{ mt: 2 }}>
          {t('readingLists.backToLists')}
        </Button>
      </Box>
    );
  }

  return (
    <Box sx={{ maxWidth: 1000, mx: 'auto', px: 3, py: 4 }}>
      {/* Header Section */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 2, mb: 2 }}>
          <Box sx={{ flex: '1 1 280px', minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, flexWrap: 'wrap' }}>
              <Typography variant="h4" component="h1">
                {readingList?.title}
              </Typography>
              <Chip
                size="small"
                icon={readingList.is_public ? <PublicIcon /> : <LockIcon />}
                label={readingList.is_public ? t('readingLists.public') : t('readingLists.private')}
                color={readingList.is_public ? 'success' : 'default'}
                variant="outlined"
              />
            </Box>
            <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', mb: 2 }}>
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
                <Typography variant="body2" sx={{
                  color: "text.secondary"
                }}>
                    {readingList?.user.username}
                </Typography>
              </Box>
              <Typography
                variant="body2"
                sx={{
                  color: "text.secondary",
                  mx: 1
                }}>•</Typography>
              <Typography variant="body2" sx={{
                color: "text.secondary"
              }}>
                {readingList && t('readingLists.updatedAgo', { time: formatTimeAgo(new Date(readingList.updated_at), t) })}
              </Typography>
              <Typography
                variant="body2"
                sx={{
                  color: "text.secondary",
                  mx: 1
                }}>•</Typography>
              <Typography variant="body2" sx={{
                color: "text.secondary"
              }}>
                {t('readingLists.novelsCount', { count: readingList?.items?.length || 0 })}
              </Typography>
            </Box>
            {readingList?.description && (
              <Typography variant="body1" sx={{
                color: "text.secondary"
              }}>
                {readingList.description}
              </Typography>
            )}
          </Box>

          <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', rowGap: 1 }}>
            {isMobile ? (
              <>
                <IconButton
                  onClick={handleShareList}
                  color="primary"
                  title={t('common.share')}
                >
                  <ShareIcon />
                </IconButton>
                {isOwner() && (
                  <>
                    <IconButton
                      onClick={() => setCollaboratorsDialogOpen(true)}
                      color="primary"
                      title={t('readingLists.manageCollaborators')}
                    >
                      <GroupIcon />
                    </IconButton>
                    <IconButton
                      onClick={() => setEditDialogOpen(true)}
                      color="primary"
                      title={t('common.edit')}
                    >
                      <EditIcon />
                    </IconButton>
                    <IconButton
                      color="error"
                      onClick={() => setDeleteDialogOpen(true)}
                      title={t('common.delete')}
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
                  {t('common.share')}
                </Button>
                {isOwner() && (
                  <>
                    <Button
                      startIcon={<GroupIcon />}
                      onClick={() => setCollaboratorsDialogOpen(true)}
                      variant="outlined"
                    >
                      {t('readingLists.manageCollaborators')}
                    </Button>
                    <Button
                      startIcon={<EditIcon />}
                      onClick={() => setEditDialogOpen(true)}
                      variant="outlined"
                    >
                      {t('common.edit')}
                    </Button>
                    <Button
                      startIcon={<DeleteIcon />}
                      color="error"
                      onClick={() => setDeleteDialogOpen(true)}
                      variant="outlined"
                    >
                      {t('common.delete')}
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
            {t('readingLists.empty')}
          </Typography>
          <Typography variant="body2" sx={{
            color: "text.secondary"
          }}>
            {canEdit() ? 
              t('readingLists.emptyOwnerHint') :
              t('readingLists.emptyOtherHint')}
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
                canEdit={canEdit()}
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
        <DialogTitle>{t('readingLists.editTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="edit-title"
            label={t('readingLists.listTitle')}
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
            label={t('readingLists.descriptionOptional')}
            type="text"
            fullWidth
            variant="outlined"
            multiline
            rows={4}
            value={editDescription}
            onChange={(e) => setEditDescription(e.target.value)}
          />
          {isOwner() && (
            <FormControlLabel
              sx={{ mt: 1 }}
              control={
                <Switch
                  checked={editIsPublic}
                  onChange={(e) => setEditIsPublic(e.target.checked)}
                />
              }
              label={editIsPublic ? t('readingLists.public') : t('readingLists.private')}
            />
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setEditDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button 
            onClick={handleUpdateList} 
            variant="contained"
            disabled={!editTitle.trim()}
          >
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete List Confirmation Dialog */}
      <Dialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
      >
        <DialogTitle>{t('readingLists.deleteTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('readingLists.deleteBody', { title: readingList.title })}
          </Typography>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setDeleteDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button 
            onClick={handleDeleteList} 
            variant="contained" 
            color="error"
          >
            {t('common.delete')}
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
        <DialogTitle>{t('readingLists.editNoteTitle')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            id="note"
            label={t('readingLists.yourNote')}
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
          <Button onClick={() => setEditNoteDialogOpen(false)}>{t('common.cancel')}</Button>
          <Button 
            onClick={handleSaveNote} 
            variant="contained"
          >
            {t('readingLists.saveNote')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Collaborators Dialog */}
      <Dialog
        open={collaboratorsDialogOpen}
        onClose={() => setCollaboratorsDialogOpen(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{t('readingLists.manageCollaborators')}</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} sx={{ mt: 1, mb: 2 }}>
            <Autocomplete
              fullWidth
              size="small"
              options={userOptions}
              getOptionLabel={(option) => option.username}
              isOptionEqualToValue={(option, value) => option.id === value.id}
              value={null}
              inputValue={userSearchInput}
              onInputChange={(_, value) => setUserSearchInput(value)}
              onChange={(_, value) => handleAddCollaborator(value)}
              renderInput={(params) => (
                <TextField {...params} label={t('readingLists.searchUsers')} />
              )}
            />
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>{t('readingLists.role')}</InputLabel>
              <Select
                value={newCollaboratorRole}
                label={t('readingLists.role')}
                onChange={(e) => setNewCollaboratorRole(e.target.value as 'editor' | 'reader')}
              >
                <MenuItem value="editor">{t('readingLists.roleEditor')}</MenuItem>
                <MenuItem value="reader">{t('readingLists.roleReader')}</MenuItem>
              </Select>
            </FormControl>
          </Stack>

          <Divider sx={{ mb: 1 }} />

          {readingList.collaborators && readingList.collaborators.length > 0 ? (
            <List>
              {readingList.collaborators.map((collaborator: ReadingListCollaborator) => (
                <ListItem
                  key={collaborator.id}
                  secondaryAction={
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Select
                        size="small"
                        value={collaborator.role}
                        onChange={(e) => handleUpdateCollaboratorRole(
                          collaborator.id, e.target.value as 'editor' | 'reader')}
                      >
                        <MenuItem value="editor">{t('readingLists.roleEditor')}</MenuItem>
                        <MenuItem value="reader">{t('readingLists.roleReader')}</MenuItem>
                      </Select>
                      <IconButton
                        edge="end"
                        color="error"
                        onClick={() => handleRemoveCollaborator(collaborator.id)}
                        title={t('readingLists.removeCollaborator')}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Stack>
                  }
                >
                  <ListItemAvatar>
                    <Avatar src={collaborator.user.profile_pic || undefined}>
                      {collaborator.user.username[0]?.toUpperCase()}
                    </Avatar>
                  </ListItemAvatar>
                  <ListItemText primary={collaborator.user.username} />
                </ListItem>
              ))}
            </List>
          ) : (
            <Typography variant="body2" sx={{ color: 'text.secondary', py: 2 }}>
              {t('readingLists.noCollaborators')}
            </Typography>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setCollaboratorsDialogOpen(false)}>{t('common.close')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default ReadingListDetail;
