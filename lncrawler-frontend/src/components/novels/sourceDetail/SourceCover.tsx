import type { MouseEvent } from 'react';
import { Box, CardMedia, Zoom, useTheme } from '@mui/material';
import { useTranslation } from 'react-i18next';
import defaultCover from '@assets/default-cover.jpg';
import { AdultBadge } from '@components/common/AdultBadge';
import { languageFlagUrl, languageCodeToName } from '@utils/Misc.tsx';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceCover = ({
  source,
  coverBlurred,
  onCoverClick,
}: {
  source: ISourceDetail;
  coverBlurred: boolean;
  onCoverClick?: (event: MouseEvent) => void;
}) => {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <Zoom in={true} timeout={500}>
      <Box
        sx={{
          position: 'relative',
          width: '100%',
          paddingTop: '150%',
          borderRadius: 2,
          overflow: 'hidden',
          boxShadow: '0 10px 30px rgba(0, 0, 0, 0.3)',
          border: `4px solid ${theme.palette.common.white}`,
        }}
      >
        <CardMedia
          component="img"
          image={source.cover_url || source.cover_min_url || defaultCover}
          alt={source.title}
          onClick={onCoverClick}
          sx={{
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            cursor: coverBlurred ? 'pointer' : undefined,
            filter: coverBlurred ? 'blur(16px)' : 'none',
          }}
          onError={(e) => {
            e.currentTarget.onerror = null;
            e.currentTarget.src = defaultCover;
          }}
        />
        <AdultBadge isAdult={source.is_adult} novelId={source.novel_id} />
                    
        {/* Language indicator */}
        <Box
          sx={{
            position: 'absolute',
            top: 8,
            right: 8,
            bgcolor: 'rgba(0,0,0,0.7)',
            color: 'white',
            px: 1,
            py: 0.3,
            borderRadius: 1,
            fontSize: '0.75rem',
            fontWeight: 'bold',
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            textTransform: 'uppercase',
          }}
        >
          <img 
            src={languageFlagUrl(source.language)} 
            alt={languageCodeToName(t, source.language)}
            style={{ 
              width: '20px',
              height: '15px',
              objectFit: 'cover',
              borderRadius: '2px',
            }}
          />
          {source.language}
        </Box>
      </Box>
    </Zoom>
  );
};

export default SourceCover;
