import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Container,
  FormControlLabel,
  Grid,
  Menu,
  MenuItem,
  Pagination,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import RssFeedIcon from '@mui/icons-material/RssFeed';
import SearchIcon from '@mui/icons-material/Search';
import { useAuth } from '@context/AuthContext';
import { useAdultContent } from '@context/AdultContentContext';
import { useNotification } from '@context/NotificationContext';
import { audiobookService } from '@services/audiobook.service';
import { novelService } from '@services/novel.service';
import type { AudiobookCard as AudiobookCardData, AudiobookListResponse, AudiobookSort } from '@models/audiobook_types';
import { languageCodeToName, languageFlagUrl } from '@utils/Misc';
import { useDebounce } from '@utils/useDebounce';
import { useUrlListState, useUrlSearch } from '@utils/useUrlListState';
import SeoMeta from '../common/SeoMeta';
import AudiobookCard from './AudiobookCard';
import PodcastAppHelpDialog from './PodcastAppHelpDialog';
import { AudiobookGridSkeleton } from './AudiobooksSkeleton';

const SORTS: AudiobookSort[] = ['popular', 'new', 'updated', 'longest'];
const PAGE_SIZE = 24;

// Adult filter of the catalog RSS feed (?adult=), see the backend feed view.
type CatalogAdult = 'exclude' | 'include' | 'only';

const AudiobooksPage = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const { notify } = useNotification();
  const { showR18 } = useAdultContent();
  // Guests and 'blur'/'yes' viewers may see adult entries; 'no' viewers never get them.
  const adultVisible = showR18 !== 'no';
  const { searchParams, setParams } = useUrlListState();
  const [, setSearchParams] = useSearchParams();
  const [query, setQuery] = useUrlSearch('q');

  const sort = (SORTS.find(s => s === searchParams.get('sort')) ?? 'popular') as AudiobookSort;
  const tags = searchParams.getAll('tag');
  const listening = isAuthenticated && searchParams.get('listening') === '1';
  const lang = searchParams.get('lang') || '';
  const page = Math.max(1, Number(searchParams.get('page')) || 1);
  const urlQuery = searchParams.get('q') || '';
  const hasFilters = Boolean(urlQuery || tags.length || listening || lang);

  const [result, setResult] = useState<AudiobookListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [rssAnchor, setRssAnchor] = useState<HTMLElement | null>(null);

  const [tagInput, setTagInput] = useState('');
  const debouncedTagInput = useDebounce(tagInput);
  const [tagOptions, setTagOptions] = useState<string[]>([]);

  // Fetch the page whenever the list state in the URL changes.
  const listKey = searchParams.toString();
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(false);
    audiobookService
      .list({
        sort,
        q: urlQuery || undefined,
        tag: tags,
        listening: listening || undefined,
        lang: lang || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      .then((response) => { if (!cancelled) setResult(response); })
      .catch(() => { if (!cancelled) setError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the serialized URL state
  }, [listKey]);

  // Tag suggestions, from the same endpoint as the search page.
  useEffect(() => {
    if (debouncedTagInput.length < 1) {
      setTagOptions([]);
      return;
    }
    let cancelled = false;
    novelService
      .getAutocompleteSuggestions('tag', debouncedTagInput)
      .then((suggestions) => { if (!cancelled) setTagOptions(suggestions.map(s => s.name)); })
      .catch(() => { if (!cancelled) setTagOptions([]); });
    return () => { cancelled = true; };
  }, [debouncedTagInput]);

  // Arrays go straight to the URL: useUrlListState only writes single values.
  const setTags = (next: string[]) => {
    setSearchParams((current) => {
      const params = new URLSearchParams(current);
      params.delete('tag');
      next.forEach(tag => params.append('tag', tag));
      params.delete('page');
      return params;
    });
  };

  const items: AudiobookCardData[] = result?.results ?? [];
  const catalogFeedUrl = result?.catalog_feed_url ?? '';
  const languages = result?.languages ?? [];

  const copyCatalogFeed = async (adult: CatalogAdult) => {
    setRssAnchor(null);
    try {
      await navigator.clipboard.writeText(`${catalogFeedUrl}?adult=${adult}`);
      notify({ message: t('audiobooks.feedCopied'), severity: 'success' });
    } catch {
      notify({ message: t('audiobooks.feedCopyError'), severity: 'error' });
    }
  };
  const pageTitle = t('audiobooks.title');
  const pageDescription = t('audiobooks.metaDescription');

  return (
    <Container maxWidth="lg" sx={{ py: 3 }}>
      <SeoMeta
        title={pageTitle}
        description={pageDescription}
        canonical={`${window.location.origin}/audiobooks/`}
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} sx={{ alignItems: { sm: 'flex-end' }, justifyContent: 'space-between', gap: 1 }}>
        <Box>
          <Typography variant="h4" component="h1" sx={{ fontWeight: 700 }}>{pageTitle}</Typography>
          <Typography variant="body1" color="text.secondary">{t('audiobooks.pitch')}</Typography>
        </Box>
        <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', alignSelf: { xs: 'flex-start', sm: 'auto' } }}>
          <Button startIcon={<InfoOutlinedIcon />} onClick={() => setHelpOpen(true)}>
            {t('audiobooks.podcastHelpLink')}
          </Button>
          {catalogFeedUrl && (
            <Button startIcon={<RssFeedIcon />} aria-haspopup="menu" onClick={(event) => setRssAnchor(event.currentTarget)}>
              {t('audiobooks.catalogRss')}
            </Button>
          )}
          <Menu anchorEl={rssAnchor} open={Boolean(rssAnchor)} onClose={() => setRssAnchor(null)}>
            <MenuItem onClick={() => void copyCatalogFeed('exclude')}>{t('audiobooks.catalogRssNoAdult')}</MenuItem>
            {adultVisible && (
              <MenuItem onClick={() => void copyCatalogFeed('include')}>{t('audiobooks.catalogRssAll')}</MenuItem>
            )}
            {adultVisible && (
              <MenuItem onClick={() => void copyCatalogFeed('only')}>{t('audiobooks.catalogRssAdultOnly')}</MenuItem>
            )}
          </Menu>
        </Stack>
      </Stack>

      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} sx={{ my: 2, alignItems: { md: 'center' } }}>
        <TextField
          size="small"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={t('audiobooks.searchPlaceholder')}
          aria-label={t('audiobooks.searchPlaceholder')}
          slotProps={{ input: { startAdornment: <SearchIcon fontSize="small" sx={{ mr: 1, color: 'text.secondary' }} /> } }}
          sx={{ minWidth: { md: 240 } }}
        />
        <TextField
          select
          size="small"
          label={t('audiobooks.sortLabel')}
          value={sort}
          onChange={(event) => setParams({ sort: event.target.value, page: null })}
          sx={{ minWidth: 160 }}
        >
          {SORTS.map(option => (
            <MenuItem key={option} value={option}>{t(`audiobooks.sort.${option}`)}</MenuItem>
          ))}
        </TextField>
        {(languages.length > 1 || lang) && (
          <TextField
            select
            size="small"
            label={t('audiobooks.languageLabel')}
            value={lang}
            onChange={(event) => setParams({ lang: event.target.value || null, page: null })}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">{t('audiobooks.allLanguages')}</MenuItem>
            {/* A language from the URL that no longer has audiobooks stays listed, so the select can show it */}
            {(lang && !languages.includes(lang) ? [...languages, lang] : languages).map(code => (
              <MenuItem key={code} value={code} sx={{ gap: 1 }}>
                <Box
                  component="img"
                  src={languageFlagUrl(code)}
                  alt=""
                  sx={{ width: 20, height: 15, objectFit: 'cover', borderRadius: '2px', flexShrink: 0 }}
                />
                {languageCodeToName(t, code)}
              </MenuItem>
            ))}
          </TextField>
        )}
        <Autocomplete
          multiple
          size="small"
          options={tagOptions}
          value={tags}
          inputValue={tagInput}
          onInputChange={(_, value) => setTagInput(value)}
          onChange={(_, value) => setTags(value)}
          filterOptions={(options) => options}
          sx={{ flex: 1, minWidth: 0 }}
          renderInput={(params) => (
            <TextField {...params} label={t('audiobooks.tagsLabel')} placeholder={t('audiobooks.tagsPlaceholder')} />
          )}
        />
        {isAuthenticated && (
          <FormControlLabel
            control={
              <Switch
                checked={listening}
                onChange={(event) => setParams({ listening: event.target.checked ? '1' : null, page: null })}
              />
            }
            label={t('audiobooks.myAudiobooks')}
            sx={{ whiteSpace: 'nowrap' }}
          />
        )}
      </Stack>

      {error && <Alert severity="error">{t('audiobooks.loadError')}</Alert>}

      {!error && loading && <AudiobookGridSkeleton count={PAGE_SIZE} />}

      {!error && !loading && items.length === 0 && (
        <Box sx={{ py: 6, textAlign: 'center' }}>
          <Typography variant="h6" component="p">
            {hasFilters ? t('audiobooks.emptyFiltered') : t('audiobooks.empty')}
          </Typography>
          {hasFilters && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>{t('audiobooks.emptyFilteredHint')}</Typography>
          )}
        </Box>
      )}

      {!error && !loading && items.length > 0 && (
        <>
          <Grid container spacing={2}>
            {items.map(book => (
              <Grid key={`${book.slug}-${book.language}`} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                <AudiobookCard book={book} />
              </Grid>
            ))}
          </Grid>
          {result && result.total_pages > 1 && (
            <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
              <Pagination
                count={result.total_pages}
                page={result.current_page}
                color="primary"
                onChange={(_, value) => setParams({ page: value > 1 ? String(value) : null })}
              />
            </Box>
          )}
        </>
      )}

      <PodcastAppHelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} />
    </Container>
  );
};

export default AudiobooksPage;
