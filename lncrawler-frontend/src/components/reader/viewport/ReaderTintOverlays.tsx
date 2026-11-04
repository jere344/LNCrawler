import { useEffect, useState } from 'react';
import { Box, useTheme } from '@mui/material';

interface ReaderTintOverlaysProps {
  dimLevel: number;
  nightMode: boolean;
  nightModeStrength: number;
  nightModeScheduleEnabled: boolean;
  nightModeStartTime: string;
  nightModeEndTime: string;
}

const TIME_PATTERN = /^\d{2}:\d{2}$/;

// Minutes since midnight, or undefined for a time that is not HH:MM
const toMinutes = (time: string): number | undefined => {
  if (!TIME_PATTERN.test(time)) return undefined;
  const [hour, min] = time.split(':').map(Number);
  return hour * 60 + min;
};

// Whether the time now is inside the night mode schedule (overnight ranges like 20:00 to 06:00 are allowed).
// A time that cannot be read counts as inside, so night mode is never silently off.
const isWithinSchedule = (startTime: string, endTime: string) => {
  const start = toMinutes(startTime);
  const end = toMinutes(endTime);
  if (start === undefined || end === undefined) return true;

  const now = new Date();
  const currentTime = now.getHours() * 60 + now.getMinutes();

  if (start > end) {
    return currentTime >= start || currentTime <= end;
  }

  return currentTime >= start && currentTime <= end;
};

// Dimming and night mode filter, drawn over the whole screen without blocking clicks
const ReaderTintOverlays = ({
  dimLevel,
  nightMode,
  nightModeStrength,
  nightModeScheduleEnabled,
  nightModeStartTime,
  nightModeEndTime,
}: ReaderTintOverlaysProps) => {
  const theme = useTheme();

  // Re-render every minute so a schedule boundary is crossed without a reload.
  const [, setClockTick] = useState(0);
  useEffect(() => {
    if (!nightModeScheduleEnabled) return;
    const interval = window.setInterval(() => setClockTick((tick) => tick + 1), 60000);
    return () => window.clearInterval(interval);
  }, [nightModeScheduleEnabled]);

  const nightModeActive = nightMode &&
    (!nightModeScheduleEnabled || isWithinSchedule(nightModeStartTime, nightModeEndTime));

  return (
    <>
      {dimLevel > 0 && (
        <Box
          sx={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'black',
            opacity: dimLevel / 100,
            zIndex: theme.zIndex.appBar,
            pointerEvents: 'none', // Allows clicking through the overlay
          }}
        />
      )}

      {/* Night Mode Blue Light Filter Overlay */}
      <Box
        sx={{
          position: 'fixed',
          inset: 0,
          backgroundColor: '#ffb347', // Warm orange tint to filter blue light
          opacity: nightModeActive ? nightModeStrength / 100 : 0,
          zIndex: theme.zIndex.appBar,
          pointerEvents: 'none', // Allows clicking through the overlay
          mixBlendMode: 'multiply', // Better blending for blue light filter effect
          transition: 'opacity 0.5s ease-in-out', // Smooth fade in/out transition
          '@media (prefers-reduced-motion: reduce)': { transition: 'none' },
        }}
      />
    </>
  );
};

export default ReaderTintOverlays;
