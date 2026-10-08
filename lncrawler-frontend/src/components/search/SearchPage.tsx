import React, { useEffect, useState, useRef } from 'react';
import { 
  Box, Container, Typography, TextField, Paper, 
  FormControl, InputLabel, Select, MenuItem, Checkbox,
  Chip, Button, FormGroup,
  FormControlLabel, Rating, IconButton, InputAdornment,
  CircularProgress, Pagination, Stack, Autocomplete,
  ToggleButton, ToggleButtonGroup,
  Grid as Grid,
} from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import SearchIcon from '@mui/icons-material/Search';
import TuneIcon from '@mui/icons-material/Tune';
import SortIcon from '@mui/icons-material/Sort';
import CloseIcon from '@mui/icons-material/Close';
import { novelService } from '../../services/api';
import BaseNovelCard from '../common/novelcardtypes/BaseNovelCard';
import { useDebounce } from '@utils/useDebounce';
import { Novel } from '@models/novels_types';
import { languageFlagUrl, availableLanguages, languageCodeToName, getNovelSourceLink } from '@utils/Misc';
import { useTheme } from '@theme/ThemeContext';
import { useLanguage } from '@context/LanguageContext';
import { useAuth } from '@context/AuthContext';
import SeoMeta from '../common/SeoMeta';

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

const ITEMS_PER_PAGE = 24;

const SearchPage: React.FC = () => {
  const { t } = useTranslation();
  const { contentLanguages, languageFilterEnabled } = useLanguage();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();

  // Default the adult filter from the account preference: users who allow
  // adult content (yes/blur) start on 'show', everyone else on 'hide'.
  const defaultAdult: AdultFilter =
    user?.show_r18 === 'yes' || user?.show_r18 === 'blur' ? 'show' : 'hide';
  
  // State for search results
  const [novels, setNovels] = useState<Novel[]>([]);
  const [loading, setLoading] = useState(false);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [currentPage, setCurrentPage] = useState(1);
  
  // State for filter options
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    tags: [],
    authors: [],
    statuses: [],
    languages: availableLanguages,
  });
  
  // State for current filters
  const [searchQuery, setSearchQuery] = useState(searchParams.get('query') || '');
  const [selectedTags, setSelectedTags] = useState<string[]>(searchParams.getAll('tag'));
  const [excludedTags, setExcludedTags] = useState<string[]>(searchParams.getAll('exclude_tag'));
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>(searchParams.getAll('author'));
  const [selectedStatus, setSelectedStatus] = useState(searchParams.get('status') || '');
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>(
    searchParams.getAll('language').length > 0
      ? searchParams.getAll('language')
      : languageFilterEnabled
        ? contentLanguages
        : []
  );
  const [minRating, setMinRating] = useState<number | null>(
    searchParams.get('min_rating') ? Number(searchParams.get('min_rating')) : null
  );
  const [sortBy, setSortBy] = useState(searchParams.get('sort_by') || 'title');
  const [sortOrder, setSortOrder] = useState(searchParams.get('sort_order') || 'asc');
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

  // Pre-check the user's content languages once, on first arrival. After that
  // the URL is authoritative: unchecking everything shows all languages.
  const seededLanguages = useRef(searchParams.getAll('language').length > 0);
  useEffect(() => {
    if (seededLanguages.current) return;
    if (!languageFilterEnabled || contentLanguages.length === 0) return;
    seededLanguages.current = true;
    const params = new URLSearchParams(searchParams);
    contentLanguages.forEach((code) => params.append('language', code));
    setSearchParams(params, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentLanguages, languageFilterEnabled]);
  
  // Tags each search fetch so a slow older request can't overwrite a newer one
  const searchRequestIdRef = useRef(0);

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
  
  // Load search results based on current parameters
  useEffect(() => {
    const requestId = ++searchRequestIdRef.current;
    const fetchNovels = async () => {
      setLoading(true);
      try {
        const page = searchParams.get('page') ? parseInt(searchParams.get('page')!) : 1;

        // The selected languages (from the URL) are authoritative: none
        // selected means no language filter, showing everything.
        const selectedLanguages = searchParams.getAll('language');

        const response = await novelService.searchNovels({
          query: searchParams.get('query') || undefined,
          page,
          page_size: ITEMS_PER_PAGE,
          tag: searchParams.getAll('tag'),
          exclude_tag: searchParams.getAll('exclude_tag'),
          author: searchParams.getAll('author'),
          status: searchParams.get('status') || undefined,
          languages: selectedLanguages.length > 0 ? selectedLanguages : undefined,
          min_rating: searchParams.get('min_rating') ? 
            Number(searchParams.get('min_rating')) : undefined,
          sort_by: (searchParams.get('sort_by') as 'title' | 'rating' | 'date_added' | 'popularity' | 'trending' | 'last_updated') || 'title',
          sort_order: (searchParams.get('sort_order') as 'asc' | 'desc') || 'asc',
          adult: (searchParams.get('adult') as AdultFilter) || undefined,
        });
        
        if (requestId !== searchRequestIdRef.current) return;
        setNovels(response.results);
        setTotalCount(response.count);
        setTotalPages(response.total_pages);
        setCurrentPage(response.current_page);
        
        // Store filter options (mainly for status options)
        setFilterOptions(
          {
            tags: response.tags || [],
            authors: response.authors || [],
            statuses: response.statuses || [],
            languages: response.languages || availableLanguages,
          }
        );
      } catch (error) {
        if (requestId !== searchRequestIdRef.current) return;
        console.error('Error fetching search results:', error);
      } finally {
        if (requestId === searchRequestIdRef.current) {
          setLoading(false);
        }
      }
    };
    
    fetchNovels();
  }, [searchParams]);
  
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
        // Add all values from array
        value.forEach(v => params.append(key, v));
      } else if (value !== '') {
        // Add single value
        params.set(key, value.toString());
      }
    });
    
    setSearchParams(params);
  };
  
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
    setSortBy('title');
    setSortOrder('asc');
    setAdult(defaultAdult);
    
    // Reset URL params to default
    setSearchParams(new URLSearchParams({ page: '1' }));
  };

   // Apply filters
  const applyFilters = () => {
    updateSearchParams({
      query: searchQuery,
      tag: selectedTags,
      exclude_tag: excludedTags,
      author: selectedAuthors,
      status: selectedStatus,
      language: selectedLanguages,
      min_rating: minRating,
      sort_by: sortBy,
      sort_order: sortOrder,
      adult: adult === defaultAdult ? null : adult,
    });
    setShowFilters(false);
  };
  
  const pageUrl = window.location.href;
  const baseTitle = t('search.metaDefaultTitle');
  const queryTitle = searchQuery ? t('search.metaQueryTitle', { query: searchQuery }) : baseTitle;

  const metaTitle = loading ? t('search.metaSearchingTitle') : queryTitle;
  
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
        sx={{ p: 2, mb: 3, display: 'flex', alignItems: 'center' }}
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
          sx={{ ml: 2 }}
        >
          {t('search.search')}
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          onClick={() => setShowFilters(!showFilters)}
          startIcon={<TuneIcon />}
          sx={{ ml: 2 }}
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
                  onChange={(e) => setSortBy(e.target.value)}
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
            
            {/* Apply Filters Button */}
            <Grid size={12}>
              <Button 
                variant="contained" 
                color="primary"
                onClick={applyFilters}
                fullWidth
              >
                {t('search.applyFilters')}
              </Button>
            </Grid>
          </Grid>
        </Paper>
      )}

      {/* Active Filters Display */}
      {(selectedTags.length > 0 || excludedTags.length > 0 ||
       selectedAuthors.length > 0 || selectedStatus || selectedLanguages.length > 0 || 
       minRating || sortBy !== 'title' || sortOrder !== 'asc' || adult !== defaultAdult) && (
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
          
          {(sortBy !== 'title' || sortOrder !== 'asc') && (
            <Chip 
              label={t('search.sortFilter', { sortBy, sortOrder })}
              onDelete={() => {
                setSortBy('title');
                setSortOrder('asc');
                updateSearchParams({ 
                  sort_by: 'title',
                  sort_order: 'asc'
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
        {loading ? t('search.searching') : (
          t('search.foundCount', { count: totalCount })
        )}
      </Typography>

      {/* Loading indicator */}
      {loading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {/* Novel Grid */}
      {!loading && novels.length > 0 && (
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
      {!loading && novels.length === 0 && (
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
    </Container>
  );
};

export default SearchPage;
