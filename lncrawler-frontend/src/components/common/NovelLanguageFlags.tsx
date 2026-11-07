import React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { languageCodeToName, languageFlagUrl } from '@utils/Misc';

const FLAG_WIDTH = 30
const MAX_FLAGS_PER_ROW = 10

interface NovelLanguageFlagsProps {
  languages: string[];
  // 'large': the flags of the novel cards, in a column at the top right. 'small': the first two flags of the reading list cards, at the bottom right.
  size?: 'large' | 'small';
}

// Language flags of a novel cover. Must sit in a cover that is positioned (position: relative).
export const NovelLanguageFlags: React.FC<NovelLanguageFlagsProps> = ({ languages, size = 'large' }) => {
  const { t } = useTranslation();

  if (size === 'small') {
    return (
      <Box
        sx={{
          position: 'absolute',
          bottom: 4,
          right: 4,
          display: 'flex',
          gap: 0.25,
          alignItems: 'center',
        }}
      >
        {languages.length > 0 ? (
          languages.slice(0, 2).map((lang) => (
            <Tooltip key={lang} title={languageCodeToName(t, lang)}>
              <img
                src={languageFlagUrl(lang)}
                alt={languageCodeToName(t, lang)}
                style={{
                  width: '20px',
                  height: '14px',
                  objectFit: 'cover',
                  borderRadius: '2px',
                  boxShadow: '0 1px 2px rgba(0,0,0,0.3)',
                }}
              />
            </Tooltip>
          ))
        ) : (
          <Tooltip title={t('cards.unknownLanguage')}>
            <Box
              sx={{
                width: '20px',
                height: '14px',
                bgcolor: 'rgba(0,0,0,0.6)',
                color: 'white',
                fontSize: '0.7rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: '2px',
              }}
            >
              ?
            </Box>
          </Tooltip>
        )}
      </Box>
    );
  }

  const flagRows = languages.length > MAX_FLAGS_PER_ROW
    ? [
        languages.slice(0, Math.ceil(languages.length / 2)),
        languages.slice(Math.ceil(languages.length / 2)),
      ]
    : [languages];
  const maxFlagsInRow = Math.max(1, ...flagRows.map((row) => row.length));

  return (
    <Box
      sx={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        display: 'flex',
        justifyContent: 'flex-end',
        pointerEvents: 'none',
      }}
    >
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          width: `min(100%, ${FLAG_WIDTH * maxFlagsInRow}px)`,
          boxShadow: '0 2px 4px rgba(0,0,0,0.4)',
          border: '1px solid rgb(0, 0, 0)',
          borderRadius: 1,
          pointerEvents: 'auto',
        }}
      >
        {languages.length > 0 ? (
          flagRows.map((row, rowIndex) => (
            <Box key={rowIndex} sx={{ display: 'flex', justifyContent: 'flex-end' }}>
              {row.map((lang, index) => (
                <Tooltip key={lang} title={languageCodeToName(t, lang)}>
                  <img
                    src={languageFlagUrl(lang)}
                    alt={languageCodeToName(t, lang)}
                    style={{
                      display: 'block',
                      flexShrink: 0,
                      width: `${FLAG_WIDTH}px`,
                      height: '20px',
                      objectFit: 'cover',
                      borderRadius: '2px',
                      marginLeft: index === 0
                        ? 0
                        : `calc(-1 * max(0px, (${FLAG_WIDTH}px * ${row.length} - 100%) / ${row.length - 1}))`,
                    }}
                  />
                </Tooltip>
              ))}
            </Box>
          ))
        ) : (
          <Tooltip title={t('cards.unknownLanguage')}>
            <Typography
              sx={{
                fontSize: '0.8rem', // Adjusted size for consistency
                color: '#fff',
                fontWeight: 'bold',
                lineHeight: 1, // Ensure '?' is vertically centered if it's taller
              }}
            >
              ?
            </Typography>
          </Tooltip>
        )}
      </Box>
    </Box>
  );
};
