import React, { forwardRef } from 'react';
import { Box, useTheme } from '@mui/material';
import { EdgeTapBehavior } from '../ReaderSettings';

interface ReaderViewportProps {
  children: React.ReactNode;
  isMobile: boolean;
  controlsVisible: boolean;
  edgeTapWidthPercentage: number;
  dimLevel?: number;
  nightMode?: boolean;
  nightModeStrength?: number;
  nightModeScheduleEnabled?: boolean;
  nightModeStartTime?: string;
  nightModeEndTime?: string;
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
    nightMode = false,
    nightModeStrength = 50,
    nightModeScheduleEnabled = false,
    nightModeStartTime = '20:00',
    nightModeEndTime = '06:00',
    onContentClick
  }, 
  ref
) => {
  const theme = useTheme();

  // Function to check if current time is within night mode schedule
  const isNightModeTime = () => {
    if (!nightModeScheduleEnabled) return true;
    
    const now = new Date();
    const currentTime = now.getHours() * 60 + now.getMinutes();
    
    const [startHour, startMin] = nightModeStartTime.split(':').map(Number);
    const [endHour, endMin] = nightModeEndTime.split(':').map(Number);
    
    const startTime = startHour * 60 + startMin;
    const endTime = endHour * 60 + endMin;
    
    // Handle overnight schedules (e.g., 20:00 to 06:00)
    if (startTime > endTime) {
      return currentTime >= startTime || currentTime <= endTime;
    }
    
    return currentTime >= startTime && currentTime <= endTime;
  };

  // Determine if night mode should be active
  const nightModeActive = nightMode && (!nightModeScheduleEnabled || isNightModeTime());

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
      
      {/* Night Mode Blue Light Filter Overlay */}
      <Box
        sx={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: '#ffb347', // Warm orange tint to filter blue light
          opacity: nightModeActive ? nightModeStrength / 100 : 0,
          zIndex: theme.zIndex.drawer - 2,
          pointerEvents: 'none', // Allows clicking through the overlay
          mixBlendMode: 'multiply', // Better blending for blue light filter effect
          transition: 'opacity 0.5s ease-in-out', // Smooth fade in/out transition
        }}
      />
      
      {children}
    </Box>
  );
});

ReaderViewport.displayName = 'ReaderViewport';

export default ReaderViewport;
