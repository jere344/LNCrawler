import type { ReactNode, Ref } from 'react';
import { Box, IconButton, Typography, type SxProps, type Theme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CloseIcon from '@mui/icons-material/Close';
import DirectionalIcon from '../DirectionalIcon';
import { TOUCH_TARGET } from '../touchTarget';

interface ReaderPanelHeaderProps {
  title: string;
  // Shows the back button at the start of the header when set
  onBack?: () => void;
  backRef?: Ref<HTMLButtonElement>;
  // Extra controls after the title
  extra?: ReactNode;
  // Shows a close button at the end of the header when set
  close?: { label: string; onClick: () => void; ref?: Ref<HTMLButtonElement> };
  // Padding and border of the row, set by the panel that shows the header
  sx?: SxProps<Theme>;
}

// The header of a reader panel: an optional back button, the title, extra controls, and an optional close button
const ReaderPanelHeader = ({ title, onBack, backRef, extra, close, sx }: ReaderPanelHeaderProps) => {
  const { t } = useTranslation();

  return (
    <Box sx={[{ display: 'flex', alignItems: 'center', gap: 1 }, ...(Array.isArray(sx) ? sx : [sx])]}>
      {onBack && (
        <IconButton ref={backRef} onClick={onBack} aria-label={t('readerDisplay.back')}>
          <DirectionalIcon><ArrowBackIcon /></DirectionalIcon>
        </IconButton>
      )}
      <Typography variant="h6" component="h2" noWrap sx={{ flex: 1, minWidth: 0, fontSize: '1.1rem' }}>
        {title}
      </Typography>
      {extra}
      {close && (
        <IconButton ref={close.ref} onClick={close.onClick} aria-label={close.label} sx={TOUCH_TARGET}>
          <CloseIcon />
        </IconButton>
      )}
    </Box>
  );
};

export default ReaderPanelHeader;
