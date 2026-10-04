import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box,
  Typography,
  Grid as Grid,
  Pagination,
  Alert,
  CircularProgress,
  useMediaQuery,
  Paper,
  Divider,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Drawer,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
} from '@dnd-kit/sortable';
import SearchIcon from '@mui/icons-material/Search';
import FolderIcon from '@mui/icons-material/Folder';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import { Link as RouterLink } from 'react-router-dom';
import { userService, LibrarySort } from '@services/user.service';
import { novelService } from '@services/novel.service';
import LibraryNovelCard from '@components/library/LibraryNovelCard';
import LibraryFolderSidebar from '@components/library/LibraryFolderSidebar';
import { LibraryFolder, Novel } from '@models/novels_types';
import { useAuth } from '@context/AuthContext';
import { useDebounce } from '@utils/useDebounce';
import BreadcrumbNav from '../common/BreadcrumbNav';
import NovelRecommendation from '@components/common/NovelRecommendation';
import { useTranslation } from 'react-i18next';

const LibraryPage: React.FC = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

  const [items, setItems] = useState<Novel[]>([]);
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [recommendations, setRecommendations] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [allCount, setAllCount] = useState(0);
  const [folder, setFolder] = useState('all');
  const [sort, setSort] = useState<LibrarySort>('custom');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search);
  const [mobileFoldersOpen, setMobileFoldersOpen] = useState(false);

  const [noteDialog, setNoteDialog] = useState<{
    open: boolean;
    novel: Novel | null;
    value: string;
    folder: string;
  }>({
    open: false,
    novel: null,
    value: '',
    folder: '',
  });
  const [folderDialog, setFolderDialog] = useState<{
    open: boolean;
    folder: LibraryFolder | null;
    value: string;
  }>({ open: false, folder: null, value: '' });
  const [deleteFolder, setDeleteFolder] = useState<LibraryFolder | null>(null);

  // Tags each fetch so a slow older response can't overwrite a newer one
  const fetchRequestIdRef = useRef(0);

  const canDrag = sort === 'custom' && folder === 'all' && !debouncedSearch;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const fetchLibrary = useCallback(
    async (pageNum = 1) => {
      const requestId = ++fetchRequestIdRef.current;
      try {
        setLoading(true);
        setError(null);
        const response = await userService.listBookmarkedNovels({
          page: pageNum,
          pageSize: 24,
          search: debouncedSearch,
          folder,
          sort,
        });
        if (requestId !== fetchRequestIdRef.current) return;
        setItems(response.results);
        setFolders(response.folders || []);
        setRecommendations(response.recommendations || []);
        setTotalPages(response.total_pages);
        setPage(response.current_page);
        if (folder === 'all' && !debouncedSearch) {
          setAllCount(response.count);
        }
      } catch (err) {
        if (requestId !== fetchRequestIdRef.current) return;
        console.error('Error fetching library:', err);
        setError(t('library.loadFailed'));
      } finally {
        if (requestId === fetchRequestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [debouncedSearch, folder, sort, t]
  );

  useEffect(() => {
    if (isAuthenticated) {
      fetchLibrary(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetchLibrary already depends on all inputs
  }, [isAuthenticated, debouncedSearch, folder, sort]);

  const handlePageChange = (_: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    fetchLibrary(value);
    window.scrollTo(0, 0);
  };

  const handleRate = async (novel: Novel, value: number | null) => {
    if (!value) return;
    try {
      const response = await novelService.rateNovel(novel.slug, value);
      setItems((prev) =>
        prev.map((item) =>
          item.id === novel.id ? { ...item, user_rating: response.user_rating } : item
        )
      );
    } catch (err) {
      console.error('Error rating novel:', err);
    }
  };

  const handleSaveNote = async () => {
    if (!noteDialog.novel?.bookmark_id) return;
    const folderId = noteDialog.folder || null;
    try {
      await userService.updateLibraryItem(noteDialog.novel.bookmark_id, {
        note: noteDialog.value,
        folder: folderId,
      });
      setItems((prev) =>
        prev.map((item) =>
          item.id === noteDialog.novel?.id
            ? {
                ...item,
                note: noteDialog.value || null,
                folder: folderId,
                folder_name: folders.find((f) => f.id === folderId)?.name ?? null,
              }
            : item
        )
      );
      setNoteDialog({ open: false, novel: null, value: '', folder: '' });
    } catch (err) {
      console.error('Error saving note:', err);
    }
  };

  const handleSaveFolder = async () => {
    const name = folderDialog.value.trim();
    if (!name) return;
    try {
      const saved = folderDialog.folder
        ? await userService.renameLibraryFolder(folderDialog.folder.id, name)
        : await userService.createLibraryFolder(name);
      setFolders((prev) => {
        const exists = prev.some((f) => f.id === saved.id);
        return exists ? prev.map((f) => (f.id === saved.id ? saved : f)) : [...prev, saved];
      });
      setFolderDialog({ open: false, folder: null, value: '' });
    } catch (err) {
      console.error('Error saving folder:', err);
    }
  };

  const handleDeleteFolder = async () => {
    if (!deleteFolder) return;
    try {
      await userService.deleteLibraryFolder(deleteFolder.id);
      setFolders((prev) => prev.filter((f) => f.id !== deleteFolder.id));
      if (folder === deleteFolder.id) setFolder('all');
      setDeleteFolder(null);
    } catch (err) {
      console.error('Error deleting folder:', err);
    }
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = items.findIndex((item) => (item.bookmark_id || item.id) === active.id);
    const newIndex = items.findIndex((item) => (item.bookmark_id || item.id) === over.id);
    if (oldIndex === -1 || newIndex === -1) return;

    const reordered = arrayMove(items, oldIndex, newIndex);
    setItems(reordered);
    try {
      await userService.reorderLibrary(
        reordered
          .filter((item) => item.bookmark_id)
          .map((item, index) => ({ id: item.bookmark_id as string, position: index }))
      );
    } catch (err) {
      console.error('Error reordering library:', err);
      fetchLibrary(1);
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
          my: 4,
        }}
      >
        <LibraryBooksIcon sx={{ fontSize: 60, color: 'primary.main', mb: 2 }} />
        <Typography variant="h5" component="h1" gutterBottom>
          {t('library.headingLoggedOut')}
        </Typography>
        <Typography variant="body1" align="center" sx={{ color: 'text.secondary' }}>
          {t('library.needLogin')}
        </Typography>
        <Typography variant="body2" align="center" sx={{ color: 'text.secondary' }}>
          {t('library.loginPrompt')}
        </Typography>
      </Paper>
    );
  }

  const sidebar = (
    <LibraryFolderSidebar
      folders={folders}
      totalCount={allCount}
      selected={folder}
      onSelect={(value) => {
        setFolder(value);
        setMobileFoldersOpen(false);
      }}
      editable
      onCreate={() => setFolderDialog({ open: true, folder: null, value: '' })}
      onRename={(value) => setFolderDialog({ open: true, folder: value, value: value.name })}
      onDelete={(value) => setDeleteFolder(value)}
    />
  );

  return (
    <Box sx={{ px: { xs: 2, sm: 3 } }}>
      <BreadcrumbNav
        items={[{ label: t('header.library'), icon: <LibraryBooksIcon fontSize="inherit" /> }]}
      />

      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', mb: 1 }}>
        <Typography variant="h4" component="h1" sx={{ flex: 1 }}>
          {t('library.yourLibrary')}
        </Typography>
        <Button
          component={RouterLink}
          to="/import"
          variant="outlined"
          startIcon={<UploadFileIcon />}
        >
          {t('importNu.linkFromLibrary')}
        </Button>
      </Box>

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 2 }}>
        <TextField
          size="small"
          placeholder={t('library.searchPlaceholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: '1 1 240px', minWidth: 200 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" />
              </InputAdornment>
            ),
          }}
        />
        <FormControl size="small" sx={{ minWidth: 160 }}>
          <InputLabel>{t('library.sortBy')}</InputLabel>
          <Select label={t('library.sortBy')} value={sort} onChange={(e) => setSort(e.target.value as LibrarySort)}>
            <MenuItem value="custom">{t('library.sort.custom')}</MenuItem>
            <MenuItem value="title">{t('library.sort.title')}</MenuItem>
            <MenuItem value="date_added">{t('library.sort.date_added')}</MenuItem>
            <MenuItem value="rating">{t('library.sort.rating')}</MenuItem>
          </Select>
        </FormControl>
        {isMobile && (
          <Button variant="outlined" startIcon={<FolderIcon />} onClick={() => setMobileFoldersOpen(true)}>
            {t('library.folders')}
          </Button>
        )}
      </Box>

      <Box sx={{ display: 'flex', gap: 3, alignItems: 'flex-start' }}>
        {!isMobile && (
          <Paper sx={{ p: 1, width: 240, flexShrink: 0, position: 'sticky', top: 80 }}>{sidebar}</Paper>
        )}

        <Box sx={{ flex: 1, minWidth: 0 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
              <CircularProgress />
            </Box>
          ) : error ? (
            <Alert severity="error" sx={{ my: 2 }}>
              {error}
            </Alert>
          ) : items.length === 0 ? (
            <Paper sx={{ p: 4, textAlign: 'center', my: 4 }}>
              <Typography variant="h6" align="center" color="text.secondary">
                {t('library.empty')}
              </Typography>
              <Typography variant="body2" align="center" color="text.secondary">
                {t('library.emptyHint')}
              </Typography>
            </Paper>
          ) : (
            <>
              {canDrag && (
                <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                  <SortableContext
                    items={items.map((item) => item.bookmark_id || item.id)}
                    strategy={rectSortingStrategy}
                  >
                    <Grid container spacing={2}>
                      {items.map((novel) => (
                        <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                          <LibraryNovelCard
                            novel={novel}
                            editable
                            sortable
                            onRate={handleRate}
                            onEditNote={(value) =>
                              setNoteDialog({
                                open: true,
                                novel: value,
                                value: value.note || '',
                                folder: value.folder || '',
                              })
                            }
                          />
                        </Grid>
                      ))}
                    </Grid>
                  </SortableContext>
                </DndContext>
              )}

              {!canDrag && (
                <Grid container spacing={2}>
                  {items.map((novel) => (
                    <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                      <LibraryNovelCard
                        novel={novel}
                        editable
                        onRate={handleRate}
                        onEditNote={(value) =>
                          setNoteDialog({
                            open: true,
                            novel: value,
                            value: value.note || '',
                            folder: value.folder || '',
                          })
                        }
                      />
                    </Grid>
                  ))}
                </Grid>
              )}

              {totalPages > 1 && (
                <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
                  <Pagination
                    count={totalPages}
                    page={page}
                    onChange={handlePageChange}
                    color="primary"
                    size={isMobile ? 'small' : 'medium'}
                  />
                </Box>
              )}
            </>
          )}

          {recommendations.length > 0 && !debouncedSearch && folder === 'all' && (
            <>
              <Divider sx={{ my: 6 }} />
              <Typography variant="h5" sx={{ mb: 2 }}>{t('library.recommended')}</Typography>
              <NovelRecommendation
                similarNovels={recommendations.map((novel) => ({ ...novel, similarity: 0 }))}
                loading={false}
              />
            </>
          )}
        </Box>
      </Box>

      <Drawer anchor="left" open={isMobile && mobileFoldersOpen} onClose={() => setMobileFoldersOpen(false)}>
        <Box sx={{ width: 260, p: 2 }}>{sidebar}</Box>
      </Drawer>

      {/* Note dialog */}
      <Dialog
        open={noteDialog.open}
        onClose={() => setNoteDialog({ open: false, novel: null, value: '', folder: '' })}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>{noteDialog.novel?.title}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            fullWidth
            multiline
            rows={4}
            label={t('library.noteLabel')}
            value={noteDialog.value}
            onChange={(e) => setNoteDialog((prev) => ({ ...prev, value: e.target.value }))}
          />
          <FormControl fullWidth margin="dense">
            <InputLabel>{t('library.folders')}</InputLabel>
            <Select
              label={t('library.folders')}
              value={noteDialog.folder}
              onChange={(e) => setNoteDialog((prev) => ({ ...prev, folder: e.target.value }))}
            >
              <MenuItem value="">{t('library.unfiled')}</MenuItem>
              {folders.map((f) => (
                <MenuItem key={f.id} value={f.id}>
                  {f.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNoteDialog({ open: false, novel: null, value: '', folder: '' })}>
            {t('common.cancel')}
          </Button>
          <Button variant="contained" onClick={handleSaveNote}>{t('common.save')}</Button>
        </DialogActions>
      </Dialog>

      {/* Folder dialog */}
      <Dialog open={folderDialog.open} onClose={() => setFolderDialog({ open: false, folder: null, value: '' })} fullWidth maxWidth="xs">
        <DialogTitle>{folderDialog.folder ? t('library.renameFolder') : t('library.newFolder')}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            fullWidth
            label={t('library.folderName')}
            value={folderDialog.value}
            onChange={(e) => setFolderDialog((prev) => ({ ...prev, value: e.target.value }))}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFolderDialog({ open: false, folder: null, value: '' })}>{t('common.cancel')}</Button>
          <Button variant="contained" onClick={handleSaveFolder} disabled={!folderDialog.value.trim()}>
            {t('common.save')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete folder confirmation */}
      <Dialog open={Boolean(deleteFolder)} onClose={() => setDeleteFolder(null)}>
        <DialogTitle>{t('library.deleteFolderTitle')}</DialogTitle>
        <DialogContent>
          <Typography>{t('library.deleteFolderBody', { name: deleteFolder?.name })}</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteFolder(null)}>{t('common.cancel')}</Button>
          <Button color="error" variant="contained" onClick={handleDeleteFolder}>{t('common.delete')}</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default LibraryPage;
