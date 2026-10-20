import { Box, Button, Chip, IconButton, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import PersonIcon from '@mui/icons-material/Person';
import LaunchIcon from '@mui/icons-material/Launch';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { editionLabel } from '@utils/Misc.tsx';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';
import NovelRating from '../common/NovelRating';
import { NovelRatingState } from './useSourceDetail';

const SourceHeroDetails = ({
  source,
  novelSlug,
  novelRating,
}: {
  source: ISourceDetail;
  novelSlug: string | undefined;
  novelRating: NovelRatingState;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <>
      {source.alternative_titles?.length > 0 && (
        <Typography
          variant="body2"
          sx={{
            color: alpha(theme.palette.common.white, 0.85),
            textShadow: '0 1px 3px rgba(0,0,0,0.2)',
            mb: 1.5,
          }}
        >
          <strong>{t('sourceDetail.alternativeTitles')}:</strong> {source.alternative_titles.join(', ')}
        </Typography>
      )}
                
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 1,
          mb: 3,
        }}
      >
      <Typography 
        variant="h6" 
        sx={{ 
          color: alpha(theme.palette.common.white, 0.9),
          textShadow: '0 1px 3px rgba(0,0,0,0.2)',
          fontWeight: 500,
          display: 'flex',
          alignItems: 'center',
          gap: 1
        }}
      >
        {t('sourceDetail.fromPrefix')} {source.source_name}
        {source.source_url?.startsWith('http') && (
          <Tooltip title={t('sourceDetail.visitSource')}>
            <IconButton
              size="small"
              href={source.source_url}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ 
                color: alpha(theme.palette.common.white, 0.9),
                '&:hover': {
                  color: theme.palette.common.white,
                  bgcolor: alpha(theme.palette.common.white, 0.1)
                }
              }}
            >
              <LaunchIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Typography>
      {source.edition && (
        <Chip
          size="small"
          label={editionLabel(source.edition, t)}
          sx={{ color: 'inherit', borderColor: 'currentColor' }}
          variant="outlined"
        />
      )}
      </Box>
                
      {/* Author badges */}
      <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 2 }}>
          {source.authors.length > 0 && (
            <Box
              sx={{
                display: 'inline-flex',
                alignItems: 'center',
                bgcolor: alpha('#8e44ad', 0.7),
                backdropFilter: 'blur(10px)',
                px: 2,
                py: 0.75,
                borderRadius: 6,
              }}
            >
              <PersonIcon sx={{ mr: 1, fontSize: '1rem', color: theme.palette.common.white }} />
              <Typography
                variant="body1"
                sx={{
                  color: theme.palette.common.white,
                  fontWeight: 600,
                  display: 'flex',
                  flexWrap: 'wrap',
                  alignItems: 'center',
                }}
              >
                {source.authors.map((author, index) => (
                  <Box key={index} component="span">
                    <Box
                      component={Link}
                      to={`/novels/search?author=${encodeURIComponent(author)}`}
                      sx={{
                        color: theme.palette.common.white,
                        textDecoration: 'none',
                        '&:hover': { textDecoration: 'underline' },
                      }}
                    >
                      {author}
                    </Box>
                    {index < source.authors.length - 1 ? ',\u00a0' : ''}
                  </Box>
                ))}
              </Typography>
            </Box>
          )}
          {source.novelupdates_url && source.novelupdates_url.startsWith('http') && (
            <Tooltip title={t('sourceDetail.viewOnNovelUpdates')}>
              <Button
                size="small"
                variant="outlined"
                href={source.novelupdates_url}
                target="_blank"
                rel="noopener noreferrer"
                startIcon={<MenuBookIcon fontSize="small" />}
                sx={{
                  color: alpha(theme.palette.common.white, 0.9),
                  borderColor: alpha(theme.palette.common.white, 0.5),
                  textTransform: 'none',
                  borderRadius: 6,
                  '&:hover': {
                    color: theme.palette.common.white,
                    borderColor: theme.palette.common.white,
                    bgcolor: alpha(theme.palette.common.white, 0.1),
                  },
                }}
              >
                {t('sourceDetail.novelUpdates')}
              </Button>
            </Tooltip>
          )}
        </Box>
                  
        {/* Novel rating component  */}
        <Box sx={{ mt: 2, display: 'flex', alignItems: 'center' }}>
          {novelSlug && (
            <NovelRating
              novelSlug={novelSlug}
              initialUserRating={novelRating.user_rating}
              initialAvgRating={novelRating.avg_rating}
              initialRatingCount={novelRating.rating_count}
              size="small"
            />
          )}
        </Box>
      </Box>
                
      {/* Divider with gradient */}
      <Box 
        sx={{ 
          height: '2px', 
          background: `linear-gradient(to right, ${alpha(theme.palette.common.white, 0.8)}, transparent)`,
          mb: 2.5,
          mt: 0.5,
        }} 
      />
    </>
  );
};

export default SourceHeroDetails;
