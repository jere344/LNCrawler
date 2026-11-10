import React, { ReactNode, useId, useState } from 'react';
import { Typography, Paper, Box, ButtonBase, Collapse, useTheme, alpha } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import type { SxProps } from '@mui/material';

interface SectionContainerProps {
  title: string;
  icon: React.ReactNode;
  children: ReactNode;
  // Makes the title a toggle that folds the content away.
  collapsible?: boolean;
  defaultCollapsed?: boolean;
  // Shown beside the title, e.g. a count.
  badge?: ReactNode;
}

const SectionContainer: React.FC<SectionContainerProps> = ({
  title,
  icon,
  children,
  collapsible = false,
  defaultCollapsed = false,
  badge,
}) => {
  const theme = useTheme();
  const [open, setOpen] = useState(!defaultCollapsed);
  const contentId = useId();

  const heading = (
    <>
      {React.cloneElement(icon as React.ReactElement<{ sx?: SxProps }>, { sx: { mr: 1, color: theme.palette.primary.main } })}
      {title}
      {badge && (
        <Typography component="span" variant="body2" sx={{ ml: 1.5, color: theme.palette.text.secondary, fontWeight: 600 }}>
          {badge}
        </Typography>
      )}
    </>
  );

  return (
    <Paper
      elevation={3}
      sx={{
        p: 3,
        mb: 4,
        borderRadius: 3,
        background: theme.palette.mode === 'dark'
          ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
          : theme.palette.background.paper,
        position: 'relative',
      }}
    >
      {/* Decorative element */}
      <Box
        sx={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '5px',
          height: '100%',
          background: `linear-gradient(to bottom, ${theme.palette.primary.main}, ${theme.palette.secondary.main})`,
        }}
      />

      <Typography
        variant="h5"
        gutterBottom={open}
        sx={{
          pl: 2,
          borderBottom: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
          pb: 1,
          display: 'flex',
          alignItems: 'center',
        }}
      >
        {collapsible ? (
          <ButtonBase
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            aria-controls={contentId}
            sx={{
              flexGrow: 1,
              justifyContent: 'flex-start',
              textAlign: 'left',
              font: 'inherit',
              color: 'inherit',
              letterSpacing: 'inherit',
              borderRadius: 1,
              minHeight: 44,
              '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: 2 },
            }}
          >
            {heading}
            <ExpandMoreIcon
              sx={{
                ml: 'auto',
                color: theme.palette.text.secondary,
                transform: open ? 'rotate(180deg)' : 'none',
                transition: theme.transitions.create('transform'),
              }}
            />
          </ButtonBase>
        ) : (
          heading
        )}
      </Typography>

      {collapsible ? (
        <Collapse in={open} id={contentId} unmountOnExit>
          {children}
        </Collapse>
      ) : (
        children
      )}
    </Paper>
  );
};

export default SectionContainer;
