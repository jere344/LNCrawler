import React from 'react';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, FormControlLabel, Switch } from '@mui/material';
import { useTranslation } from 'react-i18next';

interface ReadingListFormDialogProps {
  open: boolean;
  heading: string;
  submitLabel: string;
  idPrefix?: string;
  title: string;
  description: string;
  isPublic: boolean;
  showVisibility?: boolean;
  onTitleChange: (value: string) => void;
  onDescriptionChange: (value: string) => void;
  onIsPublicChange: (value: boolean) => void;
  onSubmit: () => void;
  onClose: () => void;
}

// Create and edit form for a reading list. The parent owns the values.
const ReadingListFormDialog: React.FC<ReadingListFormDialogProps> = ({
  open,
  heading,
  submitLabel,
  idPrefix = '',
  title,
  description,
  isPublic,
  showVisibility = true,
  onTitleChange,
  onDescriptionChange,
  onIsPublicChange,
  onSubmit,
  onClose,
}) => {
  const { t } = useTranslation();

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
    >
      <DialogTitle>{heading}</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          id={`${idPrefix}title`}
          label={t('readingLists.listTitle')}
          type="text"
          fullWidth
          variant="outlined"
          value={title}
          onChange={(e) => onTitleChange(e.target.value)}
          required
          sx={{ mb: 2 }}
        />
        <TextField
          margin="dense"
          id={`${idPrefix}description`}
          label={t('readingLists.descriptionOptional')}
          type="text"
          fullWidth
          variant="outlined"
          multiline
          rows={4}
          value={description}
          onChange={(e) => onDescriptionChange(e.target.value)}
        />
        {showVisibility && (
          <FormControlLabel
            sx={{ mt: 1 }}
            control={
              <Switch
                checked={isPublic}
                onChange={(e) => onIsPublicChange(e.target.checked)}
              />
            }
            label={isPublic ? t('readingLists.public') : t('readingLists.private')}
          />
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          onClick={onSubmit}
          variant="contained"
          disabled={!title.trim()}
        >
          {submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default ReadingListFormDialog;
