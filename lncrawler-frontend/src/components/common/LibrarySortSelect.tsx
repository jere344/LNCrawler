import React from 'react';
import { FormControl, InputLabel, Select, MenuItem } from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { LibrarySort } from '@services/user.service';

interface LibrarySortSelectProps {
  value: LibrarySort;
  onChange: (value: LibrarySort) => void;
  showRating?: boolean;
}

// Sort dropdown shared by the own and the public library. Rating is only offered when ratings are shown.
const LibrarySortSelect: React.FC<LibrarySortSelectProps> = ({ value, onChange, showRating = true }) => {
  const { t } = useTranslation();

  return (
    <FormControl size="small" sx={{ minWidth: 160 }}>
      <InputLabel>{t('library.sortBy')}</InputLabel>
      <Select label={t('library.sortBy')} value={value} onChange={(e) => onChange(e.target.value as LibrarySort)}>
        <MenuItem value="custom">{t('library.sort.custom')}</MenuItem>
        <MenuItem value="title">{t('library.sort.title')}</MenuItem>
        <MenuItem value="date_added">{t('library.sort.date_added')}</MenuItem>
        {showRating && <MenuItem value="rating">{t('library.sort.rating')}</MenuItem>}
      </Select>
    </FormControl>
  );
};

export default LibrarySortSelect;
