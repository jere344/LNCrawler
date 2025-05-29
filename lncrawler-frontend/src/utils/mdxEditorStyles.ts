import { Theme } from '@mui/material/styles';

export const createMDXEditorStyles = (theme: Theme, isReadOnly = false) => ({
  '.mdxeditor': {
    fontFamily: theme.typography.fontFamily,
    backgroundColor: isReadOnly ? 'transparent' : theme.palette.background.paper,
    color: theme.palette.text.primary,
    border: isReadOnly ? 'none' : undefined,
    minHeight: isReadOnly ? undefined : '300px',
  },
  '.mdxeditor-toolbar': {
    display: isReadOnly ? 'none' : 'block',
    backgroundColor: theme.palette.background.default,
    borderBottom: `1px solid ${theme.palette.divider}`,
    padding: theme.spacing(1),
  },
  '.mdxeditor-toolbar svg, .mdxeditor-toolbar path': {
    fill: theme.palette.text.secondary,
  },
  '.mdxeditor-toolbar button': {
    borderRadius: theme.shape.borderRadius,
    color: theme.palette.text.secondary,
    backgroundColor: theme.palette.background.paper,
    padding: theme.spacing(0.5),
    transition: theme.transitions.create(['background-color', 'box-shadow']),
    '&:hover': {
      backgroundColor: theme.palette.action.hover,
    },
    '&:focus': {
      outline: `2px solid ${theme.palette.primary.main}`,
      outlineOffset: '2px',
    },
    '&[data-state="on"]': {
      backgroundColor: theme.palette.primary.main,
      color: theme.palette.primary.contrastText,
      '& svg, & path': {
        fill: theme.palette.primary.contrastText,
      },
    },
    '&[data-disabled]': {
      opacity: 0.38,
      cursor: 'not-allowed',
    },
  },
  '.mdxeditor-root-contenteditable': {
    padding: isReadOnly ? 0 : theme.spacing(2),
    minHeight: isReadOnly ? undefined : '200px',
    fontSize: isReadOnly ? theme.typography.body2.fontSize : theme.typography.body1.fontSize,
    lineHeight: isReadOnly ? theme.typography.body2.lineHeight : theme.typography.body1.lineHeight,
    color: theme.palette.text.primary,
    cursor: isReadOnly ? 'default' : undefined,
  },
  '.mdxeditor-root-contenteditable p': {
    margin: `${theme.spacing(1)} 0`,
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable h1': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h4.fontSize,
    fontWeight: theme.typography.h4.fontWeight,
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable h2': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h5.fontSize,
    fontWeight: theme.typography.h5.fontWeight,
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable h3': {
    margin: `${theme.spacing(2)} 0 ${theme.spacing(1)} 0`,
    fontSize: theme.typography.h6.fontSize,
    fontWeight: theme.typography.h6.fontWeight,
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable h4, .mdxeditor-root-contenteditable h5, .mdxeditor-root-contenteditable h6': {
    margin: `${theme.spacing(1.5)} 0 ${theme.spacing(0.5)} 0`,
    fontSize: theme.typography.subtitle1.fontSize,
    fontWeight: theme.typography.subtitle1.fontWeight,
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable blockquote': {
    margin: `${theme.spacing(2)} 0`,
    padding: `${theme.spacing(1)} ${theme.spacing(2)}`,
    borderLeft: `4px solid ${theme.palette.primary.main}`,
    backgroundColor: theme.palette.action.hover,
    fontStyle: 'italic',
    color: theme.palette.text.secondary,
    borderRadius: isReadOnly ? `0 ${theme.shape.borderRadius}px ${theme.shape.borderRadius}px 0` : undefined,
  },
  '.mdxeditor-root-contenteditable ul, .mdxeditor-root-contenteditable ol': {
    margin: `${theme.spacing(1)} 0`,
    paddingLeft: theme.spacing(3),
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable li': {
    marginBottom: isReadOnly ? theme.spacing(0.5) : theme.spacing(1),
    color: theme.palette.text.primary,
  },
  '.mdxeditor-root-contenteditable strong': {
    fontWeight: theme.typography.fontWeightBold,
  },
  '.mdxeditor-root-contenteditable em': {
    fontStyle: 'italic',
  },
  '.mdxeditor-root-contenteditable u': {
    textDecoration: 'underline',
  },
  '.mdxeditor-root-contenteditable hr': {
    border: 'none',
    borderTop: `1px solid ${theme.palette.divider}`,
    margin: `${theme.spacing(3)} 0`,
  },
  '.mdxeditor-root-contenteditable > p:first-of-type': {
    marginTop: 0,
  },
  '.mdxeditor-root-contenteditable > *:last-child': {
    marginBottom: 0,
  },
  '.mdxeditor-popup-container': {
    zIndex: theme.zIndex.modal,
  },
  '.mdxeditor-select-content': {
    backgroundColor: theme.palette.background.paper,
    border: `1px solid ${theme.palette.divider}`,
    borderRadius: theme.shape.borderRadius,
    boxShadow: theme.shadows[4],
    zIndex: theme.zIndex.tooltip,
  },
});