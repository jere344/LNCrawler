import { Box, ButtonBase, IconButton, TextField, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ClearIcon from '@mui/icons-material/Clear';
import DirectionalIcon from '../DirectionalIcon';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { SETTINGS_PAGES } from './settingsPages';
import { SETTINGS_INDEX, type SettingsIndexEntry } from './settingsIndex';
import { searchSettings, splitAtMatch } from './settingsSearch';

interface SettingsSearchProps {
  query: string;
  onQueryChange: (query: string) => void;
  onChoose: (entry: SettingsIndexEntry) => void;
  // Escape with no query closes the panel
  onClose: () => void;
}

// Search field for every setting, with the matching settings listed under it
const SettingsSearch = ({ query, onQueryChange, onChoose, onClose }: SettingsSearchProps) => {
  const { t } = useTranslation();
  const { ttsEngine } = useReaderSettings();
  const hasQuery = query.trim() !== '';

  // Only the rows the current voice engine shows: pitch for the device voice, volume for HD
  const hits = hasQuery
    ? searchSettings(query, SETTINGS_INDEX.filter((entry) => !entry.engine || entry.engine === ttsEngine).map((entry) => ({
      entry,
      label: t(entry.labelKey),
      keywords: t(entry.keywordsKey),
      page: t(SETTINGS_PAGES[entry.page].titleKey),
    })))
    : [];

  return (
    <Box sx={{ pb: 2 }}>
      <TextField
        type="search"
        fullWidth
        size="small"
        sx={{ '& input::-webkit-search-cancel-button': { display: 'none' } }}
        label={t('readerSettingsPages.searchLabel')}
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        // Escape clears the search first, then closes the panel. The keyboard shortcuts ignore Escape from a field, so this handles it.
        onKeyDown={(event) => {
          if (event.key !== 'Escape') return;
          // The window keyboard listener must not also see this Escape
          event.stopPropagation();
          if (hasQuery) onQueryChange('');
          else onClose();
        }}
        slotProps={{
          input: {
            endAdornment: hasQuery ? (
              <IconButton size="small" aria-label={t('readerSettingsPages.searchClear')} onClick={() => onQueryChange('')}>
                <ClearIcon fontSize="small" />
              </IconButton>
            ) : undefined,
          },
        }}
      />

      {hasQuery && hits.length === 0 && (
        <Typography role="status" color="text.secondary" sx={{ pt: 2 }}>
          {t('readerSettingsPages.searchEmpty', { query: query.trim() })}
        </Typography>
      )}

      {hits.length > 0 && (
        <>
          <Typography role="status" variant="body2" color="text.secondary" sx={{ pt: 2, pb: 0.5 }}>
            {t('readerSettingsPages.searchCount', { count: hits.length })}
          </Typography>
          {hits.map(({ entry, label, page }) => {
            const parts = splitAtMatch(label, query);
            return (
              <ButtonBase
                key={entry.id}
                onClick={() => onChoose(entry)}
                sx={{ display: 'flex', width: '100%', alignItems: 'center', gap: 2, py: 1.5, textAlign: 'start', borderRadius: 1 }}
              >
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography sx={{ fontWeight: 600 }}>
                    {parts ? (
                      <>
                        {parts.before}
                        <Box component="mark" sx={{ bgcolor: 'action.selected', color: 'inherit', borderRadius: 0.5 }}>{parts.match}</Box>
                        {parts.after}
                      </>
                    ) : label}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">{page}</Typography>
                </Box>
                <DirectionalIcon><ChevronRightIcon color="action" /></DirectionalIcon>
              </ButtonBase>
            );
          })}
        </>
      )}
    </Box>
  );
};

export default SettingsSearch;
