import type { ReactNode } from 'react';
import { Box, Button, CircularProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link as RouterLink } from 'react-router-dom';
import type { ChapterStream } from '../hooks/useChapterStream';

interface ChapterStreamEndProps {
  stream: ChapterStream;
  novelSlug?: string;
  sourceSlug?: string;
}

// Below the last section of the infinite list: loading, why the list stopped, or a retry
const ChapterStreamEnd = ({ stream, novelSlug, sourceSlug }: ChapterStreamEndProps) => {
  const { t } = useTranslation();
  const { loading, end, endChapter, retry } = stream;

  let message: string | null = null;
  let action: ReactNode = null;
  if (loading) {
    message = t('reader.infiniteLoading');
  } else if (end === 'last') {
    message = t('reader.infiniteEnd');
  } else if (end === 'gap' || end === 'unavailable') {
    message = t('reader.infiniteUnavailable', { chapter: endChapter });
    action = (
      <Button component={RouterLink} to={`/novels/${novelSlug}/${sourceSlug}/chapter/${endChapter}`}>
        {t('reader.infiniteOpenChapter', { chapter: endChapter })}
      </Button>
    );
  } else if (end === 'dmca') {
    message = t('reader.dmcaUnavailable');
  } else if (end === 'error') {
    message = t('reader.loadFailed');
    action = <Button onClick={() => { void retry(); }}>{t('reader.retry')}</Button>;
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, textAlign: 'center', py: message ? 4 : 0 }}>
      {loading && <CircularProgress size={28} aria-hidden="true" />}
      {/* Always mounted, so screen readers announce the text when it appears */}
      <Typography
        role="status"
        color={end === 'error' ? 'error' : 'text.secondary'}
        sx={loading ? visuallyHidden : undefined}
      >
        {message}
      </Typography>
      {action}
    </Box>
  );
};

// The loading text is for screen readers only; the spinner shows it on screen
const visuallyHidden = {
  position: 'absolute', width: '1px', height: '1px', overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap',
} as const;

export default ChapterStreamEnd;
