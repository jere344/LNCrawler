import { useState } from 'react';
import { Box, ButtonBase, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

interface CommentMessageProps {
  message: string;
  containsSpoiler: boolean;
}

// Comment text; a spoiler stays blurred until it is clicked, or activated with Enter or Space
const CommentMessage = ({ message, containsSpoiler }: CommentMessageProps) => {
  const { t } = useTranslation();
  const [isSpoilerRevealed, setSpoilerRevealed] = useState(false);

  if (!containsSpoiler) {
    return (
      <Typography variant="body1" sx={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>
        {message}
      </Typography>
    );
  }

  return (
    <Box sx={{ mt: 1 }}>
      <ButtonBase
        component="div"
        role="button"
        tabIndex={0}
        disableRipple
        aria-label={isSpoilerRevealed ? undefined : t('comments.spoiler')}
        onClick={() => setSpoilerRevealed(!isSpoilerRevealed)}
        sx={{
          display: 'block',
          width: '100%',
          textAlign: 'inherit',
          typography: 'body1',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          filter: isSpoilerRevealed ? 'none' : 'blur(5px)',
          cursor: 'pointer',
          transition: 'filter 0.2s',
          p: 1,
          '&.Mui-focusVisible': {
            outline: (theme) => `2px solid ${theme.palette.primary.main}`,
            outlineOffset: 2,
          },
        }}
      >
        {message}
      </ButtonBase>
      {!isSpoilerRevealed && (
        <Typography
          variant="caption"
          sx={{
            color: "warning.main",
            display: 'block',
            mt: 0.5,
            fontStyle: 'italic'
          }}>
          {t('comments.spoiler')}
        </Typography>
      )}
    </Box>
  );
};

export default CommentMessage;
