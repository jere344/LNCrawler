import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Grid as Grid,
  Alert,
  CircularProgress,
  Paper,
  TextField,
  InputAdornment,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Button,
  Drawer,
  Pagination,
  useMediaQuery,
} from '@mui/material';
import { useTheme } from '@mui/material/styles';
import SearchIcon from '@mui/icons-material/Search';
import FolderIcon from '@mui/icons-material/Folder';
import { profileService } from '@services/profile.service';
import LibraryNovelCard from '@components/library/LibraryNovelCard';
import LibraryFolderSidebar from '@components/library/LibraryFolderSidebar';
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
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));

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
  const [mobileFoldersOpen, setMobileFoldersOpen] = useState(false);

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

  const sidebar = (
    <LibraryFolderSidebar
      folders={folders}
      totalCount={allCount}
      selected={folder}
      onSelect={(value) => {
        setFolder(value);
        setMobileFoldersOpen(false);
      }}
    />
  );

  const grid = (
    <Grid container spacing={2}>
      {items.map((novel) => (
        <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
          <LibraryNovelCard novel={novel} editable={false} showRating={showRatings} />
        </Grid>
      ))}
    </Grid>
  );

  return (
    <Box>
      {(!showNotes || !showRatings) && (
        <Alert severity="info" sx={{ mb: 2 }}>
          {t('library.mirrorHidden')}
        </Alert>
      )}

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
          <Select label={t('library.sortBy')} value={sort} onChange={(e) => setSort(e.target.value)}>
            <MenuItem value="custom">{t('library.sort.custom')}</MenuItem>
            <MenuItem value="title">{t('library.sort.title')}</MenuItem>
            <MenuItem value="date_added">{t('library.sort.date_added')}</MenuItem>
            {showRatings && <MenuItem value="rating">{t('library.sort.rating')}</MenuItem>}
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
            <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
              <CircularProgress />
            </Box>
          ) : items.length === 0 ? (
            <Alert severity="info">{t('profile.emptySection')}</Alert>
          ) : (
            grid
          )}

          {totalPages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
              <Pagination
                count={totalPages}
                page={page}
                onChange={(_, value) => fetchLibrary(value)}
                color="primary"
                size={isMobile ? 'small' : 'medium'}
              />
            </Box>
          )}
        </Box>
      </Box>

      <Drawer anchor="left" open={isMobile && mobileFoldersOpen} onClose={() => setMobileFoldersOpen(false)}>
        <Box sx={{ width: 260, p: 2 }}>{sidebar}</Box>
      </Drawer>
    </Box>
  );
};

export default PublicLibraryTab;
