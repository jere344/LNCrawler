import { useState, useEffect, useMemo, use } from 'react';
import { useDebounce } from '@utils/useDebounce';
import { useParams, useLoaderData, useNavigation, useSearchParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Container,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Box,
  Button,
  CircularProgress,
  Divider,
  TextField,
  InputAdornment,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Stack,
  SelectChangeEvent,
  Grid as Grid,
  Alert,
} from '@mui/material';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SearchIcon from '@mui/icons-material/Search';
import { Chapter } from '@models/novels_types';
import BreadcrumbNav from '../common/BreadcrumbNav';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import { getChapterLabel } from '@utils/Misc';
import SeoMeta, { DEFAULT_OG_IMAGE } from '../common/SeoMeta';
import type { AsyncData, ChapterListLoaderData } from '../../router/loaders';

const ChapterList = () => {
  const { t } = useTranslation();
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const { data: chapterListPromise } = useLoaderData() as AsyncData<ChapterListLoaderData>;
  const loaderData = use(chapterListPromise);
  const navigation = useNavigation();
  const [searchParams, setSearchParams] = useSearchParams();

  const chapterData = loaderData.ok ? loaderData.data : null;
  const error = loaderData.ok ? null : t('chapterList.loadFailed');
  const loading = navigation.state === 'loading';
  const pageSize = Number(searchParams.get('page_size')) || 100;

  const [searchTerm, setSearchTerm] = useState<string>(searchParams.get('q') || '');
  const debouncedSearch = useDebounce(searchTerm);

  // Mirror the debounced search into the URL so the loader owns the request.
  useEffect(() => {
    if (debouncedSearch === (searchParams.get('q') || '')) return;
    const next = new URLSearchParams(searchParams);
    if (debouncedSearch) next.set('q', debouncedSearch);
    else next.delete('q');
    next.delete('page');
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only react to the debounced value
  }, [debouncedSearch]);

  // Keep the input in sync when the URL changes (back/forward or another source).
  useEffect(() => {
    setSearchTerm(searchParams.get('q') || '');
  }, [novelSlug, sourceSlug, searchParams]);

  // Organize chapters by volume
  const { volumeChapters, volumes } = useMemo(() => {
    const chaptersByVolume: { [key: number]: Chapter[] } = {};
    const volumeList: Set<number> = new Set();

    (chapterData?.chapters ?? []).forEach((chapter: Chapter) => {
      const volume = chapter.volume || 0;
      volumeList.add(volume);
      if (!chaptersByVolume[volume]) {
        chaptersByVolume[volume] = [];
      }
      chaptersByVolume[volume].push(chapter);
    });

    return { volumeChapters: chaptersByVolume, volumes: Array.from(volumeList).sort((a, b) => a - b) };
  }, [chapterData]);

  const handlePageChange = (_event: React.ChangeEvent<unknown>, value: number) => {
    const next = new URLSearchParams(searchParams);
    next.set('page', String(value));
    setSearchParams(next);
  };

  const handlePageSizeChange = (event: SelectChangeEvent<number>) => {
    const next = new URLSearchParams(searchParams);
    next.set('page_size', String(Number(event.target.value)));
    next.delete('page');
    setSearchParams(next);
  };

  const pageUrl = window.location.href;

  const metaTitle = chapterData 
    ? t('chapterList.metaTitle', { novel: chapterData.novel_title, source: chapterData.source_name }) 
    : t('chapterList.metaLoadingTitle');
  const metaDescription = chapterData 
    ? t('chapterList.metaDescription', { count: chapterData.count, novel: chapterData.novel_title, source: chapterData.source_name })
    : t('chapterList.metaLoadingDescription');
  // i18n-missing: no catalog key for the chapter-list fallback keywords
  const metaKeywords = chapterData 
    ? t('chapterList.keywords', { novel: chapterData.novel_title, source: chapterData.source_name })
    : "chapter list, light novel, web novel";
  const ogImage = chapterData?.source_overview_image_url || DEFAULT_OG_IMAGE;
  if (loading && !chapterData) {
    return (
      <Container>
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error || !chapterData) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} component={Link} to={`/`} sx={{ mt: 2 }}>
          {t('chapterList.backToNovels')}
        </Button>
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || t('chapterList.notFound')}</Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="md">
      <SeoMeta
        title={metaTitle}
        description={metaDescription.substring(0, 160)}
        keywords={metaKeywords}
        image={ogImage}
        canonical={pageUrl}
      />

      {!loading && chapterData && (
        <BreadcrumbNav
          items={[
            {
              label: chapterData.novel_title,
              icon: <BookIcon fontSize="inherit" />
            },
            {
              label: chapterData.source_name,
              link: `/novels/${novelSlug}/${sourceSlug}`,
              icon: <LanguageIcon fontSize="inherit" />
            },
            {
              label: t('chapterList.chapters'),
              icon: <ListAltIcon fontSize="inherit" />
            }
          ]}
        />
      )}

      <Button component={Link} to={`/novels/${novelSlug}/${sourceSlug}`} startIcon={<ArrowBackIcon />} sx={{ mt: 2 }}>
        {t('chapterList.backToSource')}
      </Button>

      {chapterData.is_dmca && (
        <Alert severity="error" sx={{ mt: 2 }}>
          {t('chapterList.dmcaNotice')}
        </Alert>
      )}

      <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
        <Typography variant="h4" gutterBottom>
          {chapterData.novel_title}
        </Typography>
        
        <Typography variant="subtitle1" gutterBottom sx={{
          color: "text.secondary"
        }}>
          {t('chapterList.sourcePrefix')} {chapterData.source_name}
        </Typography>
        
        <Box sx={{ mt: 3, mb: 2 }}>
          <TextField
            fullWidth
            placeholder={t('chapterList.searchPlaceholder')}
            variant="outlined"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
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

        <Box sx={{ mt: 3, mb: 3 }}>
          <Grid container spacing={2} sx={{
            alignItems: "center"
          }}>
            <Grid>
              <Typography variant="subtitle1">
                {t('chapterList.totalChapters', { count: chapterData.count })}
              </Typography>
            </Grid>
            <Grid size="grow">
              <Stack
                direction="row"
                spacing={2}
                sx={{
                  alignItems: "center",
                  justifyContent: "flex-end"
                }}>
                <Typography variant="body2">
                  {t('chapterList.pageOf', { current: chapterData.current_page, total: chapterData.total_pages })}
                </Typography>
                <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
                  <InputLabel id="page-size-label">{t('chapterList.perPage')}</InputLabel>
                  <Select
                    labelId="page-size-label"
                    value={pageSize}
                    onChange={handlePageSizeChange}
                    label={t('chapterList.perPage')}
                  >
                    <MenuItem value={50}>50</MenuItem>
                    <MenuItem value={100}>100</MenuItem>
                    <MenuItem value={200}>200</MenuItem>
                    <MenuItem value={500}>500</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            </Grid>
          </Grid>
        </Box>

        {chapterData.total_pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
            <Pagination 
              count={chapterData.total_pages} 
              page={chapterData.current_page}
              onChange={handlePageChange} 
              color="primary" 
              showFirstButton 
              showLastButton
            />
          </Box>
        )}
        
        {volumes.length > 0 ? (
          volumes.map(volume => {
            if (!volumeChapters[volume] || volumeChapters[volume].length === 0) return null;
            
            const volumeTitle = volumeChapters[volume][0].volume_title || t('chapterList.volume', { volume });
            const showHeader = volume !== 0 || !!volumeChapters[volume][0].volume_title;
            
            return (
              <Box key={volume} sx={{ mb: 4 }}>
                {showHeader && (
                  <>
                    <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>
                      {volumeTitle}
                    </Typography>
                    <Divider sx={{ mb: 2 }} />
                  </>
                )}
                
                <List disablePadding>
                  {volumeChapters[volume].map((chapter) => (
                    <ListItem disablePadding key={chapter.id} divider>
                      <ListItemButton 
                        component={Link}
                        to={`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.chapter_id}`}
                        disabled={!chapter.has_content}
                        sx={{
                          opacity: chapter.has_content && !chapterData.is_dmca ? 1 : 0.5,
                          '&.Mui-disabled': {
                            opacity: 0.5,
                          }
                        }}
                      >
                        <ListItemText 
                          primary={getChapterLabel(t, chapter.title, chapter.chapter_id)}
                          secondary={!chapter.has_content ? t('chapterList.contentUnavailable') : null}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              </Box>
            );
          })
        ) : (
          <Typography variant="body1" sx={{ textAlign: 'center', py: 4 }}>
            {t('chapterList.noChapters')}
          </Typography>
        )}
        
        {chapterData.total_pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
            <Pagination 
              count={chapterData.total_pages} 
              page={chapterData.current_page}
              onChange={handlePageChange} 
              color="primary" 
              showFirstButton 
              showLastButton
            />
          </Box>
        )}
      </Paper>
    </Container>
  );
};

export default ChapterList;
