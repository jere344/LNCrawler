import { Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

interface PodcastAppHelpDialogProps {
  open: boolean;
  onClose: () => void;
}

// Explains the RSS route: each audiobook page links to a feed that podcast apps can subscribe to.
const PodcastAppHelpDialog = ({ open, onClose }: PodcastAppHelpDialogProps) => {
  const { t } = useTranslation();
  return (
    <Dialog open={open} onClose={onClose} aria-labelledby="podcast-help-title" maxWidth="xs" fullWidth>
      <DialogTitle id="podcast-help-title">{t('audiobooks.podcastHelpTitle')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: 1.5 }}>{t('audiobooks.podcastHelpBody')}</Typography>
        <Typography variant="body2" sx={{ mb: 1.5 }}>{t('audiobooks.podcastHelpCatalog')}</Typography>
        <Typography variant="body2" sx={{ mb: 1.5 }}>{t('audiobooks.podcastHelpApps')}</Typography>
        <Typography variant="body2" color="text.secondary">{t('audiobooks.podcastHelpApple')}</Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.close')}</Button>
      </DialogActions>
    </Dialog>
  );
};

export default PodcastAppHelpDialog;
