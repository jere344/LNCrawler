import { Box, Grid, Typography, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ListAltIcon from '@mui/icons-material/ListAlt';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import { formatDate } from '@utils/Misc.tsx';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceHeroStats = ({ source, language }: { source: ISourceDetail; language: string }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <>
      {/* Source stats */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid size={{ xs: 12, sm: 6, md: 6 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              p: 1,
              borderRadius: 2,
              bgcolor: alpha('#3498db', 0.3),
              backdropFilter: 'blur(10px)',
              border: `1px solid ${alpha('#3498db', 0.5)}`,
            }}
          >
            <ListAltIcon sx={{ color: alpha('#3498db', 0.9), mr: 1 }} />
            <Box>
              <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.7) }}>
                {t('novelSources.chapters')}
              </Typography>
              <Typography variant="body1" sx={{ fontWeight: 700, color: theme.palette.common.white }}>
                {source.available_chapters_count ?? 0}
                {(source.available_chapters_count ?? 0) !== (source.chapters_count ?? 0) && (
                  <Box component="span" sx={{ color: alpha(theme.palette.common.white, 0.5), fontWeight: 400 }}>
                    /{source.chapters_count ?? 0}
                  </Box>
                )}
              </Typography>
            </Box>
          </Box>
        </Grid>
                  
        <Grid size={{ xs: 12, sm: 6, md: 6 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              p: 1,
              borderRadius: 2,
              bgcolor: alpha('#9b59b6', 0.3),
              backdropFilter: 'blur(10px)',
              border: `1px solid ${alpha('#9b59b6', 0.5)}`,
            }}
          >
            <CalendarTodayIcon sx={{ color: alpha('#9b59b6', 0.9), mr: 1 }} />
            <Box>
              <Typography variant="caption" sx={{ color: alpha(theme.palette.common.white, 0.7) }}>
                {t('sourceDetail.lastUpdated')}
              </Typography>
              <Typography variant="body1" sx={{ fontWeight: 700, color: theme.palette.common.white }}>
                {formatDate(source.last_chapter_update, language)}
              </Typography>
            </Box>
          </Box>
        </Grid>
      </Grid>
    </>
  );
};

export default SourceHeroStats;
