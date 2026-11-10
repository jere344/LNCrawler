import React, { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Badge,
  Box,
  Button,
  Chip,
  Drawer,
  IconButton,
  InputAdornment,
  TextField,
  Typography,
  alpha,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import CloseIcon from '@mui/icons-material/Close';
import SearchIcon from '@mui/icons-material/Search';
import TuneIcon from '@mui/icons-material/Tune';
import { editionLabel, languageCodeToName } from '@utils/Misc';
import { novelService } from '../../services/api';
import { NovelDetail, NovelFromSource } from '@models/novels_types';
import SourceRow, { SOURCE_COLUMNS, SourceCover } from './novelSources/SourceRow';
import {
  ALL,
  DEFAULT_SORT,
  DEFAULT_SORT_DIR,
  SORT_KEYS,
  SortDir,
  SortKey,
  defaultLanguage,
  editionKey,
  facetCounts,
  languageKey,
  matchesFilters,
  sortSources,
  sourceChapterCount,
} from './novelSources/sourceFilters';

interface NovelSourcesProps {
  novel: NovelDetail;
  currentSourceSlug?: string;
}

const PAGE_SIZE = { desktop: 6, mobile: 5 };
// Showing a few more is cheaper than a "show more" step for them.
const SHOW_ALL_BELOW = 3;

const NovelSources: React.FC<NovelSourcesProps> = ({ novel, currentSourceSlug }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const mobile = useMediaQuery(theme.breakpoints.down('md'));
  const [sources, setSources] = useState<NovelFromSource[]>(novel.sources);
  // Scores as loaded: the rating sort uses them so a row doesn't jump while its vote is cast.
  const [loadedRatings] = useState<Record<string, number>>(() =>
    Object.fromEntries(novel.sources.map((s) => [s.source_slug, s.vote_score])),
  );
  const [votingInProgress, setVotingInProgress] = useState<Record<string, boolean>>({});
  const [query, setQuery] = useState('');
  const [language, setLanguage] = useState<string | null>(null);
  const [edition, setEdition] = useState(ALL);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>(DEFAULT_SORT);
  const [extra, setExtra] = useState(0);
  const [sheetOpen, setSheetOpen] = useState(false);

  const current = sources.find((s) => s.source_slug === currentSourceSlug);
  const others = useMemo(() => sources.filter((s) => s.source_slug !== currentSourceSlug), [sources, currentSourceSlug]);
  const defaultLang = defaultLanguage(others, current);
  const filters = { query, language: language ?? defaultLang, edition };

  const handleVote = async (sourceSlug: string, voteType: 'up' | 'down') => {
    if (!novel.slug || votingInProgress[sourceSlug]) return;

    setVotingInProgress((prev) => ({ ...prev, [sourceSlug]: true }));
    try {
      const voteResponse = await novelService.voteSource(novel.slug, sourceSlug, voteType);
      setSources((prev) =>
        prev.map((source) =>
          source.source_slug === sourceSlug
            ? {
                ...source,
                upvotes: voteResponse.upvotes,
                downvotes: voteResponse.downvotes,
                vote_score: voteResponse.vote_score,
                user_vote: voteResponse.user_vote,
              }
            : source,
        ),
      );
    } catch (err) {
      console.error('Error voting for source:', err);
    } finally {
      setVotingInProgress((prev) => ({ ...prev, [sourceSlug]: false }));
    }
  };

  // Every change to what is listed starts the list over at its first page.
  const change = (apply: () => void) => {
    apply();
    setExtra(0);
  };
  const resetFilters = () => change(() => { setQuery(''); setLanguage(null); setEdition(ALL); });
  const pickSort = (key: SortKey) =>
    change(() =>
      setSort((prev) =>
        prev.key === key && !mobile
          ? { key, dir: prev.dir === 'asc' ? 'desc' : 'asc' }
          : { key, dir: DEFAULT_SORT_DIR[key] },
      ),
    );

  const filtered = sortSources(others.filter((s) => matchesFilters(s, filters)), sort.key, sort.dir, loadedRatings);
  const pageSize = mobile ? PAGE_SIZE.mobile : PAGE_SIZE.desktop;
  let limit = pageSize + extra;
  if (filtered.length - limit <= SHOW_ALL_BELOW) limit = filtered.length;
  const shown = filtered.slice(0, limit);
  const remaining = filtered.length - shown.length;

  const languageCounts = facetCounts(others, filters, 'language');
  const editionCounts = facetCounts(others, filters, 'edition');
  const languageOptions = [...new Set(others.map(languageKey))]
    .sort((a, b) => (languageCounts.get(b) ?? 0) - (languageCounts.get(a) ?? 0))
    .map((value) => ({
      value,
      label: value ? languageCodeToName(t, value) : t('common.unknown'),
      count: languageCounts.get(value) ?? 0,
    }));
  const editionOptions = [...new Set(others.map(editionKey).filter(Boolean))].map((value) => ({
    value,
    label: editionLabel(others.find((s) => editionKey(s) === value)?.edition, t),
    count: editionCounts.get(value) ?? 0,
  }));
  const filterCount = (filters.language !== defaultLang ? 1 : 0) + (edition !== ALL ? 1 : 0) + (query.trim() ? 1 : 0);
  const sortLabel = (key: SortKey) => t(`novelSources.sort.${key}`);

  const chip = (label: string, count: number | undefined, active: boolean, onClick: () => void) => (
    <Chip
      key={label}
      clickable
      aria-pressed={active}
      color={active ? 'primary' : 'default'}
      variant={active ? 'filled' : 'outlined'}
      label={count === undefined ? label : `${label} ${count}`}
      onClick={onClick}
      sx={{ height: mobile ? 44 : 34, borderRadius: 999, flex: 'none' }}
    />
  );

  const languageChips = languageOptions.length > 1 && (
    <>
      {chip(t('novelSources.all'), others.filter((s) => matchesFilters(s, { ...filters, language: ALL })).length, filters.language === ALL, () => change(() => setLanguage(ALL)))}
      {languageOptions.map((o) => chip(o.label, o.count, filters.language === o.value, () => change(() => setLanguage(o.value))))}
    </>
  );
  const editionChips = editionOptions.length > 1 && (
    <>
      {chip(t('novelSources.allVersions'), others.filter((s) => matchesFilters(s, { ...filters, edition: ALL })).length, edition === ALL, () => change(() => setEdition(ALL)))}
      {editionOptions.map((o) => chip(o.label, o.count, edition === o.value, () => change(() => setEdition(o.value))))}
    </>
  );

  const search = (
    <TextField
      size="small"
      value={query}
      onChange={(e) => change(() => setQuery(e.target.value))}
      placeholder={t('novelSources.searchPlaceholder')}
      type="search"
      slotProps={{
        htmlInput: { 'aria-label': t('novelSources.searchPlaceholder') },
        input: {
          startAdornment: (
            <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment>
          ),
          endAdornment: query && (
            <InputAdornment position="end">
              <IconButton size="small" aria-label={t('novelSources.clearSearch')} onClick={() => change(() => setQuery(''))}>
                <CloseIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
          sx: { height: mobile ? 44 : 40 },
        },
      }}
      sx={{ flex: mobile ? 1 : '0 0 320px', '& input[type="search"]::-webkit-search-cancel-button': { display: 'none' } }}
    />
  );

  const resetButton = filterCount > 0 && (
    <Button size="small" onClick={resetFilters} sx={{ minHeight: mobile ? 44 : undefined }}>
      {t('novelSources.reset')}
    </Button>
  );

  const sortHeader = (key: SortKey, label: string) => (
    <Button
      onClick={() => pickSort(key)}
      color="inherit"
      endIcon={
        sort.key === key ? (sort.dir === 'asc' ? <ArrowUpwardIcon fontSize="inherit" /> : <ArrowDownwardIcon fontSize="inherit" />) : undefined
      }
      sx={{
        justifyContent: 'flex-start',
        fontSize: 13,
        fontWeight: 600,
        textTransform: 'none',
        px: 0,
        minWidth: 0,
        color: sort.key === key ? theme.palette.text.primary : theme.palette.text.secondary,
      }}
    >
      {label}
    </Button>
  );
  const headerLabel = (label: string) => (
    <Typography sx={{ fontSize: 13, fontWeight: 600, color: theme.palette.text.secondary }}>{label}</Typography>
  );

  return (
    <Box>
      {current && (
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: 2,
            px: 2,
            py: 1.25,
            mb: 2,
            borderRadius: 2,
            bgcolor: alpha(theme.palette.primary.main, 0.06),
            border: `1px solid ${alpha(theme.palette.divider, 0.15)}`,
          }}
        >
          <SourceCover source={current} />
          <Box sx={{ flex: '1 1 200px', minWidth: 0 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <Typography noWrap sx={{ fontWeight: 600, fontSize: 15 }}>{current.source_name}</Typography>
              <Chip size="small" color="success" label={t('novelSources.current')} sx={{ flex: 'none' }} />
            </Box>
            <Typography noWrap variant="body2" color="text.secondary" sx={{ fontSize: 12 }}>
              {[current.title, editionLabel(current.edition, t)].filter(Boolean).join(' · ')}
            </Typography>
          </Box>
          <Typography variant="body2" color="text.secondary">
            <Box component="b" sx={{ color: theme.palette.primary.main }}>{sourceChapterCount(current)}</Box>{' '}
            {t('novelSources.chapters')}
          </Typography>
        </Box>
      )}

      {mobile ? (
        <>
          <Box sx={{ display: 'flex', gap: 1, mb: 1 }}>
            {search}
            <Button
              variant="outlined"
              color="inherit"
              onClick={() => setSheetOpen(true)}
              aria-label={t('novelSources.filtersTitle')}
              sx={{ height: 44, minWidth: 44, px: 1.5 }}
            >
              <Badge color="primary" badgeContent={filterCount}><TuneIcon /></Badge>
            </Button>
          </Box>
          {languageChips && (
            <Box role="group" aria-label={t('novelSources.language')} sx={{ display: 'flex', gap: 1, overflowX: 'auto', pb: 1, scrollbarWidth: 'none' }}>
              {languageChips}
            </Box>
          )}
        </>
      ) : (
        <>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
            {search}
            {languageChips && <Box role="group" aria-label={t('novelSources.language')} sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>{languageChips}</Box>}
          </Box>
          {(editionChips || resetButton) && (
            <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mb: 1.5 }}>
              {editionChips && <Box role="group" aria-label={t('novelSources.version')} sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>{editionChips}</Box>}
              {resetButton}
            </Box>
          )}
          <Box
            sx={{
              display: 'grid',
              gridTemplateColumns: SOURCE_COLUMNS,
              columnGap: 2,
              alignItems: 'center',
              px: 1,
              height: 40,
              borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}`,
              bgcolor: alpha(theme.palette.common.black, 0.12),
            }}
          >
            {sortHeader('name', t('novelSources.source'))}
            {headerLabel(t('novelSources.language'))}
            {headerLabel(t('novelSources.version'))}
            {sortHeader('chapters', t('novelSources.chapters'))}
            {sortHeader('updated', t('novelSources.updated'))}
            {sortHeader('rating', t('novelSources.rating'))}
          </Box>
        </>
      )}

      {shown.map((source) => (
        <SourceRow
          key={source.id}
          source={source}
          novelSlug={novel.slug}
          mobile={mobile}
          voting={!!votingInProgress[source.source_slug]}
          onVote={handleVote}
        />
      ))}

      {filtered.length === 0 && (
        <Box sx={{ py: 5, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.5, borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}` }}>
          <Typography sx={{ fontWeight: 600 }}>{t('novelSources.noMatch')}</Typography>
          <Button variant="outlined" onClick={resetFilters}>{t('novelSources.reset')}</Button>
        </Box>
      )}

      {filtered.length > 0 && (
        <Box sx={{ pt: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.5, borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}` }}>
          <Typography variant="body2" color="text.secondary">
            {t('novelSources.showing', { shown: shown.length, total: filtered.length })}
          </Typography>
          {remaining > 0 && (
            <Button
              variant="outlined"
              onClick={() => setExtra((e) => e + pageSize)}
              fullWidth={mobile}
              sx={{ minHeight: 44 }}
            >
              {t('novelSources.showMore', { count: Math.min(pageSize, remaining) })}
            </Button>
          )}
        </Box>
      )}

      <Drawer
        anchor="bottom"
        open={mobile && sheetOpen}
        onClose={() => setSheetOpen(false)}
        slotProps={{ paper: { sx: { borderTopLeftRadius: 12, borderTopRightRadius: 12, maxHeight: '90%', px: 2 } } }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', minHeight: 56 }}>
          <Typography variant="h6" component="h3">{t('novelSources.filtersTitle')}</Typography>
          <IconButton aria-label={t('common.close')} onClick={() => setSheetOpen(false)} sx={{ width: 44, height: 44 }}>
            <CloseIcon />
          </IconButton>
        </Box>
        <Box sx={{ overflowY: 'auto' }}>
          <SheetSection title={t('novelSources.sortBy')}>
            {SORT_KEYS.map((key) => chip(sortLabel(key), undefined, sort.key === key, () => pickSort(key)))}
          </SheetSection>
          {languageChips && <SheetSection title={t('novelSources.language')}>{languageChips}</SheetSection>}
          {editionChips && <SheetSection title={t('novelSources.version')}>{editionChips}</SheetSection>}
        </Box>
        <Box sx={{ display: 'flex', gap: 1.5, py: 2, position: 'sticky', bottom: 0, bgcolor: 'background.paper', borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}` }}>
          <Button variant="outlined" color="inherit" onClick={resetFilters} sx={{ minHeight: 48 }}>{t('novelSources.reset')}</Button>
          <Button variant="contained" fullWidth onClick={() => setSheetOpen(false)} sx={{ minHeight: 48 }}>
            {t('novelSources.showResults', { count: filtered.length })}
          </Button>
        </Box>
      </Drawer>
    </Box>
  );
};

const SheetSection: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => {
  const theme = useTheme();
  return (
    <Box sx={{ py: 1.5, borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}` }}>
      <Typography sx={{ fontSize: 13, fontWeight: 600, color: theme.palette.text.secondary, mb: 1 }}>{title}</Typography>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>{children}</Box>
    </Box>
  );
};

export default NovelSources;
