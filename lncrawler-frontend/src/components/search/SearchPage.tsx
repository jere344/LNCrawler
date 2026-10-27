import React, { useEffect, useState, use } from 'react';
import { 
  Box, Container, Typography, TextField, Paper, 
  FormControl, InputLabel, Select, MenuItem, Checkbox,
  Chip, Button, FormGroup,
  FormControlLabel, Rating, IconButton, InputAdornment,
  CircularProgress, Pagination, Stack, Autocomplete,
  ToggleButton, ToggleButtonGroup,
  Grid as Grid,
} from '@mui/material';
import { useSearchParams, useLoaderData } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SearchIcon from '@mui/icons-material/Search';
import TuneIcon from '@mui/icons-material/Tune';
import SortIcon from '@mui/icons-material/Sort';
import CloseIcon from '@mui/icons-material/Close';
import { novelService } from '../../services/api';
import { defaultSortOrder } from '@services/novel.service';
import BaseNovelCard from '../common/novelcardtypes/BaseNovelCard';
import { useDebounce } from '@utils/useDebounce';
import { languageFlagUrl, availableLanguages, languageCodeToName, getNovelSourceLink } from '@utils/Misc';
import { useTheme } from '@theme/ThemeContext';
import { useLanguage } from '@context/LanguageContext';
import { useAuth } from '@context/AuthContext';
import SeoMeta from '../common/SeoMeta';
import { SearchResultsSkeleton } from './SearchSkeleton';
import type { AsyncData, SearchLoaderData } from '../../router/loaders';

type AdultFilter = 'hide' | 'show' | 'only';


interface FilterOptions {
  tags: string[];
  authors: string[];
  statuses: string[];
  languages: string[];
}

// Add these interfaces for the suggestion types
interface Suggestion {
  name: string;
  count: number;
  alias?: string;
}

// Suspends only for the first results (the page skeleton). A later search keeps
// the page and its filters on screen and reports `pending` until its results
// arrive, so only the result grid swaps to a skeleton.
const useSearchResults = (promise: Promise<SearchLoaderData>) => {
  const [first] = useState(promise);
  const firstData = use(first);
  const [settled, setSettled] = useState({ promise: first, data: firstData });
  useEffect(() => {
    if (promise === settled.promise) return;
    let live = true;
    promise.then((data) => { if (live) setSettled({ promise, data }); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [promise]);
  // Results reused on back/forward are already fulfilled (see reuseOnHistory):
  // show them in this render, so the scroll restore sees the full grid.
  const ready = promise as Promise<SearchLoaderData> & { status?: string; value?: SearchLoaderData };
  if (promise !== settled.promise && ready.status === 'fulfilled') return { data: ready.value!, pending: false };
  return { data: settled.data, pending: promise !== settled.promise };
};

const SearchPage: React.FC = () => {
  const { t } = useTranslation();
  const { contentLanguages, languageFilterEnabled } = useLanguage();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Default the adult filter from the account preference: users who allow
  // adult content (yes/blur) start on 'show', everyone else on 'hide'.
  const defaultAdult: AdultFilter =
    user?.show_r18 === 'yes' || user?.show_r18 === 'blur' ? 'show' : 'hide';

  // Results are owned by the route loader (started before the i18n gate).
  const { data: searchDataPromise } = useLoaderData() as AsyncData<SearchLoaderData>;
  const { data: loaderData, pending } = useSearchResults(searchDataPromise);
  const novels = loaderData.ok ? loaderData.data.results : [];
  const totalCount = loaderData.ok ? loaderData.data.count : 0;
  const hiddenAdult = loaderData.ok ? loaderData.data.hidden_adult ?? 0 : 0;
  const totalPages = loaderData.ok ? loaderData.data.total_pages : 1;
  const currentPage = loaderData.ok ? loaderData.data.current_page : 1;

  // Filter options
  const filterOptions: FilterOptions = {
    tags: loaderData.ok ? loaderData.data.tags || [] : [],
    authors: loaderData.ok ? loaderData.data.authors || [] : [],
    statuses: loaderData.ok ? loaderData.data.statuses || [] : [],
    languages: loaderData.ok ? loaderData.data.languages || availableLanguages : availableLanguages,
  };
  
  // State for current filters
  const [searchQuery, setSearchQuery] = useState(searchParams.get('query') || '');
  const [selectedTags, setSelectedTags] = useState<string[]>(searchParams.getAll('tag'));
  const [excludedTags, setExcludedTags] = useState<string[]>(searchParams.getAll('exclude_tag'));
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>(searchParams.getAll('author'));
  const [selectedStatus, setSelectedStatus] = useState(searchParams.get('status') || '');
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>(
    // Same convention as searchLoader: `language=` (empty) means "all languages".
    searchParams.has('language')
      ? searchParams.getAll('language').filter(Boolean)
      : languageFilterEnabled
        ? contentLanguages
        : []
  );
  const [minRating, setMinRating] = useState<number | null>(
    searchParams.get('min_rating') ? Number(searchParams.get('min_rating')) : null
  );
  const initialSortBy = searchParams.get('sort_by') || 'popularity';
  const [sortBy, setSortBy] = useState(initialSortBy);
  const [sortOrder, setSortOrder] = useState(searchParams.get('sort_order') || defaultSortOrder(initialSortBy));
  const [adult, setAdult] = useState<AdultFilter>(
    (searchParams.get('adult') as AdultFilter) || defaultAdult
  );

  // The profile loads after the first render, so re-align the toggle with its
  // default once it does (results are already correct from the server). Bail
  // out when the URL pins an explicit choice, i.e. the user touched the toggle.
  useEffect(() => {
    if (searchParams.get('adult')) return;
    setAdult(defaultAdult);
  }, [defaultAdult, searchParams]);

  // Keep the search box in sync with the committed query when navigating
  // (back/forward). Keyed on the query alone so filter changes don't wipe a draft.
  const committedQuery = searchParams.get('query') || '';
  useEffect(() => {
    setSearchQuery(committedQuery);
  }, [committedQuery]);

  // No URL rewrite here: the loader already applies the stored content languages
  // on first arrival, so the page does not navigate (and refetch) on mount.

  // State for autocomplete options
  const [tagSuggestions, setTagSuggestions] = useState<Suggestion[]>([]);
  const [authorSuggestions, setAuthorSuggestions] = useState<Suggestion[]>([]);
  
  // State for autocomplete input values
  const [tagInput, setTagInput] = useState('');
  const [excludeTagInput, setExcludeTagInput] = useState('');
  const [authorInput, setAuthorInput] = useState('');
  const debouncedTagInput = useDebounce(tagInput);
  const debouncedExcludeTagInput = useDebounce(excludeTagInput);
  const debouncedAuthorInput = useDebounce(authorInput);
  
  // State for loading suggestions
  const [loadingTags, setLoadingTags] = useState(false);
  const [loadingAuthors, setLoadingAuthors] = useState(false);
  
  // UI state
  const [showFilters, setShowFilters] = useState(false);
  
  // Fetch tag suggestions whenever the debounced input changes
  useEffect(() => {
    const query = debouncedTagInput || debouncedExcludeTagInput;
    if (query.length < 1) {
      setTagSuggestions([]);
      setLoadingTags(false);
      return;
    }
    let cancelled = false;
    setLoadingTags(true);
    novelService.getAutocompleteSuggestions('tag', query)
      .then((response) => { if (!cancelled) setTagSuggestions(response); })
      .catch((error) => {
        console.error('Error fetching tag suggestions:', error);
        if (!cancelled) setTagSuggestions([]);
      })
      .finally(() => { if (!cancelled) setLoadingTags(false); });
    return () => { cancelled = true; };
  }, [debouncedTagInput, debouncedExcludeTagInput]);

  // Fetch author suggestions whenever the debounced input changes
  useEffect(() => {
    if (debouncedAuthorInput.length < 1) {
      setAuthorSuggestions([]);
      setLoadingAuthors(false);
      return;
    }
    let cancelled = false;
    setLoadingAuthors(true);
    novelService.getAutocompleteSuggestions('author', debouncedAuthorInput)
      .then((response) => { if (!cancelled) setAuthorSuggestions(response); })
      .catch((error) => {
        console.error('Error fetching author suggestions:', error);
        if (!cancelled) setAuthorSuggestions([]);
      })
      .finally(() => { if (!cancelled) setLoadingAuthors(false); });
    return () => { cancelled = true; };
  }, [debouncedAuthorInput]);
  
  // Update search params when filters change
  const updateSearchParams = (newParams: Record<string, string | string[] | number | null>) => {
    const params = new URLSearchParams(searchParams);
    
    // Reset to page 1 when filters change
    params.set('page', '1');
    
    Object.entries(newParams).forEach(([key, value]) => {
      // Remove existing values for this key
      params.delete(key);
      
      if (value === null) {
        // Skip if value is null
      } else if (Array.isArray(value)) {
        if (key === 'language' && value.length === 0) {
          // Empty marker: the user chose "all languages" (see searchLoader).
          params.append(key, '');
        } else {
          // Add all values from array
          value.forEach(v => params.append(key, v));
        }
      } else if (value !== '') {
        // Add single value
        params.set(key, value.toString());
      }
    });

    // Filters and the query keep the reader where they are; only a page change scrolls to the top.
    setSearchParams(params, { state: { keepScroll: true } });
  };

  // Filter state as one string, so a single debounced effect can commit it to the URL.
  // adult is stored as 'default' while it matches the account default, so the
  // profile-driven realign above does not count as a user change.
  const makeFilterKey = (f: {
    tag: string[]; exclude_tag: string[]; author: string[]; status: string;
    language: string[]; min_rating: number | null; sort_by: string; sort_order: string; adult: AdultFilter;
  }) => JSON.stringify({ ...f, adult: f.adult === defaultAdult ? 'default' : f.adult });

  const filterKey = makeFilterKey({
    tag: selectedTags, exclude_tag: excludedTags, author: selectedAuthors, status: selectedStatus,
    language: selectedLanguages, min_rating: minRating, sort_by: sortBy, sort_order: sortOrder, adult,
  });
  // The same key, read from the URL. Matches the state initializers above, so the
  // key already in the URL (or the stored defaults on first arrival) counts as applied.
  const keyFromParams = (sp: URLSearchParams) => {
    const sortByParam = sp.get('sort_by') || 'popularity';
    return makeFilterKey({
      tag: sp.getAll('tag'),
      exclude_tag: sp.getAll('exclude_tag'),
      author: sp.getAll('author'),
      status: sp.get('status') || '',
      language: sp.has('language')
        ? sp.getAll('language').filter(Boolean)
        : (languageFilterEnabled ? contentLanguages : []),
      min_rating: sp.get('min_rating') ? Number(sp.get('min_rating')) : null,
      sort_by: sortByParam,
      sort_order: sp.get('sort_order') || defaultSortOrder(sortByParam),
      adult: (sp.get('adult') as AdultFilter) || defaultAdult,
    });
  };
  const debouncedFilterKey = useDebounce(filterKey, 400);

  // Back/forward (or any outside URL change): pull the filters back from the URL,
  // so the debounced commit below never writes stale state over the history entry.
  const urlFilterKey = keyFromParams(searchParams);
  useEffect(() => {
    if (urlFilterKey === filterKey) return;
    const f = JSON.parse(urlFilterKey) as {
      tag: string[]; exclude_tag: string[]; author: string[]; status: string;
      language: string[]; min_rating: number | null; sort_by: string; sort_order: string; adult: string;
    };
    setSelectedTags(f.tag);
    setExcludedTags(f.exclude_tag);
    setSelectedAuthors(f.author);
    setSelectedStatus(f.status);
    setSelectedLanguages(f.language);
    setMinRating(f.min_rating);
    setSortBy(f.sort_by);
    setSortOrder(f.sort_order);
    setAdult(f.adult === 'default' ? defaultAdult : f.adult as AdultFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlFilterKey]);

  // Auto-apply filter changes (debounced). Uses the committed query from the URL,
  // not the draft in the search box, which still needs its own submit.
  // The URL is the reference for what is applied, so equal keys are a no-op.
  useEffect(() => {
    if (debouncedFilterKey === keyFromParams(searchParams)) return;
    const f = JSON.parse(debouncedFilterKey) as {
      tag: string[]; exclude_tag: string[]; author: string[]; status: string;
      language: string[]; min_rating: number | null; sort_by: string; sort_order: string; adult: string;
    };
    updateSearchParams({
      query: searchParams.get('query'),
      tag: f.tag,
      exclude_tag: f.exclude_tag,
      author: f.author,
      status: f.status,
      language: f.language,
      min_rating: f.min_rating,
      sort_by: f.sort_by,
      sort_order: f.sort_order,
      adult: f.adult === 'default' ? null : f.adult,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedFilterKey]);
  
  const { setThemeById, availableThemes } = useTheme();

  // Handle search form submission
  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    for (const theme of availableThemes) {
      if (theme.password === searchQuery) {
        setThemeById(theme.id);
        return;
      }
    }
    updateSearchParams({ query: searchQuery });
  };
  
  // Handle page change
  const handlePageChange = (_: React.ChangeEvent<unknown>, page: number) => {
    const params = new URLSearchParams(searchParams);
    params.set('page', page.toString());
    setSearchParams(params);
  };
  
  // Handle clear filters
  const handleClearFilters = () => {
    setSearchQuery('');
    setSelectedTags([]);
    setExcludedTags([]);
    setSelectedAuthors([]);
    setSelectedStatus('');
    setSelectedLanguages([]);
    setMinRating(null);
    setSortBy('popularity');
    setSortOrder('desc');
    setAdult(defaultAdult);

    // Reset URL params to default. The empty `language` marker means "all languages".
    setSearchParams(new URLSearchParams({ page: '1', language: '' }));
  };


  const pageUrl = window.location.href;
  const baseTitle = t('search.metaDefaultTitle');
  const queryTitle = searchQuery ? t('search.metaQueryTitle', { query: searchQuery }) : baseTitle;

  const metaTitle = queryTitle;
  
  let description = t('search.metaDescription');
  if (searchQuery) {
    description = t('search.metaQueryDescription', { query: searchQuery, count: totalCount });
  }
  const metaDescription = description.substring(0, 160);

  const keywordsList = t('search.metaKeywords').split(', ');
  if (searchQuery) keywordsList.push(searchQuery);
  selectedTags.forEach(tag => keywordsList.push(tag));
  selectedAuthors.forEach(author => keywordsList.push(author));
  selectedLanguages.forEach(code => keywordsList.push(languageCodeToName(t, code)));
  const metaKeywords = keywordsList.join(', ');

  // Tag suggestions may carry a merged-away alias; show it as a hint while the
  // canonical name stays the value used for filtering.
  const suggestionLabel = (option: string | Suggestion) => {
    if (typeof option === 'string') return option;
    return t('search.optionWithCount', { name: option.name, count: option.count });
  };

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <SeoMeta
        title={metaTitle}
        description={metaDescription}
        keywords={metaKeywords}
        canonical={pageUrl}
      />

      <Typography variant="h4" component="h1" gutterBottom>
        {t('search.heading')}
      </Typography>

      {/* Search Box */}
      <Paper 
        component="form" 
        sx={{ p: 2, mb: 3, display: 'flex', flexWrap: { xs: 'wrap', sm: 'nowrap' }, alignItems: 'center', gap: { xs: 1, sm: 0 } }}
        onSubmit={handleSearchSubmit}
      >
        <TextField
          fullWidth
          variant="outlined"
          placeholder={t('search.placeholder')}
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          slotProps={{
            input: {
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
              endAdornment: searchQuery && (
                <InputAdornment position="end">
                  <IconButton 
                    size="small"
                    onClick={() => {
                      setSearchQuery('');
                      updateSearchParams({ query: null });
                    }}
                  >
                    <CloseIcon />
                  </IconButton>
                </InputAdornment>
              )
            }
          }}
        />
        <Button 
          variant="contained" 
          color="primary" 
          type="submit"
          sx={{ ml: { xs: 0, sm: 2 }, width: { xs: '100%', sm: 'auto' } }}
        >
          {t('search.search')}
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          onClick={() => setShowFilters(!showFilters)}
          startIcon={<TuneIcon />}
          sx={{ ml: { xs: 0, sm: 2 }, width: { xs: '100%', sm: 'auto' } }}
        >
          {t('search.filters')}
        </Button>
      </Paper>

      {/* Filters */}
      {showFilters && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h6">{t('search.filtersAndSort')}</Typography>
            <Button 
              variant="text" 
              color="secondary" 
              onClick={handleClearFilters}
            >
              {t('search.clearAll')}
            </Button>
          </Box>
          
          <Grid container spacing={3}>
            {/* Tags - Autocomplete */}
            <Grid size={{ xs: 12, md: 6 }}> 
              <Autocomplete<string | Suggestion, true>
                multiple
                options={tagSuggestions}
                value={selectedTags}
                inputValue={tagInput}
                onInputChange={(_, newInputValue) => {
                  setTagInput(newInputValue);
                }}
                onChange={(_, newValue) => {
                  setSelectedTags(newValue.map(item => typeof item === 'string' ? item : item.name));
                }}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  return suggestionLabel(option);
                }}
                isOptionEqualToValue={(option, value) => {
                  const optionName = typeof option === 'string' ? option : option.name;
                  const valueName = typeof value === 'string' ? value : value.name;
                  return optionName === valueName;
                }}
                renderValue={(value, getItemProps) =>
                  value.map((option, index) => {
                    const tagName = typeof option === 'string' ? option : option.name;
                    return (
                      <Chip
                        label={tagName}
                        {...getItemProps({ index })}
                      />
                    );
                  })
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('search.includeTags')}
                    placeholder={t('search.includeTagsPlaceholder')}
                    slotProps={{
                      ...params.slotProps,

                      input: {
                        ...params.slotProps.input,
                        endAdornment: (
                          <React.Fragment>
                            {loadingTags ? <CircularProgress color="inherit" size={20} /> : null}
                            {params.slotProps.input.endAdornment}
                          </React.Fragment>
                        ),
                      }
                    }}
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props}>
                    {typeof option === 'string' ? 
                      option : 
                      suggestionLabel(option)
                    }
                  </li>
                )}
                filterOptions={(x) => x} // Don't filter options client-side
                noOptionsText={t('search.noTags')}
                loading={loadingTags}
                loadingText={t('search.loading')}
              />
            </Grid>
            
            {/* Excluded Tags - Autocomplete */}
            <Grid size={{ xs: 12, md: 6 }}> 
              <Autocomplete<string | Suggestion, true>
                multiple
                options={tagSuggestions}
                value={excludedTags}
                inputValue={excludeTagInput}
                onInputChange={(_, newInputValue) => {
                  setExcludeTagInput(newInputValue);
                }}
                onChange={(_, newValue) => {
                  setExcludedTags(newValue.map(item => typeof item === 'string' ? item : item.name));
                }}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  return suggestionLabel(option);
                }}
                isOptionEqualToValue={(option, value) => {
                  const optionName = typeof option === 'string' ? option : option.name;
                  const valueName = typeof value === 'string' ? value : value.name;
                  return optionName === valueName;
                }}
                renderValue={(value, getItemProps) =>
                  value.map((option, index) => {
                    const tagName = typeof option === 'string' ? option : option.name;
                    return (
                      <Chip
                        label={tagName}
                        color="error"
                        variant="outlined"
                        {...getItemProps({ index })}
                      />
                    );
                  })
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('search.excludeTags')}
                    placeholder={t('search.excludeTagsPlaceholder')}
                    slotProps={{
                      ...params.slotProps,

                      input: {
                        ...params.slotProps.input,
                        endAdornment: (
                          <React.Fragment>
                            {loadingTags ? <CircularProgress color="inherit" size={20} /> : null}
                            {params.slotProps.input.endAdornment}
                          </React.Fragment>
                        ),
                      }
                    }}
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props}>
                    {typeof option === 'string' ? 
                      option : 
                      suggestionLabel(option)
                    }
                  </li>
                )}
                filterOptions={(x) => x}
                noOptionsText={t('search.noTags')}
                loading={loadingTags}
                loadingText={t('search.loading')}
              />
            </Grid>
            
            {/* Authors - Autocomplete */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Autocomplete<string | Suggestion, true>
                multiple
                options={authorSuggestions}
                value={selectedAuthors}
                inputValue={authorInput}
                onInputChange={(_, newInputValue) => {
                  setAuthorInput(newInputValue);
                }}
                onChange={(_, newValue) => {
                  setSelectedAuthors(newValue.map(item => typeof item === 'string' ? item : item.name));
                }}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  return suggestionLabel(option);
                }}
                isOptionEqualToValue={(option, value) => {
                  const optionName = typeof option === 'string' ? option : option.name;
                  const valueName = typeof value === 'string' ? value : value.name;
                  return optionName === valueName;
                }}
                renderValue={(value, getItemProps) =>
                  value.map((option, index) => {
                    const tagName = typeof option === 'string' ? option : option.name;
                    return (
                      <Chip
                        label={tagName}
                        {...getItemProps({ index })}
                      />
                    );
                  })
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t('search.authors')}
                    placeholder={t('search.authorsPlaceholder')}
                    slotProps={{
                      ...params.slotProps,

                      input: {
                        ...params.slotProps.input,
                        endAdornment: (
                          <React.Fragment>
                            {loadingAuthors ? <CircularProgress color="inherit" size={20} /> : null}
                            {params.slotProps.input.endAdornment}
                          </React.Fragment>
                        ),
                      }
                    }}
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props}>
                    {typeof option === 'string' ? 
                      option : 
                      suggestionLabel(option)
                    }
                  </li>
                )}
                filterOptions={(x) => x} // Don't filter options client-side
                noOptionsText={t('search.noAuthors')}
                loading={loadingAuthors}
                loadingText={t('search.loading')}
              />
            </Grid>
            
            {/* Language Filter */}
            <Grid size={{ xs: 12, md: 6 }}>
              <FormControl fullWidth>
                <InputLabel>{t('search.language')}</InputLabel>
                <Select
                  multiple
                  value={selectedLanguages}
                  onChange={(e) =>
                    setSelectedLanguages(
                      typeof e.target.value === 'string'
                        ? e.target.value.split(',')
                        : (e.target.value as string[])
                    )
                  }
                  label={t('search.language')}
                  renderValue={(selected) => (
                    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5 }}>
                      {selected.map((langCode) => (
                        <Chip
                          key={langCode}
                          size="small"
                          label={languageCodeToName(t, langCode)}
                          avatar={
                            <img
                              src={languageFlagUrl(langCode)}
                              alt={languageCodeToName(t, langCode)}
                              style={{ width: '20px', height: '15px', objectFit: 'cover' }}
                            />
                          }
                        />
                      ))}
                    </Box>
                  )}
                >
                  {filterOptions.languages.map((langCode) => (
                    <MenuItem key={langCode} value={langCode}>
                      <Checkbox checked={selectedLanguages.indexOf(langCode) > -1} />
                      <Box sx={{ display: 'flex', alignItems: 'center' }}>
                        <img 
                          src={languageFlagUrl(langCode)} 
                          alt={languageCodeToName(t, langCode)}
                          style={{ 
                            width: '20px',
                            height: '15px',
                            objectFit: 'cover',
                            borderRadius: '2px',
                            marginRight: '8px',
                          }}
                        />
                        {languageCodeToName(t, langCode)}
                      </Box>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            {/* Minimum Rating */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography component="legend">{t('search.minimumRating')}</Typography>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Rating
                  value={minRating || 0}
                  onChange={(_, newValue) => setMinRating(newValue)}
                  precision={0.5}
                />
                {minRating !== null && (
                  <Button 
                    size="small" 
                    onClick={() => setMinRating(null)}
                    startIcon={<CloseIcon />}
                    sx={{ ml: 1 }}
                  >
                    {t('search.clear')}
                  </Button>
                )}
              </Box>
            </Grid>
            
            {/* Sort Options */}
            <Grid size={{ xs: 12, md: 6 }}>
              <FormControl fullWidth>
                <InputLabel>{t('search.sortBy')}</InputLabel>
                <Select
                  value={sortBy}
                  onChange={(e) => { setSortBy(e.target.value); setSortOrder(defaultSortOrder(e.target.value)); }}
                  label={t('search.sortBy')}
                  startAdornment={
                    <InputAdornment position="start">
                      <SortIcon />
                    </InputAdornment>
                  }
                >
                  <MenuItem value="title">{t('search.sortTitle')}</MenuItem>
                  <MenuItem value="rating">{t('search.sortRating')}</MenuItem>
                  <MenuItem value="date_added">{t('search.sortDateAdded')}</MenuItem>
                  <MenuItem value="popularity">{t('search.sortAllTimeViews')}</MenuItem>
                  <MenuItem value="trending">{t('search.sortTrending')}</MenuItem>
                  <MenuItem value="last_updated">{t('search.sortLastUpdated')}</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            {/* Sort Order */}
            <Grid size={{ xs: 12, md: 6 }}>
              <FormGroup row>
                <FormControlLabel
                  control={
                    <Checkbox 
                      checked={sortOrder === 'desc'}
                      onChange={(e) => setSortOrder(e.target.checked ? 'desc' : 'asc')}
                    />
                  }
                  label={t('search.sortDescending')}
                />
              </FormGroup>
            </Grid>
            
            {/* Adult (R18) content */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography variant="body2" sx={{ mb: 0.5, color: 'text.secondary' }}>
                {t('search.adultContent')}
              </Typography>
              <ToggleButtonGroup
                value={adult}
                exclusive
                size="small"
                onChange={(_, value: AdultFilter | null) => { if (value) setAdult(value); }}
              >
                <ToggleButton value="hide">{t('search.adultHide')}</ToggleButton>
                <ToggleButton value="show">{t('search.adultShow')}</ToggleButton>
                <ToggleButton value="only">{t('search.adultOnly')}</ToggleButton>
              </ToggleButtonGroup>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Active Filters Display */}
      {(selectedTags.length > 0 || excludedTags.length > 0 ||
       selectedAuthors.length > 0 || selectedStatus || selectedLanguages.length > 0 || 
       minRating || sortBy !== 'popularity' || sortOrder !== 'desc' || adult !== defaultAdult) && (
        <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {selectedTags.map(tag => (
            <Chip 
              key={`tag-${tag}`} 
              label={t('search.tagFilter', { tag })}
              color="primary"
              onDelete={() => {
                setSelectedTags(selectedTags.filter(t => t !== tag));
                updateSearchParams({ 
                  tag: selectedTags.filter(t => t !== tag)
                });
              }}
            />
          ))}
          
          {excludedTags.map(tag => (
            <Chip 
              key={`exclude-tag-${tag}`} 
              label={t('search.excludeFilter', { tag })}
              color="error"
              variant="outlined"
              onDelete={() => {
                setExcludedTags(excludedTags.filter(t => t !== tag));
                updateSearchParams({ 
                  exclude_tag: excludedTags.filter(t => t !== tag)
                });
              }}
            />
          ))}
          
          {selectedAuthors.map(author => (
            <Chip 
              key={`author-${author}`} 
              label={t('search.authorFilter', { author })}
              onDelete={() => {
                setSelectedAuthors(selectedAuthors.filter(a => a !== author));
                updateSearchParams({ 
                  author: selectedAuthors.filter(a => a !== author)
                });
              }}
            />
          ))}
          
          {selectedStatus && (
            <Chip 
              label={t('search.statusFilter', { status: selectedStatus })}
              onDelete={() => {
                setSelectedStatus('');
                updateSearchParams({ status: null });
              }}
            />
          )}
          
          {selectedLanguages.map((langCode) => (
            <Chip 
              key={langCode}
              label={
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                  {t('search.languageFilter')}&nbsp;
                  <img 
                    src={languageFlagUrl(langCode)} 
                    alt={languageCodeToName(t, langCode)}
                    style={{ 
                      width: '20px', 
                      height: '15px', 
                      objectFit: 'cover',
                      borderRadius: '2px',
                      marginRight: '4px',
                      marginLeft: '4px',
                    }}
                  />
                  {languageCodeToName(t, langCode)}
                </Box>
              }
              onDelete={() => {
                const next = selectedLanguages.filter((code) => code !== langCode);
                setSelectedLanguages(next);
                updateSearchParams({ language: next });
              }}
            />
          ))}
          
          {minRating !== null && (
            <Chip 
              label={t('search.ratingFilter', { rating: minRating })}
              onDelete={() => {
                setMinRating(null);
                updateSearchParams({ min_rating: null });
              }}
            />
          )}
          
          {(sortBy !== 'popularity' || sortOrder !== 'desc') && (
            <Chip
              label={t('search.sortFilter', { sortBy, sortOrder })}
              onDelete={() => {
                setSortBy('popularity');
                setSortOrder('desc');
                updateSearchParams({
                  sort_by: 'popularity',
                  sort_order: 'desc'
                });
              }}
            />
          )}

          {adult !== defaultAdult && (
            <Chip
              label={t(`search.adult${adult === 'hide' ? 'Hide' : adult === 'show' ? 'Show' : 'Only'}`)}
              onDelete={() => {
                setAdult(defaultAdult);
                updateSearchParams({ adult: defaultAdult });
              }}
            />
          )}
        </Box>
      )}

      {/* Results Count */}
      <Typography variant="subtitle1" sx={{ mb: 2 }}>
        {t('search.foundCount', { count: totalCount })}
      </Typography>
      {hiddenAdult > 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t('search.hiddenAdultCount', { count: hiddenAdult })}{' '}
          <Button
            size="small"
            onClick={() => {
              setAdult('show');
              updateSearchParams({ adult: 'show' });
            }}
          >
            {t('search.hiddenAdultShow')}
          </Button>
        </Typography>
      )}

      {pending ? (
        <SearchResultsSkeleton />
      ) : (
        <>
          {/* Novel Grid */}
          {novels.length > 0 && (
            <Grid container spacing={3}>
              {novels.map((novel) => (
                <Grid key={novel.id} size={{ xs: 6, sm: 4, md: 3, lg: 2 }}>
                  <BaseNovelCard
                    novel={novel}
                    {...getNovelSourceLink(novel)}
                  />
                </Grid>
              ))}
            </Grid>
          )}

          {/* No Results */}
          {novels.length === 0 && (
            <Box sx={{ textAlign: 'center', my: 5 }}>
              <Typography variant="h6">{t('search.noResults')}</Typography>
              <Typography color="textSecondary">
                {t('search.noResultsHint')}
              </Typography>
            </Box>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <Stack spacing={2} sx={{ mt: 4, display: 'flex', alignItems: 'center' }}>
              <Pagination
                count={totalPages}
                page={currentPage}
                onChange={handlePageChange}
                color="primary"
                size="large"
              />
            </Stack>
          )}
        </>
      )}
    </Container>
  );
};

export default SearchPage;
