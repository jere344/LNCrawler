import React, { useEffect, useState, useCallback } from 'react';
import { 
  Box, Container, Typography, TextField, Paper, 
  FormControl, InputLabel, Select, MenuItem, Checkbox,
  Chip, Button, FormGroup,
  FormControlLabel, Rating, IconButton, InputAdornment,
  CircularProgress, Pagination, Stack, Autocomplete,
  Grid2 as Grid,
} from '@mui/material';
import { useSearchParams } from 'react-router-dom';
import SearchIcon from '@mui/icons-material/Search';
import TuneIcon from '@mui/icons-material/Tune';
import SortIcon from '@mui/icons-material/Sort';
import CloseIcon from '@mui/icons-material/Close';
import { novelService } from '../../services/api';
import BaseNovelCard from '../common/novelcardtypes/BaseNovelCard';
import { debounce } from 'lodash';
import { Novel } from '@models/novels_types';
import { languageCodeToFlag, availableLanguages, languageCodeToName } from '@utils/Misc';
import { useTheme } from '@theme/ThemeContext';


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
}

const ITEMS_PER_PAGE = 24;
const DEBOUNCE_TIME = 300; // milliseconds
const DEFAULT_OG_IMAGE = '/og-image.jpg';

const SearchPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  
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
  const [selectedAuthors, setSelectedAuthors] = useState<string[]>(searchParams.getAll('author'));
  const [selectedStatus, setSelectedStatus] = useState(searchParams.get('status') || '');
  const [selectedLanguage, setSelectedLanguage] = useState(searchParams.get('language') || '');
  const [minRating, setMinRating] = useState<number | null>(
    searchParams.get('min_rating') ? Number(searchParams.get('min_rating')) : null
  );
  const [sortBy, setSortBy] = useState(searchParams.get('sort_by') || 'title');
  const [sortOrder, setSortOrder] = useState(searchParams.get('sort_order') || 'desc');
  
  // State for autocomplete options
  const [tagSuggestions, setTagSuggestions] = useState<Suggestion[]>([]);
  const [authorSuggestions, setAuthorSuggestions] = useState<Suggestion[]>([]);
  
  // State for autocomplete input values
  const [tagInput, setTagInput] = useState('');
  const [authorInput, setAuthorInput] = useState('');
  
  // State for loading suggestions
  const [loadingTags, setLoadingTags] = useState(false);
  const [loadingAuthors, setLoadingAuthors] = useState(false);
  
  // UI state
  const [showFilters, setShowFilters] = useState(false);
  
  // Create debounced functions for fetching suggestions
  const fetchTagSuggestions = useCallback(
    debounce(async (query: string) => {
      if (query.length < 1) {
        setTagSuggestions([]);
        setLoadingTags(false);
        return;
      }
      
      setLoadingTags(true);
      try {
        const response = await novelService.getAutocompleteSuggestions('tag', query);
        setTagSuggestions(response);
      } catch (error) {
        console.error('Error fetching tag suggestions:', error);
        setTagSuggestions([]);
      } finally {
        setLoadingTags(false);
      }
    }, DEBOUNCE_TIME),
    []
  );
  
  const fetchAuthorSuggestions = useCallback(
    debounce(async (query: string) => {
      if (query.length < 1) {
        setAuthorSuggestions([]);
        setLoadingAuthors(false);
        return;
      }
      
      setLoadingAuthors(true);
      try {
        const response = await novelService.getAutocompleteSuggestions('author', query);
        setAuthorSuggestions(response);
      } catch (error) {
        console.error('Error fetching author suggestions:', error);
        setAuthorSuggestions([]);
      } finally {
        setLoadingAuthors(false);
      }
    }, DEBOUNCE_TIME),
    []
  );
  
  // Load search results based on current parameters
  useEffect(() => {
    const fetchNovels = async () => {
      setLoading(true);
      try {
        const page = searchParams.get('page') ? parseInt(searchParams.get('page')!) : 1;
        
        const response = await novelService.searchNovels({
          query: searchParams.get('query') || undefined,
          page,
          page_size: ITEMS_PER_PAGE,
          tag: searchParams.getAll('tag'),
          author: searchParams.getAll('author'),
          status: searchParams.get('status') || undefined,
          language: searchParams.get('language') || undefined,
          min_rating: searchParams.get('min_rating') ? 
            Number(searchParams.get('min_rating')) : undefined,
          sort_by: (searchParams.get('sort_by') as any) || 'title',
          sort_order: (searchParams.get('sort_order') as 'asc' | 'desc') || 'desc',
        });
        
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
        console.error('Error fetching search results:', error);
      } finally {
        setLoading(false);
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
    setSelectedAuthors([]);
    setSelectedStatus('');
    setSelectedLanguage('');
    setMinRating(null);
    setSortBy('title');
    setSortOrder('desc');
    
    // Reset URL params to default
    setSearchParams(new URLSearchParams({ page: '1' }));
  };

   // Apply filters
  const applyFilters = () => {
    updateSearchParams({
      query: searchQuery,
      tag: selectedTags,
      author: selectedAuthors,
      status: selectedStatus,
      language: selectedLanguage,
      min_rating: minRating,
      sort_by: sortBy,
      sort_order: sortOrder,
    });
    setShowFilters(false);
  };
  
  const pageUrl = window.location.href;
  const siteName = "LNCrawler";
  const baseTitle = `Search Light Novels | ${siteName}`;
  const queryTitle = searchQuery ? `Search results for "${searchQuery}" | ${siteName}` : baseTitle;

  const metaTitle = loading ? `Searching... | ${siteName}` : queryTitle;
  
  let description = `Search and discover a vast collection of Asian light novels on ${siteName}. Filter by tags, authors, language, and more.`;
  if (searchQuery) {
    description = `Find light novels matching "${searchQuery}". ${totalCount > 0 ? `Found ${totalCount} results.` : ''} Explore on ${siteName}.`;
  }
  const metaDescription = description.substring(0, 160);

  const keywordsList = ["search light novels", "find web novels", "LNCrawler search", "novel discovery"];
  if (searchQuery) keywordsList.push(searchQuery);
  selectedTags.forEach(tag => keywordsList.push(tag));
  selectedAuthors.forEach(author => keywordsList.push(author));
  if (selectedLanguage) keywordsList.push(languageCodeToName(selectedLanguage));
  const metaKeywords = keywordsList.join(', ');

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <title>{metaTitle}</title>
      <meta name="description" content={metaDescription} />
      <meta name="keywords" content={metaKeywords} />
      <link rel="canonical" href={pageUrl} />

      <meta property="og:title" content={metaTitle} />
      <meta property="og:description" content={metaDescription} />
      <meta property="og:type" content="website" />
      <meta property="og:url" content={pageUrl} />
      <meta property="og:site_name" content={siteName} />
      <meta property="og:image" content={DEFAULT_OG_IMAGE} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={metaTitle} />
      <meta name="twitter:description" content={metaDescription} />
      <meta name="twitter:image" content={DEFAULT_OG_IMAGE} />

      <Typography variant="h4" component="h1" gutterBottom>
        Search Novels
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
          placeholder="Search by title, author, or keywords..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          InputProps={{
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
          }}
        />
        <Button 
          variant="contained" 
          color="primary" 
          type="submit"
          sx={{ ml: 2 }}
        >
          Search
        </Button>
        <Button
          variant="outlined"
          color="secondary"
          onClick={() => setShowFilters(!showFilters)}
          startIcon={<TuneIcon />}
          sx={{ ml: 2 }}
        >
          Filters
        </Button>
      </Paper>
      
      {/* Filters */}
      {showFilters && (
        <Paper sx={{ p: 3, mb: 3 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 2 }}>
            <Typography variant="h6">Filters & Sort</Typography>
            <Button 
              variant="text" 
              color="secondary" 
              onClick={handleClearFilters}
            >
              Clear All
            </Button>
          </Box>
          
          <Grid container spacing={3}>
            {/* Tags - Autocomplete */}
            <Grid size={{ xs: 12, md: 6 }}> 
              <Autocomplete
                multiple
                options={tagSuggestions}
                value={selectedTags}
                inputValue={tagInput}
                onInputChange={(_, newInputValue) => {
                  setTagInput(newInputValue);
                  fetchTagSuggestions(newInputValue);
                }}
                onChange={(_, newValue) => {
                  setSelectedTags(newValue.map(item => typeof item === 'string' ? item : item.name));
                }}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  return `${option.name} (${option.count})`;
                }}
                isOptionEqualToValue={(option, value) => {
                  const optionName = typeof option === 'string' ? option : option.name;
                  const valueName = typeof value === 'string' ? value : value.name;
                  return optionName === valueName;
                }}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const tagName = typeof option === 'string' ? option : option.name;
                    return (
                      <Chip
                        label={tagName}
                        {...getTagProps({ index })}
                      />
                    );
                  })
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Tags"
                    placeholder="Type to search tags..."
                    InputProps={{
                      ...params.InputProps,
                      endAdornment: (
                        <React.Fragment>
                          {loadingTags ? <CircularProgress color="inherit" size={20} /> : null}
                          {params.InputProps.endAdornment}
                        </React.Fragment>
                      ),
                    }}
                    helperText="Type at least 3 characters to search"
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props}>
                    {typeof option === 'string' ? 
                      option : 
                      `${option.name} (${option.count})`
                    }
                  </li>
                )}
                filterOptions={(x) => x} // Don't filter options client-side
                noOptionsText="No tags found"
                loading={loadingTags}
                loadingText="Loading..."
              />
            </Grid>
            
            {/* Authors - Autocomplete */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Autocomplete
                multiple
                options={authorSuggestions}
                value={selectedAuthors}
                inputValue={authorInput}
                onInputChange={(_, newInputValue) => {
                  setAuthorInput(newInputValue);
                  fetchAuthorSuggestions(newInputValue);
                }}
                onChange={(_, newValue) => {
                  setSelectedAuthors(newValue.map(item => typeof item === 'string' ? item : item.name));
                }}
                getOptionLabel={(option) => {
                  if (typeof option === 'string') {
                    return option;
                  }
                  return `${option.name} (${option.count})`;
                }}
                isOptionEqualToValue={(option, value) => {
                  const optionName = typeof option === 'string' ? option : option.name;
                  const valueName = typeof value === 'string' ? value : value.name;
                  return optionName === valueName;
                }}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const tagName = typeof option === 'string' ? option : option.name;
                    return (
                      <Chip
                        label={tagName}
                        {...getTagProps({ index })}
                      />
                    );
                  })
                }
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Authors"
                    placeholder="Type to search authors..."
                    InputProps={{
                      ...params.InputProps,
                      endAdornment: (
                        <React.Fragment>
                          {loadingAuthors ? <CircularProgress color="inherit" size={20} /> : null}
                          {params.InputProps.endAdornment}
                        </React.Fragment>
                      ),
                    }}
                    helperText="Type at least 3 characters to search"
                  />
                )}
                renderOption={(props, option) => (
                  <li {...props}>
                    {typeof option === 'string' ? 
                      option : 
                      `${option.name} (${option.count})`
                    }
                  </li>
                )}
                filterOptions={(x) => x} // Don't filter options client-side
                noOptionsText="No authors found"
                loading={loadingAuthors}
                loadingText="Loading..."
              />
            </Grid>
            
            {/* Language Filter */}
            <Grid size={{ xs: 12, md: 6 }}>
              <FormControl fullWidth>
                <InputLabel>Language</InputLabel>
                <Select
                  value={selectedLanguage}
                  onChange={(e) => setSelectedLanguage(e.target.value)}
                  label="Language"
                >
                  <MenuItem value="">
                    <em>Any</em>
                  </MenuItem>
                  {filterOptions.languages.map((langCode) => (
                    <MenuItem key={langCode} value={langCode}>
                      {languageCodeToFlag(langCode)} {languageCodeToName(langCode)}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            {/* Minimum Rating */}
            <Grid size={{ xs: 12, md: 6 }}>
              <Typography component="legend">Minimum Rating</Typography>
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
                    Clear
                  </Button>
                )}
              </Box>
            </Grid>
            
            {/* Sort Options */}
            <Grid size={{ xs: 12, md: 6 }}>
              <FormControl fullWidth>
                <InputLabel>Sort By</InputLabel>
                <Select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  label="Sort By"
                  startAdornment={
                    <InputAdornment position="start">
                      <SortIcon />
                    </InputAdornment>
                  }
                >
                  <MenuItem value="title">Title</MenuItem>
                  <MenuItem value="rating">Rating</MenuItem>
                  <MenuItem value="date_added">Date Added</MenuItem>
                  <MenuItem value="popularity">All-time Views</MenuItem>
                  <MenuItem value="trending">Trending (Weekly Views)</MenuItem>
                  <MenuItem value="last_updated">Last Updated</MenuItem>
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
                  label="Sort Descending"
                />
              </FormGroup>
            </Grid>
            
            {/* Apply Filters Button */}
            <Grid size={12}>
              <Button 
                variant="contained" 
                color="primary"
                onClick={applyFilters}
                fullWidth
              >
                Apply Filters
              </Button>
            </Grid>
          </Grid>
        </Paper>
      )}
      
      {/* Active Filters Display */}
      {(selectedTags.length > 0 || 
       selectedAuthors.length > 0 || selectedStatus || selectedLanguage || 
       minRating || sortBy !== 'title' || sortOrder !== 'asc') && (
        <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1 }}>
          {selectedTags.map(tag => (
            <Chip 
              key={`tag-${tag}`} 
              label={`Tag: ${tag}`}
              onDelete={() => {
                setSelectedTags(selectedTags.filter(t => t !== tag));
                updateSearchParams({ 
                  tag: selectedTags.filter(t => t !== tag)
                });
              }}
            />
          ))}
          
          {selectedAuthors.map(author => (
            <Chip 
              key={`author-${author}`} 
              label={`Author: ${author}`}
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
              label={`Status: ${selectedStatus}`}
              onDelete={() => {
                setSelectedStatus('');
                updateSearchParams({ status: null });
              }}
            />
          )}
          
          {selectedLanguage && (
            <Chip 
              label={`Language: ${languageCodeToFlag(selectedLanguage)} ${languageCodeToName(selectedLanguage)}`}
              onDelete={() => {
                setSelectedLanguage('');
                updateSearchParams({ language: null });
              }}
            />
          )}
          
          {minRating !== null && (
            <Chip 
              label={`Min Rating: ${minRating}`}
              onDelete={() => {
                setMinRating(null);
                updateSearchParams({ min_rating: null });
              }}
            />
          )}
          
          {(sortBy !== 'title' || sortOrder !== 'asc') && (
            <Chip 
              label={`Sort: ${sortBy} (${sortOrder})`}
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
        </Box>
      )}
      
      {/* Results Count */}
      <Typography variant="subtitle1" sx={{ mb: 2 }}>
        {loading ? 'Searching...' : (
          totalCount > 0 ? 
            `Found ${totalCount} novel${totalCount !== 1 ? 's' : ''}` : 
            'No novels found'
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
                to={`/novels/${novel.slug}`}
              />
            </Grid>
          ))}
        </Grid>
      )}
      
      {/* No Results */}
      {!loading && novels.length === 0 && (
        <Box sx={{ textAlign: 'center', my: 5 }}>
          <Typography variant="h6">No novels found matching your criteria</Typography>
          <Typography color="textSecondary">
            Try adjusting your filters or search terms
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
