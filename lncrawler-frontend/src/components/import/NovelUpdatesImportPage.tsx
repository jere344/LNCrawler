import React, { useMemo, useRef, useState } from 'react';
import {
  Box,
  Typography,
  Paper,
  Button,
  Alert,
  TextField,
  Autocomplete,
  Avatar,
  Checkbox,
  FormControlLabel,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import BookIcon from '@mui/icons-material/Book';
import { Link as RouterLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { novelService } from '@services/novel.service';
import { importService } from '@services/import.service';
import type { NuImportEntry, NuImportApplyResponse } from '@services/import.service';
import type { Novel } from '@models/novels_types';
import { useAuth } from '@context/AuthContext';
import BreadcrumbNav from '@components/common/BreadcrumbNav';

interface NovelSelectProps {
  value: Novel | null;
  initialOptions: Novel[];
  onChange: (novel: Novel | null) => void;
}

const NovelSelect: React.FC<NovelSelectProps> = ({ value, initialOptions, onChange }) => {
  const { t } = useTranslation();
  const [options, setOptions] = useState<Novel[]>(initialOptions);
  const [searching, setSearching] = useState(false);
  const requestId = useRef(0);

  const search = async (query: string) => {
    if (query.trim().length < 2) {
      requestId.current += 1;
      setOptions([]);
      return;
    }
    const id = ++requestId.current;
    setSearching(true);
    try {
      const data = await novelService.searchNovels({ query, page_size: 20 });
      if (id === requestId.current) setOptions(data.results || []);
    } catch (err) {
      console.error('Error searching novels:', err);
    } finally {
      if (id === requestId.current) setSearching(false);
    }
  };

  const optionsWithValue = useMemo(() => {
    if (!value) return options;
    return options.some((option) => option.id === value.id) ? options : [value, ...options];
  }, [options, value]);

  return (
    <Autocomplete
      size="small"
      options={optionsWithValue}
      value={value}
      getOptionLabel={(option) => option.title}
      isOptionEqualToValue={(a, b) => a.id === b.id}
      loading={searching}
      onChange={(_, novel) => onChange(novel)}
      onInputChange={(_, query) => search(query)}
      renderOption={(props, option) => (
        <Box component="li" {...props} key={option.id} sx={{ gap: 1 }}>
          <Avatar
            src={option.prefered_source?.cover_min_url || undefined}
            sx={{ width: 24, height: 24 }}
          >
            <BookIcon sx={{ fontSize: 16 }} />
          </Avatar>
          {option.title}
        </Box>
      )}
      renderInput={(params) => (
        <TextField
          {...params}
          label={t('importNu.matchLabel')}
          placeholder={t('importNu.searchPlaceholder')}
        />
      )}
    />
  );
};

interface RowState {
  entry: NuImportEntry;
  novel: Novel | null;
  folder: string;
  include: boolean;
}

const NovelUpdatesImportPage: React.FC = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [rows, setRows] = useState<RowState[]>([]);
  const [parseId, setParseId] = useState(0);
  const [parsing, setParsing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<NuImportApplyResponse | null>(null);

  const handleFile = async (file: File) => {
    setError(null);
    setResult(null);
    setParsing(true);
    try {
      const data = await importService.parseNovelupdatesExport(file);
      setRows(
        data.entries.map((entry) => ({
          entry,
          novel: entry.novel,
          folder: entry.folder,
          include: entry.status === 'matched',
        }))
      );
      setParseId((id) => id + 1);
    } catch (err) {
      const message = (err as { response?: { data?: { error?: string } } })?.response?.data?.error;
      setError(message || t('importNu.parseFailed'));
    } finally {
      setParsing(false);
    }
  };

  const updateRow = (index: number, patch: Partial<RowState>) =>
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));

  const selectedCount = rows.filter((row) => row.include && row.novel).length;

  const progressText = (entry: NuImportEntry) => {
    if (entry.chapter > 0) {
      return entry.volume > 0 ? `v${entry.volume}c${entry.chapter}` : `c${entry.chapter}`;
    }
    if (entry.volume > 0) return `v${entry.volume}`;
    return t('importNu.noProgress');
  };

  const handleApply = async () => {
    const payload = rows
      .filter((row) => row.include && row.novel)
      .map((row) => ({
        novel_id: (row.novel as Novel).id,
        folder: row.folder.trim() || undefined,
        ...(row.entry.volume > 0 ? { volume: row.entry.volume } : {}),
        ...(row.entry.chapter > 0 ? { chapter: row.entry.chapter } : {}),
      }));
    if (payload.length === 0) return;
    setApplying(true);
    setError(null);
    try {
      const data = await importService.applyNovelupdatesImport(payload);
      setResult(data);
      setRows([]);
    } catch (err) {
      console.error('Error applying NovelUpdates import:', err);
      setError(t('importNu.applyFailed'));
    } finally {
      setApplying(false);
    }
  };

  if (!isAuthenticated) {
    return (
      <Paper
        elevation={3}
        sx={{
          p: 4,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 2,
          mx: 'auto',
          maxWidth: 'md',
          my: 4,
        }}
      >
        <LibraryBooksIcon sx={{ fontSize: 60, color: 'primary.main', mb: 2 }} />
        <Typography variant="h5" component="h1" gutterBottom>
          {t('importNu.heading')}
        </Typography>
        <Typography variant="body1" align="center" sx={{ color: 'text.secondary' }}>
          {t('library.needLogin')}
        </Typography>
      </Paper>
    );
  }

  return (
    <Box sx={{ px: { xs: 2, sm: 3 } }}>
      <BreadcrumbNav
        items={[{ label: t('importNu.heading'), icon: <UploadFileIcon fontSize="inherit" /> }]}
      />

      <Typography variant="h4" component="h1" gutterBottom>
        {t('importNu.heading')}
      </Typography>

      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="subtitle1" fontWeight="bold">
          {t('importNu.tutorialTitle')}
        </Typography>
        <Typography component="div" variant="body2">
          <ol style={{ margin: '8px 0 0', paddingInlineStart: 20 }}>
            <li>{t('importNu.tutorialStep1')}</li>
            <li>{t('importNu.tutorialStep2')}</li>
            <li>{t('importNu.tutorialStep3')}</li>
          </ol>
        </Typography>
      </Alert>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {result && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {t('importNu.resultSummary', {
            bookmarked: result.bookmarked,
            already: result.already_bookmarked,
            progress: result.progress_set,
          })}
          <Box sx={{ mt: 1 }}>
            <Button component={RouterLink} to="/library" size="small">
              {t('importNu.goToLibrary')}
            </Button>
          </Box>
        </Alert>
      )}

      <input
        ref={fileInputRef}
        type="file"
        accept=".xml,text/xml,application/xml"
        hidden
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) handleFile(file);
          event.target.value = '';
        }}
      />

      {rows.length === 0 ? (
        <Paper sx={{ p: 4, textAlign: 'center' }}>
          <Typography variant="body1" color="text.secondary" sx={{ mb: 2 }}>
            {t('importNu.chooseFileHint')}
          </Typography>
          <Button
            variant="contained"
            startIcon={<UploadFileIcon />}
            onClick={() => fileInputRef.current?.click()}
            disabled={parsing}
          >
            {parsing ? t('importNu.parsing') : t('importNu.chooseFile')}
          </Button>
        </Paper>
      ) : (
        <>
          <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', mb: 2, flexWrap: 'wrap' }}>
            <Typography variant="body2" color="text.secondary" sx={{ flex: 1 }}>
              {t('importNu.parsedCount', { count: rows.length, selected: selectedCount })}
            </Typography>
            <Button onClick={() => fileInputRef.current?.click()} disabled={parsing}>
              {t('importNu.chooseAnother')}
            </Button>
            <Button
              variant="contained"
              onClick={handleApply}
              disabled={applying || parsing || selectedCount === 0}
            >
              {applying ? t('importNu.applying') : t('importNu.apply', { count: selectedCount })}
            </Button>
          </Box>

          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
            {rows.map((row, index) => (
              <Paper key={`${parseId}-${row.entry.index}`} sx={{ p: 2 }}>
                <Box sx={{ display: 'flex', gap: 2, alignItems: 'center', flexWrap: 'wrap' }}>
                  <Box sx={{ flex: '1 1 220px', minWidth: 0 }}>
                    <Typography variant="subtitle1" noWrap title={row.entry.title}>
                      {row.entry.title}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {t('importNu.listLabel', { list: row.entry.list_name })} ·{' '}
                      {progressText(row.entry)}
                    </Typography>
                  </Box>
                  <Box sx={{ flex: '1 1 260px', minWidth: 220 }}>
                    <NovelSelect
                      value={row.novel}
                      initialOptions={
                        row.entry.novel
                          ? [row.entry.novel, ...row.entry.candidates]
                          : row.entry.candidates
                      }
                      onChange={(novel) =>
                        updateRow(index, { novel, include: novel ? true : false })
                      }
                    />
                  </Box>
                  <TextField
                    size="small"
                    label={t('importNu.folderLabel')}
                    value={row.folder}
                    onChange={(event) => updateRow(index, { folder: event.target.value })}
                    sx={{ flex: '1 1 160px', minWidth: 140 }}
                  />
                  <FormControlLabel
                    control={
                      <Checkbox
                        checked={row.include}
                        disabled={!row.novel}
                        onChange={(event) =>
                          updateRow(index, { include: event.target.checked })
                        }
                      />
                    }
                    label={t('importNu.include')}
                  />
                </Box>
              </Paper>
            ))}
          </Box>
        </>
      )}
    </Box>
  );
};

export default NovelUpdatesImportPage;
