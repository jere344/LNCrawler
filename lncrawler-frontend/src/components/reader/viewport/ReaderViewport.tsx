import React from 'react';
import { Box } from '@mui/material';
import type { CenterAction } from '../readerSettingsSchema';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';
import ReaderTintOverlays, { type ReaderTintSettings } from './ReaderTintOverlays';

interface ReaderViewportProps {
  children: React.ReactNode;
  centerLongPress: CenterAction;
  tapProps: ReaderTapProps;
  // Dimming and night mode, drawn over the viewport
  settings: ReaderTintSettings;
}

const ReaderViewport = ({
  children,
  centerLongPress,
  tapProps,
  settings,
}: ReaderViewportProps) => {
  return (
    <Box
      {...tapProps}
      sx={{
        minHeight: '100dvh',
        position: 'relative',
        // Stops double-tap zoom while keeping pinch and scroll
        touchAction: 'manipulation',
        WebkitTouchCallout: centerLongPress !== 'none' ? 'none' : undefined,
      }}
    >
      <ReaderTintOverlays settings={settings} />

      {children}
    </Box>
  );
};

export default ReaderViewport;
