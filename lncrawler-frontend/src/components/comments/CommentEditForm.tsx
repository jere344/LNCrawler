import {
  Box,
  Button,
  TextField,
  FormControlLabel,
  Checkbox,
  CircularProgress,
  Alert,
} from '@mui/material';
import SaveIcon from '@mui/icons-material/Save';
import CancelIcon from '@mui/icons-material/Cancel';
import { useTranslation } from 'react-i18next';
import type { CommentEdit } from './useCommentEdit';

interface CommentEditFormProps {
  edit: CommentEdit;
}

// Inline form to edit a comment's message and spoiler flag, driven by useCommentEdit
const CommentEditForm = ({ edit }: CommentEditFormProps) => {
  const { t } = useTranslation();

  return (
    <Box sx={{ mt: 2 }}>
      {edit.error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => edit.setError(null)}>
          {edit.error}
        </Alert>
      )}

      <TextField
        fullWidth
        label={t('comments.editPlaceholder')}
        multiline
        rows={4}
        value={edit.message}
        onChange={(e) => edit.setMessage(e.target.value)}
        disabled={edit.isSubmitting}
      />

      <FormControlLabel
        control={
          <Checkbox
            checked={edit.containsSpoiler}
            onChange={(e) => edit.setContainsSpoiler(e.target.checked)}
            color="primary"
          />
        }
        label={t('comments.containsSpoilers')}
        sx={{ mt: 1 }}
      />

      <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
        <Button
          variant="contained"
          color="primary"
          startIcon={edit.isSubmitting ? <CircularProgress size={20} color="inherit" /> : <SaveIcon />}
          onClick={() => edit.save()}
          disabled={edit.isSubmitting}
        >
          {t('common.save')}
        </Button>
        <Button
          variant="outlined"
          startIcon={<CancelIcon />}
          onClick={() => edit.cancel()}
          disabled={edit.isSubmitting}
        >
          {t('common.cancel')}
        </Button>
      </Box>
    </Box>
  );
};

export default CommentEditForm;
