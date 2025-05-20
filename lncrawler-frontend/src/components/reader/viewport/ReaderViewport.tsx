import React, { forwardRef } from 'react';
import { Box, useTheme } from '@mui/material';
import { EdgeTapBehavior } from '../ReaderSettings';

interface ReaderViewportProps {
  children: React.ReactNode;
  isMobile: boolean;
  controlsVisible: boolean;
  edgeTapWidthPercentage: number;
  dimLevel?: number;
  leftEdgeTapBehavior: EdgeTapBehavior;
  rightEdgeTapBehavior: EdgeTapBehavior;
  onContentClick: (e: React.MouseEvent<HTMLDivElement>) => void;
}

const ReaderViewport = forwardRef<HTMLDivElement, ReaderViewportProps>((
  {
    children,
    isMobile,
    controlsVisible,
    edgeTapWidthPercentage,
    dimLevel = 0,
    onContentClick
  }, 
  ref
) => {
  const theme = useTheme();

  return (
    <Box
      ref={ref}
      onClick={onContentClick}
      sx={{
        minHeight: 'calc(100vh - 64px)',
        position: 'relative',
        // Display overlay indicators for edge tap zones on mobile
        '&::before, &::after': isMobile ? {
          content: '""',
          position: 'fixed',
          top: 0,
          bottom: 0,
          width: `${edgeTapWidthPercentage}%`,
          backgroundColor: 'rgba(0, 0, 0, 0.05)',
          zIndex: 0,
          pointerEvents: 'none',
          opacity: controlsVisible ? 1 : 0,
          transition: 'opacity 0.3s ease'
        } : {},
        '&::before': isMobile ? {
          left: 0,
          borderRight: '1px dashed rgba(0, 0, 0, 0.2)'
        } : {},
        '&::after': isMobile ? {
          right: 0,
          borderLeft: '1px dashed rgba(0, 0, 0, 0.2)'
        } : {}
      }}
    >
      {/* Dimming Overlay */}
      {dimLevel > 0 && (
        <Box
          sx={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            backgroundColor: 'black',
            opacity: dimLevel / 100,
            zIndex: theme.zIndex.drawer - 1,
            pointerEvents: 'none', // Allows clicking through the overlay
          }}
        />
      )}
      
      {children}
    </Box>
  );
});

ReaderViewport.displayName = 'ReaderViewport';

export default ReaderViewport;
