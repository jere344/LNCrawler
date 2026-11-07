import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Grid as Grid,
  Alert,
  CircularProgress,
  TextField,
  InputAdornment,
  Divider,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import { DndContext } from '@dnd-kit/core';
import { profileService } from '@services/profile.service';
import type { LibrarySort } from '@services/user.service';
import LibraryNovelCard from '@components/library/LibraryNovelCard';
import LibraryFolderBar from '@components/library/LibraryFolderBar';
import LibrarySortSelect from '@components/common/LibrarySortSelect';
import PageNav from '@components/common/PageNav';
import { LibraryFolder, LibraryNovel } from '@models/novels_types';
import { useDebounce } from '@utils/useDebounce';
import { useTranslation } from 'react-i18next';

interface PublicLibraryTabProps {
  username: string;
  showNotes: boolean;
  showRatings: boolean;
}

const PublicLibraryTab: React.FC<PublicLibraryTabProps> = ({ username, showNotes, showRatings }) => {
  const { t } = useTranslation();

  const [items, setItems] = useState<LibraryNovel[]>([]);
  const [folders, setFolders] = useState<LibraryFolder[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [allCount, setAllCount] = useState(0);
  const [folder, setFolder] = useState('all');
  const [sort, setSort] = useState<LibrarySort>('custom');
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
        <LibrarySortSelect value={sort} onChange={setSort} showRating={showRatings} />
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

      <PageNav
        page={page}
        totalPages={totalPages}
        onChange={(value) => fetchLibrary(value)}
        size="small"
        sx={{ my: 4 }}
      />
    </Box>
  );
};

export default PublicLibraryTab;
