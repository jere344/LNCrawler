import { Button, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { chooseDeviceReaderSettings, chooseSavedReaderSettings } from './readerSettingsSync';
import { useReaderSyncStatus } from './useReaderSettingsSync';

// Asked once on a device that has its own settings while the account already has saved ones.
// Closing it keeps the saved settings, so nothing on the server is replaced without a clear choice.
const ReaderSyncChoiceDialog = () => {
  const { t, i18n } = useTranslation();
  const { status, slot, remoteUpdatedAt } = useReaderSyncStatus();
  if (status !== 'needs-choice') return null;

  const type = t(slot === 'mobile' ? 'readerSettings.syncTypeMobile' : 'readerSettings.syncTypeDesktop');
  const date = remoteUpdatedAt ? new Date(remoteUpdatedAt).toLocaleDateString(i18n.resolvedLanguage) : '';

  return (
    <Dialog open onClose={chooseSavedReaderSettings} aria-labelledby="reader-sync-choice-title">
      <DialogTitle id="reader-sync-choice-title">{t('readerSettings.syncChoiceTitle')}</DialogTitle>
      <DialogContent>
        <DialogContentText>{t('readerSettings.syncChoiceBody', { type, date })}</DialogContentText>
      </DialogContent>
      <DialogActions>
        <Button onClick={chooseDeviceReaderSettings}>{t('readerSettings.syncChoiceDevice')}</Button>
        <Button onClick={chooseSavedReaderSettings} variant="contained">
          {t('readerSettings.syncChoiceSaved')}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ReaderSyncChoiceDialog;
