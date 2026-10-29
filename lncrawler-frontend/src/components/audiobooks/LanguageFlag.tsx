import { useTranslation } from 'react-i18next';
import { Box, Tooltip } from '@mui/material';
import { languageCodeToName, languageFlagUrl } from '@utils/Misc';

// Language flag of an audiobook, in the corner of its cover: same look as the flags of the novel cards.
const LanguageFlag = ({ language }: { language: string }) => {
  const { t } = useTranslation();
  const name = languageCodeToName(t, language);
  return (
    <Box sx={{ position: 'absolute', top: 8, right: 8, zIndex: 2, pointerEvents: 'none' }}>
      <Tooltip title={name}>
        <Box sx={{ width: 30, pointerEvents: 'auto', border: '1px solid rgb(0, 0, 0)', borderRadius: 1, boxShadow: '0 2px 4px rgba(0,0,0,0.4)' }}>
          <Box
            component="img"
            src={languageFlagUrl(language)}
            alt={name}
            sx={{ display: 'block', width: 30, height: 20, objectFit: 'cover', borderRadius: '2px' }}
          />
        </Box>
      </Tooltip>
    </Box>
  );
};

export default LanguageFlag;
