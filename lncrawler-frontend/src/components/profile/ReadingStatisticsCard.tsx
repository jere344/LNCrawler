import React from 'react';
import { Box, Typography, Paper, Grid, LinearProgress, Tooltip } from '@mui/material';
import ImportContactsIcon from '@mui/icons-material/ImportContacts';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import InfoIcon from '@mui/icons-material/Info';

interface ProfileData {
  word_read?: number;
  chapters_read_count?: number;
  chapters_not_read_yet_count?: number;
}

interface ReadingStatisticsCardProps {
  profileData: ProfileData | null;
}

const ReadingStatisticsCard: React.FC<ReadingStatisticsCardProps> = ({ profileData }) => {
  // Format large numbers with commas
  const formatNumber = (num: number): string => {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  };

  // Calculate reading progress percentage
  const calculateReadingProgress = (): number => {
    if (!profileData) return 0;
    const totalChapters = (profileData.chapters_read_count || 0) + (profileData.chapters_not_read_yet_count || 0);
    return totalChapters > 0 ? ((profileData.chapters_read_count || 0) / totalChapters) * 100 : 0;
  };

  return (
    <Box sx={{ mt: 4 }}>
      <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <ImportContactsIcon /> Reading Statistics
      </Typography>
      
      <Grid container spacing={3}>
        {/* Reading Progress */}
        <Grid item xs={12} md={6}>
          <Paper elevation={1} sx={{ p: 2, bgcolor: 'background.paper' }}>
            <Box sx={{ mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                Reading Progress
                <Tooltip title="Only include bookmarked novels">
                    <InfoIcon fontSize="small" color="action" sx={{ opacity: 0.6, fontSize: '1rem' }} />
                </Tooltip>
              </Typography>
              
              <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                <Typography variant="body2">
                  Chapters Read: <strong>{profileData?.chapters_read_count || 0}</strong>
                </Typography>
                <Typography variant="body2">
                  Chapters Left: <strong>{profileData?.chapters_not_read_yet_count || 0}</strong>
                </Typography>
              </Box>
              <LinearProgress 
                variant="determinate" 
                value={calculateReadingProgress()}
                sx={{ 
                  height: 10, 
                  borderRadius: 5,
                  mb: 1
                }}
              />
              <Typography variant="caption" color="text.secondary">
                {calculateReadingProgress().toFixed(1)}% complete
              </Typography>
            </Box>
          </Paper>
        </Grid>
        
        {/* Word Count */}
        <Grid item xs={12} md={6}>
          <Paper elevation={1} sx={{ p: 2, bgcolor: 'background.paper' }}>
            <Box sx={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', height: '100%' }}>
              <Typography variant="subtitle2" color="text.secondary">
                Total Words Read
              </Typography>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <MenuBookIcon color="primary" />
                <Typography variant="h4" fontWeight="bold">
                  {formatNumber(profileData?.word_read || 0)}
                </Typography>
              </Box>
              <Typography variant="caption" color="text.secondary">
                Approximately {Math.round((profileData?.word_read || 0) / 250)} pages
              </Typography>
            </Box>
          </Paper>
        </Grid>
      </Grid>
    </Box>
  );
};

export default ReadingStatisticsCard;
