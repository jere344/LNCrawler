import { useState } from 'react';
import { Box, Button, DialogContentText, Dialog, DialogActions, DialogContent, DialogTitle, Stack, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import DownloadIcon from '@mui/icons-material/Download';
import UploadIcon from '@mui/icons-material/Upload';
import { useNotification } from '@context/NotificationContext';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { replaceReaderSettings, resetReaderSettings } from '../../readerSettingsStore';
import { exportReaderSettings, parseReaderSettingsFile, pickJsonFile } from '../../readerSettingsBackup';
import ReaderSyncSection from '../../sync/ReaderSyncSection';

const BackupPage = () => {
  const { t } = useTranslation();
  const { notify } = useNotification();
  const settings = useReaderSettings();
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);

  const resetDefaults = () => {
    resetReaderSettings();
    setResetConfirmOpen(false);
  };

  // Import settings from JSON file
  const importSettings = async () => {
    try {
      const text = await pickJsonFile();
      if (text === null) return;
      replaceReaderSettings(parseReaderSettingsFile(text));
    } catch (error) {
      console.error('Failed to import settings:', error);
      notify({ message: t('readerSettings.importFailed'), severity: 'error' });
    }
  };

  return (
    <Box>
      <ReaderSyncSection />
      <Typography color="text.secondary" sx={{ mb: 2 }}>{t('readerSettingsPages.backupNote')}</Typography>
      <Stack spacing={1}>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" startIcon={<UploadIcon />} onClick={importSettings} sx={{ flex: 1 }} data-setting-id="importSettings">
            {t('readerSettings.import')}
          </Button>
          <Button variant="outlined" startIcon={<DownloadIcon />} onClick={() => exportReaderSettings(settings)} sx={{ flex: 1 }} data-setting-id="exportSettings">
            {t('readerSettings.export')}
          </Button>
        </Stack>
        <Button variant="contained" color="secondary" fullWidth onClick={() => setResetConfirmOpen(true)} data-setting-id="resetDefaults">
          {t('readerSettings.resetDefaults')}
        </Button>
      </Stack>

      <Dialog
        open={resetConfirmOpen}
        onClose={() => setResetConfirmOpen(false)}
        aria-labelledby="reset-dialog-title"
        aria-describedby="reset-dialog-description"
      >
        <DialogTitle id="reset-dialog-title">
          {t('readerSettings.resetTitle')}
        </DialogTitle>
        <DialogContent>
          <DialogContentText id="reset-dialog-description">
            {t('readerSettings.resetBody')}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setResetConfirmOpen(false)} color="primary">
            {t('common.cancel')}
          </Button>
          <Button onClick={resetDefaults} color="secondary" variant="contained">
            {t('readerSettings.reset')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default BackupPage;
