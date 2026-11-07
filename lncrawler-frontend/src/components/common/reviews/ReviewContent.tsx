import React, { useMemo } from 'react';
import { Box } from '@mui/material';
import { Theme, useTheme } from '@mui/material/styles';
import { renderReviewMarkdown } from './renderReviewMarkdown';

interface ReviewContentProps {
  content: string;
  uniqueKey?: string;
}

// Read-only review typography (ported from the MDXEditor contenteditable styles).
const createReviewContentStyles = (theme: Theme) => ({
  fontFamily: theme.typography.fontFamily,
  color: theme.palette.text.primary,
  fontSize: theme.typography.body2.fontSize,
  lineHeight: theme.typography.body2.lineHeight,
  overflowWrap: 'anywhere',
  '& pre': { overflowX: 'auto' },
  '& p': {
    margin: `${theme.spacing(1)} 0`,
    color: theme.palette.text.primary,
  },
  '& h1': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h4.fontSize,
    fontWeight: theme.typography.h4.fontWeight,
    color: theme.palette.text.primary,
  },
  '& h2': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h5.fontSize,
    fontWeight: theme.typography.h5.fontWeight,
    color: theme.palette.text.primary,
  },
  '& h3': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h6.fontSize,
    fontWeight: theme.typography.h6.fontWeight,
    color: theme.palette.text.primary,
  },
  '& h4, & h5, & h6': {
    margin: `${theme.spacing(1.5)} 0 ${theme.spacing(0.5)} 0`,
    fontSize: theme.typography.subtitle1.fontSize,
    fontWeight: theme.typography.subtitle1.fontWeight,
    color: theme.palette.text.primary,
  },
  '& blockquote': {
    margin: `${theme.spacing(2)} 0`,
    padding: `${theme.spacing(1)} ${theme.spacing(2)}`,
    borderLeft: `4px solid ${theme.palette.primary.main}`,
    backgroundColor: theme.palette.action.hover,
    fontStyle: 'italic',
    color: theme.palette.text.secondary,
    borderRadius: `0 ${theme.shape.borderRadius}px ${theme.shape.borderRadius}px 0`,
  },
  '& ul, & ol': {
    margin: `${theme.spacing(1)} 0`,
    paddingLeft: theme.spacing(3),
    color: theme.palette.text.primary,
  },
  '& li': {
    marginBottom: theme.spacing(0.5),
    color: theme.palette.text.primary,
  },
  '& strong': {
    fontWeight: theme.typography.fontWeightBold,
  },
  '& em': {
    fontStyle: 'italic',
  },
  '& u': {
    textDecoration: 'underline',
  },
  '& hr': {
    border: 'none',
    borderTop: `1px solid ${theme.palette.divider}`,
    margin: `${theme.spacing(3)} 0`,
  },
  '& > p:first-of-type': {
    marginTop: 0,
  },
  '& > *:last-child': {
    marginBottom: 0,
  },
});

const ReviewContent: React.FC<ReviewContentProps> = ({ content }) => {
  const theme = useTheme();
  const html = useMemo(() => renderReviewMarkdown(content), [content]);

  return (
    <Box
      sx={{ mt: 1, ...createReviewContentStyles(theme) }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
};

export default ReviewContent;
