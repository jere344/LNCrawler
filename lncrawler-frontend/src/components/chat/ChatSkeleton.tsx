import { Box, Paper, Skeleton, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

/** Chat page skeleton: same frame, message panel and composer as the loaded chat. */
const ChatSkeleton = () => {
  const { t } = useTranslation();

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: { xs: 'calc(100vh - 200px)', md: 'calc(100vh - 180px)' },
        minHeight: 420,
        py: 1,
      }}
    >
      <Typography variant="h6" sx={{ mb: 1 }}>
        {t('chat.title')}
      </Typography>

      <Box
        sx={{
          flex: 1,
          minHeight: 0,
          overflow: 'hidden',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          p: 1,
        }}
      >
        {[...Array(6)].map((_, index) => (
          <Box
            key={`chat-skeleton-${index}`}
            sx={{ display: 'flex', flexDirection: 'column', alignItems: index % 2 ? 'flex-end' : 'flex-start', mb: 2 }}
          >
            <Skeleton variant="text" width={120} height={16} />
            <Skeleton variant="rounded" width={`${45 + ((index * 13) % 35)}%`} height={44} />
          </Box>
        ))}
      </Box>

      <Paper elevation={2} sx={{ p: 1, borderRadius: 2, mt: 1 }}>
        <Skeleton variant="rounded" height={56} />
      </Paper>
    </Box>
  );
};

export default ChatSkeleton;
