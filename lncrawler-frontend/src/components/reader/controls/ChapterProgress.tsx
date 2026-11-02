import { useEffect, useState } from 'react';
import { Box, LinearProgress, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

// Share of the page scrolled through. It keeps its own state, so the reader does not re-render on every scroll.
const ChapterProgress = () => {
  const { t } = useTranslation();
  const [percent, setPercent] = useState(0);

  useEffect(() => {
    let frame: number | null = null;
    const update = () => {
      frame = null;
      const doc = document.documentElement;
      const scrollable = doc.scrollHeight - doc.clientHeight;
      setPercent(scrollable > 0 ? Math.min(100, Math.round((window.scrollY / scrollable) * 100)) : 0);
    };
    const handleScroll = () => {
      if (frame === null) frame = window.requestAnimationFrame(update);
    };

    update();
    window.addEventListener('scroll', handleScroll, { passive: true });
    window.addEventListener('resize', handleScroll);
    return () => {
      window.removeEventListener('scroll', handleScroll);
      window.removeEventListener('resize', handleScroll);
      if (frame !== null) window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 0.5 }}>
      <LinearProgress
        variant="determinate"
        value={percent}
        aria-label={t('readerControls.readProgress')}
        sx={{ height: 3, borderRadius: 1 }}
      />
      <Typography variant="caption" color="text.secondary" align="center" noWrap>
        {t('readerControls.progress', { percent })}
      </Typography>
    </Box>
  );
};

export default ChapterProgress;
