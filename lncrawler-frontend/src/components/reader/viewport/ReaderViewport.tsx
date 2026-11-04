import React from 'react';
import { Box } from '@mui/material';
import type { ControlsTrigger } from '../readerSettingsSchema';
import type { ReaderTapProps } from '../hooks/useReaderTapInput';
import ReaderTintOverlays from './ReaderTintOverlays';

interface ReaderViewportProps {
  children: React.ReactNode;
  controlsTrigger: ControlsTrigger;
  tapProps: ReaderTapProps;
  dimLevel?: number;
  nightMode?: boolean;
  nightModeStrength?: number;
  nightModeScheduleEnabled?: boolean;
  nightModeStartTime?: string;
  nightModeEndTime?: string;
}

const ReaderViewport = ({
  children,
  controlsTrigger,
  tapProps,
  dimLevel = 0,
  nightMode = false,
  nightModeStrength = 50,
  nightModeScheduleEnabled = false,
  nightModeStartTime = '20:00',
  nightModeEndTime = '06:00',
}: ReaderViewportProps) => {
  return (
    <Box
      {...tapProps}
      sx={{
        minHeight: '100dvh',
        position: 'relative',
        // Stops double-tap zoom while keeping pinch and scroll
        touchAction: 'manipulation',
        WebkitTouchCallout: controlsTrigger === 'longPress' ? 'none' : undefined,
      }}
    >
      <ReaderTintOverlays
        dimLevel={dimLevel}
        nightMode={nightMode}
        nightModeStrength={nightModeStrength}
        nightModeScheduleEnabled={nightModeScheduleEnabled}
        nightModeStartTime={nightModeStartTime}
        nightModeEndTime={nightModeEndTime}
      />

      {children}
    </Box>
  );
};

export default ReaderViewport;
