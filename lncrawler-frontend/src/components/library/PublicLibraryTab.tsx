import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Grid as Grid,
  Alert,
  CircularProgress,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Divider,
  Pagination,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { DndContext } from '@dnd-kit/core';
import { profileService } from '@services/profile.service';
import LibraryNovelCard from '@components/library/LibraryNovelCard';
import LibraryFolderBar from '@components/library/LibraryFolderBar';
import { LibraryFolder, Novel } from '@models/novels_types';
import { useDebounce } from '@utils/useDebounce';
import { useTranslation } from 'react-i18next';

interface PublicLibraryTabProps {
  username: string;
  showNotes: boolean;
  showRatings: boolean;
}

const PublicLibraryTab: React.FC<PublicLibraryTabProps> = ({ username, showNotes, showRatings }) => {
  const { t } = useTranslation();

  const [items, setItems] = useState<Novel[]>([]);
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [allCount, setAllCount] = useState(0);
  const [folder, setFolder] = useState('all');
  const [sort, setSort] = useState('custom');
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search);

  const fetchLibrary = useCallback(
    async (pageNum = 1) => {
      try {
        setLoading(true);
        const data = await profileService.getUserLibrary(username, {
          page: pageNum,
          search: debouncedSearch,
          folder,
          sort,
        });
        setItems(data.results);
        setFolders(data.folders || []);
        setTotalPages(data.total_pages);
        setPage(data.current_page);
        if (folder === 'all' && !debouncedSearch) {
          setAllCount(data.count);
        }
      } catch (err) {
        console.error('Error loading library:', err);
      } finally {
        setLoading(false);
      }
    },
    [username, debouncedSearch, folder, sort]
  );

  useEffect(() => {
    fetchLibrary(1);
  }, [fetchLibrary]);

  return (
    <Box>
      {(!showNotes || !showRatings) && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('library.mirrorHidden')}
        </Alert>
      )}

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
          <Select label={t('library.sortBy')} value={sort} onChange={(e) => setSort(e.target.value)}>
            <MenuItem value="custom">{t('library.sort.custom')}</MenuItem>
            <MenuItem value="title">{t('library.sort.title')}</MenuItem>
            <MenuItem value="date_added">{t('library.sort.date_added')}</MenuItem>
            {showRatings && <MenuItem value="rating">{t('library.sort.rating')}</MenuItem>}
          </Select>
        </FormControl>
      </Box>

      <DndContext>
        <LibraryFolderBar
          folders={folders}
          totalCount={allCount}
          selected={folder}
          onSelect={setFolder}
        />
      </DndContext>

      <Divider sx={{ mb: 2 }} />

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : items.length === 0 ? (
        <Alert severity="info">{t('profile.emptySection')}</Alert>
      ) : (
        <Grid container spacing={{ xs: 1.5, md: 2 }}>
          {items.map((novel) => (
            <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
              <LibraryNovelCard
                novel={novel}
                editable={false}
                showRating={showRatings}
                showNote={showNotes}
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
            onChange={(_, value) => fetchLibrary(value)}
            color="primary"
            size="small"
          />
        </Box>
      )}
    </Box>
  );
};

export default PublicLibraryTab;
