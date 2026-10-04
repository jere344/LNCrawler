import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Box,
  Typography,
  Grid as Grid,
  Pagination,
  Alert,
  CircularProgress,
  Paper,
  Divider,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Menu,
  Fade,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  pointerWithin,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
} from '@dnd-kit/sortable';
import SearchIcon from '@mui/icons-material/Search';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import DoneAllIcon from '@mui/icons-material/DoneAll';
import CloseIcon from '@mui/icons-material/Close';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutlined';
import { Link as RouterLink } from 'react-router-dom';
import { userService, LibrarySort } from '@services/user.service';
import { novelService } from '@services/novel.service';
import LibraryNovelCard from '@components/library/LibraryNovelCard';
import LibraryFolderBar from '@components/library/LibraryFolderBar';
import { LibraryFolder, Novel } from '@models/novels_types';
import { useAuth } from '@context/AuthContext';
import { useDebounce } from '@utils/useDebounce';
import defaultCover from '@assets/default-cover.jpg';
import BreadcrumbNav from '../common/BreadcrumbNav';
import NovelRecommendation from '@components/common/NovelRecommendation';
import { useTranslation } from 'react-i18next';

const bookmarkId = (novel: Novel) => novel.bookmark_id || novel.id;

const LibraryPage: React.FC = () => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { isAuthenticated } = useAuth();

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

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [selectMode, setSelectMode] = useState(false);
  const [activeDragIds, setActiveDragIds] = useState<string[]>([]);
  const [bulkMenuAnchor, setBulkMenuAnchor] = useState<null | HTMLElement>(null);

  const [noteDialog, setNoteDialog] = useState<{ open: boolean; novel: Novel | null; value: string }>({
    open: false,
    novel: null,
    value: '',
  });
  const [folderDialog, setFolderDialog] = useState<{ open: boolean; folder: LibraryFolder | null; value: string }>({
    open: false,
    folder: null,
    value: '',
  });
  const [deleteFolder, setDeleteFolder] = useState<LibraryFolder | null>(null);
  const [removeConfirm, setRemoveConfirm] = useState<string[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const fetchRequestIdRef = useRef(0);
  const lastSelectedIndexRef = useRef<number | null>(null);
  const activeDragIdsRef = useRef<string[]>([]);

  const canReorder = sort === 'custom' && folder === 'all' && !debouncedSearch;
  const selectionActive = selectMode || selectedIds.size > 0;

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 250, tolerance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const collisionDetection: CollisionDetection = useCallback((args) => {
    const collisions = pointerWithin(args);
    const list = collisions.length ? collisions : closestCenter(args);
    const folderHit = list.find((c) => String(c.id).startsWith('folder:'));
    return folderHit ? [folderHit] : list;
  }, []);

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
        setSelectedIds(new Set());
        setSelectMode(false);
        lastSelectedIndexRef.current = null;
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

  // Keyboard: Ctrl/Cmd+A selects everything, Escape clears.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.tagName === 'SELECT' ||
          target.isContentEditable)
      ) {
        return;
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'a') {
        event.preventDefault();
        setSelectMode(true);
        setSelectedIds(new Set(items.map(bookmarkId)));
      } else if (event.key === 'Escape') {
        setSelectedIds(new Set());
        setSelectMode(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [items]);

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

  const toggleSelect = useCallback(
    (novel: Novel, { shiftKey }: { shiftKey: boolean }) => {
      const id = bookmarkId(novel);
      const index = items.findIndex((n) => bookmarkId(n) === id);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        if (shiftKey && lastSelectedIndexRef.current !== null && index !== -1) {
          const [start, end] = [lastSelectedIndexRef.current, index].sort((a, b) => a - b);
          for (let i = start; i <= end; i += 1) next.add(bookmarkId(items[i]));
          return next;
        }
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
      lastSelectedIndexRef.current = index !== -1 ? index : lastSelectedIndexRef.current;
    },
    [items]
  );

  const clearSelection = () => {
    setSelectedIds(new Set());
    setSelectMode(false);
    lastSelectedIndexRef.current = null;
  };

  const viewMatches = useCallback(
    (folderValue: string | null | undefined) => {
      if (folder === 'all') return true;
      if (folder === 'unfiled') return !folderValue;
      return folder === folderValue;
    },
    [folder]
  );

  const moveItems = useCallback(
    async (ids: string[], toFolderId: string | null) => {
      const idSet = new Set(ids);
      const moving = items.filter((n) => idSet.has(bookmarkId(n)) && (n.folder || null) !== toFolderId);
      if (!moving.length) return;
      const prevItems = items;
      const prevFolders = folders;
      const folderName = toFolderId ? folders.find((f) => f.id === toFolderId)?.name ?? null : null;
      const beforeByNovel = new Map(moving.map((n) => [n.id, n.folder || null]));

      setItems((prev) =>
        prev
          .map((n) =>
            idSet.has(bookmarkId(n)) ? { ...n, folder: toFolderId, folder_name: folderName } : n
          )
          .filter((n) => viewMatches(n.folder))
      );
      setFolders((prev) =>
        prev.map((f) => {
          let count = f.count;
          for (const n of moving) {
            if (beforeByNovel.get(n.id) === f.id) count -= 1;
            if (toFolderId === f.id) count += 1;
          }
          return { ...f, count: Math.max(0, count) };
        })
      );

      try {
        await Promise.all(
          moving
            .filter((n) => n.bookmark_id)
            .map((n) => userService.updateLibraryItem(n.bookmark_id as string, { folder: toFolderId }))
        );
      } catch (err) {
        console.error('Error moving library items:', err);
        setItems(prevItems);
        setFolders(prevFolders);
        setActionError(t('library.loadFailed'));
      }
    },
    [items, folders, viewMatches, t]
  );

  const removeItems = useCallback(
    async (ids: string[]) => {
      const idSet = new Set(ids);
      const removing = items.filter((n) => idSet.has(bookmarkId(n)));
      if (!removing.length) return;
      const prevItems = items;
      const prevFolders = folders;
      const prevCount = allCount;

      setItems((prev) => prev.filter((n) => !idSet.has(bookmarkId(n))));
      setAllCount((c) => Math.max(0, c - removing.length));
      setFolders((prev) =>
        prev.map((f) => {
          const delta = removing.filter((n) => (n.folder || null) === f.id).length;
          return { ...f, count: Math.max(0, f.count - delta) };
        })
      );
      clearSelection();

      try {
        await Promise.all(removing.map((n) => userService.removeNovelBookmark(n.slug)));
      } catch (err) {
        console.error('Error removing library items:', err);
        setItems(prevItems);
        setFolders(prevFolders);
        setAllCount(prevCount);
        setActionError(t('library.loadFailed'));
      }
    },
    [items, folders, allCount, t]
  );

  const handleDragStart = (event: DragStartEvent) => {
    const id = String(event.active.id);
    const ids = selectedIds.has(id) && selectedIds.size > 1 ? [...selectedIds] : [id];
    activeDragIdsRef.current = ids;
    setActiveDragIds(ids);
  };

  const handleDragEnd = async (event: DragEndEvent) => {
    const dragIds = activeDragIdsRef.current;
    activeDragIdsRef.current = [];
    setActiveDragIds([]);
    const { active, over } = event;
    if (!over) return;

    const overId = String(over.id);
    if (overId.startsWith('folder:')) {
      const target = overId.slice('folder:'.length);
      const toFolderId = target === 'unfiled' || target === 'all' ? null : target;
      await moveItems(dragIds, toFolderId);
      return;
    }

    if (!canReorder || dragIds.length !== 1 || active.id === over.id) return;
    const oldIndex = items.findIndex((item) => bookmarkId(item) === active.id);
    const newIndex = items.findIndex((item) => bookmarkId(item) === over.id);
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

  const handleNoteSave = async () => {
    if (!noteDialog.novel?.bookmark_id) return;
    const novelId = noteDialog.novel.id;
    const value = noteDialog.value;
    try {
      await userService.updateLibraryItem(noteDialog.novel.bookmark_id, { note: value });
      setItems((prev) =>
        prev.map((item) => (item.id === novelId ? { ...item, note: value || null } : item))
      );
      setNoteDialog({ open: false, novel: null, value: '' });
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

  const activeNovel = useMemo(
    () => items.find((n) => bookmarkId(n) === activeDragIds[0]) || null,
    [items, activeDragIds]
  );

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

  const grid = (
    <Grid container spacing={{ xs: 1.5, md: 2 }}>
      {items.map((novel) => (
        <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
          <LibraryNovelCard
            novel={novel}
            editable
            selectable
            selected={selectedIds.has(bookmarkId(novel))}
            selectionActive={selectionActive}
            onToggleSelect={toggleSelect}
            sortable={canReorder}
            draggable
            onRate={handleRate}
            onEditNote={(n) => setNoteDialog({ open: true, novel: n, value: n.note || '' })}
            onMove={(n, f) => moveItems([bookmarkId(n)], f)}
            onRemove={(n) => setRemoveConfirm([bookmarkId(n)])}
            folders={folders}
          />
        </Grid>
      ))}
    </Grid>
  );

  return (
    <Box sx={{ px: { xs: 2, sm: 3 }, pb: selectedIds.size > 0 ? 10 : 0 }}>
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

      <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
        <TextField
          size="small"
          placeholder={t('library.searchPlaceholder')}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: '1 1 240px', minWidth: 200 }}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon fontSize="small" />
                </InputAdornment>
              ),
            },
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
        <Button
          variant={selectMode ? 'contained' : 'outlined'}
          startIcon={<DoneAllIcon />}
          onClick={() => {
            if (selectMode) clearSelection();
            else setSelectMode(true);
          }}
        >
          {t('library.select')}
        </Button>
      </Box>

      <LibraryFolderBar
        folders={folders}
        totalCount={allCount}
        selected={folder}
        onSelect={setFolder}
        editable
        dragActive={activeDragIds.length > 0}
        onCreate={() => setFolderDialog({ open: true, folder: null, value: '' })}
        onRename={(value) => setFolderDialog({ open: true, folder: value, value: value.name })}
        onDelete={(value) => setDeleteFolder(value)}
      />

      <Divider sx={{ mb: 2 }} />

      {actionError && (
        <Alert severity="error" onClose={() => setActionError(null)} sx={{ mb: 2 }}>
          {actionError}
        </Alert>
      )}

      <DndContext
        sensors={sensors}
        collisionDetection={collisionDetection}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onDragCancel={() => {
          activeDragIdsRef.current = [];
          setActiveDragIds([]);
        }}
      >
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
        ) : canReorder ? (
          <SortableContext items={items.map(bookmarkId)} strategy={rectSortingStrategy}>
            {grid}
          </SortableContext>
        ) : (
          grid
        )}

        {totalPages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
            <Pagination
              count={totalPages}
              page={page}
              onChange={handlePageChange}
              color="primary"
              size="small"
            />
          </Box>
        )}

        <DragOverlay dropAnimation={null}>
          {activeNovel && (
            <Box
              sx={{
                position: 'relative',
                width: 110,
                borderRadius: 2,
                overflow: 'hidden',
                boxShadow: 12,
                transform: 'rotate(3deg)',
                opacity: 0.95,
              }}
            >
              <Box
                component="img"
                src={activeNovel.reading_source?.cover_min_url || activeNovel.prefered_source?.cover_min_url || defaultCover}
                alt=""
                sx={{ width: '100%', display: 'block' }}
              />
              {activeDragIds.length > 1 && (
                <Box
                  sx={{
                    position: 'absolute',
                    top: 4,
                    right: 4,
                    bgcolor: 'primary.main',
                    color: 'primary.contrastText',
                    borderRadius: '50%',
                    width: 24,
                    height: 24,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '0.75rem',
                    fontWeight: 'bold',
                  }}
                >
                  {activeDragIds.length}
                </Box>
              )}
            </Box>
          )}
        </DragOverlay>
      </DndContext>

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

      {/* Floating bulk-action bar */}
      <Fade in={selectedIds.size > 0} mountOnEnter unmountOnExit>
        <Paper
          elevation={8}
          sx={{
            position: 'fixed',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: theme.zIndex.snackbar,
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: 2,
            py: 1,
            borderRadius: 5,
          }}
        >
          <Typography variant="subtitle2" sx={{ mr: 1 }}>
            {t('library.selectedCount', { count: selectedIds.size })}
          </Typography>
          <Button
            variant="contained"
            size="small"
            startIcon={<FolderIcon />}
            onClick={(e) => setBulkMenuAnchor(e.currentTarget)}
          >
            {t('library.moveTo')}
          </Button>
          <Button
            color="error"
            size="small"
            startIcon={<DeleteOutlineIcon />}
            onClick={() => setRemoveConfirm([...selectedIds])}
          >
            {t('library.removeFromLibrary')}
          </Button>
          <IconButton size="small" onClick={clearSelection} aria-label={t('library.clearSelection')}>
            <CloseIcon fontSize="small" />
          </IconButton>
        </Paper>
      </Fade>

      <Menu
        anchorEl={bulkMenuAnchor}
        open={Boolean(bulkMenuAnchor)}
        onClose={() => setBulkMenuAnchor(null)}
      >
        {folders.map((f) => (
          <MenuItem
            key={f.id}
            onClick={() => {
              const ids = [...selectedIds];
              setBulkMenuAnchor(null);
              moveItems(ids, f.id);
            }}
          >
            <FolderIcon fontSize="small" sx={{ mr: 1 }} />
            {f.name}
          </MenuItem>
        ))}
        <Divider />
        <MenuItem
          onClick={() => {
            const ids = [...selectedIds];
            setBulkMenuAnchor(null);
            moveItems(ids, null);
          }}
        >
          <FolderOffIcon fontSize="small" sx={{ mr: 1 }} />
          {t('library.unfiled')}
        </MenuItem>
        <MenuItem
          onClick={() => {
            setBulkMenuAnchor(null);
            setFolderDialog({ open: true, folder: null, value: '' });
          }}
        >
          {t('library.newFolder')}
        </MenuItem>
      </Menu>

      {/* Note dialog */}
      <Dialog
        open={noteDialog.open}
        onClose={() => setNoteDialog({ open: false, novel: null, value: '' })}
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
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setNoteDialog({ open: false, novel: null, value: '' })}>
            {t('common.cancel')}
          </Button>
          <Button variant="contained" onClick={handleNoteSave}>{t('common.save')}</Button>
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

      {/* Remove from library confirmation */}
      <Dialog open={Boolean(removeConfirm)} onClose={() => setRemoveConfirm(null)}>
        <DialogTitle>{t('library.removeConfirmTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('library.removeConfirmBody', { count: removeConfirm?.length ?? 0 })}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRemoveConfirm(null)}>{t('common.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              const ids = removeConfirm ?? [];
              setRemoveConfirm(null);
              removeItems(ids);
            }}
          >
            {t('common.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default LibraryPage;
