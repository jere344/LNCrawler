import { Box, Button, Typography, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceVoteActions = ({
  source,
  votingInProgress,
  onVote,
}: {
  source: ISourceDetail;
  votingInProgress: boolean;
  onVote: (voteType: 'up' | 'down') => void;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <>
      {/* Source vote actions*/}
      <Box sx={{ mb: 3 }}>
        <Typography variant="body2" sx={{ color: alpha(theme.palette.common.white, 0.8), mb: 1 }}>
          {t('sourceDetail.rateSource')}
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant={source.user_vote === 'up' ? 'contained' : 'outlined'}
            color="success"
            startIcon={<ThumbUpIcon />}
            onClick={() => onVote('up')}
            disabled={votingInProgress}
            sx={{ 
              borderRadius: '20px',
              px: 2,
              backdropFilter: 'blur(10px)',
              minWidth: '120px',
              position: 'relative'
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {t('sourceDetail.upvote')}
              <Typography
                variant="body2"
                sx={{
                  bgcolor: alpha(theme.palette.success.main, 0.2),
                  px: 1,
                  py: 0.2,
                  borderRadius: 1,
                  fontWeight: 'bold'
                }}
              >
                {source.upvotes}
              </Typography>
            </Box>
          </Button>
                    
          <Button
            variant={source.user_vote === 'down' ? 'contained' : 'outlined'}
            color="error"
            startIcon={<ThumbDownIcon />}
            onClick={() => onVote('down')}
            disabled={votingInProgress}
            sx={{ 
              borderRadius: '20px',
              px: 2,
              backdropFilter: 'blur(10px)',
              minWidth: '120px',
              position: 'relative'
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              {t('sourceDetail.downvote')}
              <Typography
                variant="body2"
                sx={{
                  bgcolor: alpha(theme.palette.error.main, 0.2),
                  px: 1,
                  py: 0.2,
                  borderRadius: 1,
                  fontWeight: 'bold'
                }}
              >
                {source.downvotes}
              </Typography>
            </Box>
          </Button>
        </Box>
      </Box>
    </>
  );
};

export default SourceVoteActions;
