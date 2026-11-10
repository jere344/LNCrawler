import React from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Box, Chip, IconButton, Tooltip, Typography, alpha, useTheme } from '@mui/material';
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import ImageIcon from '@mui/icons-material/Image';
import type { NovelFromSource } from '@models/novels_types';
import { editionLabel, formatDate, languageCodeToName, languageFlagUrl } from '@utils/Misc';
import { sourceChapterCount } from './sourceFilters';

// Source | Language | Version | Chapters | Updated | Rating
export const SOURCE_COLUMNS = 'minmax(0, 2fr) 140px 110px minmax(0, 1.4fr) 110px 128px';

const STALE_DAYS = 90;

const nowrap = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } as const;

const relativeTime = (dateString: string, locale: string): { text: string; stale: boolean } => {
  const days = Math.round((Date.now() - Date.parse(dateString)) / 864e5);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
  let text: string;
  if (days < 14) text = rtf.format(-Math.max(days, 0), 'day');
  else if (days < 60) text = rtf.format(-Math.floor(days / 7), 'week');
  else if (days < 365) text = rtf.format(-Math.floor(days / 30), 'month');
  else text = rtf.format(-Math.floor(days / 365), 'year');
  return { text, stale: days > STALE_DAYS };
};

export const SourceCover: React.FC<{ source: NovelFromSource }> = ({ source }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const frame = {
    width: 40,
    height: 56,
    flex: 'none',
    borderRadius: '4px',
    border: `1px solid ${alpha(theme.palette.divider, 0.2)}`,
  };
  if (source.cover_min_url) {
    return (
      <Box
        component="img"
        src={source.cover_min_url}
        alt={t('novelSources.coverAlt', { name: source.source_name })}
        loading="lazy"
        sx={{ ...frame, objectFit: 'cover' }}
      />
    );
  }
  return (
    <Box sx={{ ...frame, display: 'grid', placeItems: 'center', backgroundColor: alpha(theme.palette.primary.main, 0.08) }}>
      <ImageIcon sx={{ color: alpha(theme.palette.primary.main, 0.4) }} />
    </Box>
  );
};

const Flag: React.FC<{ language: string; withName?: boolean }> = ({ language, withName }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  if (!language) return <Typography variant="body2" color="text.secondary">{t('common.unknown')}</Typography>;
  const name = languageCodeToName(t, language);
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      <img
        src={languageFlagUrl(language)}
        alt={withName ? '' : name}
        title={name}
        style={{ width: 20, height: 15, objectFit: 'cover', borderRadius: 2, flex: 'none' }}
      />
      {withName && (
        <Typography variant="body2" sx={{ ...nowrap, color: theme.palette.text.secondary, fontWeight: 600 }}>
          {name}
        </Typography>
      )}
    </Box>
  );
};

interface VotesProps {
  source: NovelFromSource;
  voting: boolean;
  onVote: (sourceSlug: string, voteType: 'up' | 'down') => void;
  size: number;
}

const Votes: React.FC<VotesProps> = ({ source, voting, onVote, size }) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const score = source.vote_score;
  const button = (type: 'up' | 'down') => {
    const active = source.user_vote === type;
    const tone = type === 'up' ? theme.palette.primary.main : theme.palette.error.main;
    return (
      <Tooltip title={t(type === 'up' ? 'novelSources.upvote' : 'novelSources.downvote')}>
        <span>
          <IconButton
            aria-label={`${t(type === 'up' ? 'novelSources.upvote' : 'novelSources.downvote')}: ${source.source_name}`}
            aria-pressed={active}
            disabled={voting}
            onClick={() => onVote(source.source_slug, type)}
            sx={{
              width: size,
              height: size,
              color: active ? tone : alpha(theme.palette.text.primary, 0.6),
              '&:hover': { color: tone, bgcolor: alpha(tone, 0.1) },
            }}
          >
            {type === 'up' ? <ThumbUpIcon fontSize="small" /> : <ThumbDownIcon fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
    );
  };
  return (
    <Box sx={{ position: 'relative', zIndex: 2, display: 'inline-flex', alignItems: 'center' }}>
      {button('up')}
      <Typography
        component="span"
        sx={{
          minWidth: 24,
          textAlign: 'center',
          fontWeight: 700,
          fontSize: 13,
          color: score > 0 ? theme.palette.success.main : score < 0 ? theme.palette.error.light : theme.palette.text.secondary,
        }}
      >
        {score}
      </Typography>
      {button('down')}
    </Box>
  );
};

interface SourceRowProps {
  source: NovelFromSource;
  novelSlug: string;
  mobile: boolean;
  voting: boolean;
  onVote: (sourceSlug: string, voteType: 'up' | 'down') => void;
}

const SourceRow: React.FC<SourceRowProps> = ({ source, novelSlug, mobile, voting, onVote }) => {
  const { t, i18n } = useTranslation();
  const theme = useTheme();
  const disabled = !!source.is_disabled;
  const edition = editionLabel(source.edition, t);
  const updated = relativeTime(source.last_chapter_update, i18n.language);
  const latest = source.latest_available_chapter?.display_title;
  const dim = disabled ? { opacity: 0.6 } : undefined;

  const link = (
    <Box
      component={Link}
      to={`/novels/${novelSlug}/${source.source_slug}`}
      aria-label={t('novelSources.openSource', { name: source.source_name })}
      sx={{
        position: 'absolute',
        inset: 0,
        zIndex: 1,
        '&:focus-visible': { outline: `2px solid ${theme.palette.primary.main}`, outlineOffset: -3 },
      }}
    />
  );

  const name = (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0 }}>
      <Typography sx={{ ...nowrap, ...dim, fontWeight: 600, fontSize: 15, color: theme.palette.primary.main }}>
        {source.source_name}
      </Typography>
      {disabled && <Chip size="small" variant="outlined" label={t('novelSources.disabled')} sx={{ flex: 'none' }} />}
    </Box>
  );
  const subtitle = (text: string) => (
    <Typography variant="body2" sx={{ ...nowrap, ...dim, fontSize: 12, color: theme.palette.text.secondary }}>
      {text}
    </Typography>
  );

  const rowSx = {
    position: 'relative',
    borderTop: `1px solid ${alpha(theme.palette.divider, 0.12)}`,
    '&:hover': { bgcolor: alpha(theme.palette.primary.main, 0.06) },
  } as const;

  if (mobile) {
    return (
      <Box sx={{ ...rowSx, display: 'flex', gap: 1.5, py: 1.5 }}>
        {link}
        <Box sx={dim}><SourceCover source={source} /></Box>
        <Box sx={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 0.25 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>{name}</Box>
            <Flag language={source.language} />
          </Box>
          {subtitle([source.title, edition].filter(Boolean).join(' · '))}
          {latest && subtitle(latest)}
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
            <Typography component="span" variant="body2" sx={{ ...dim, color: theme.palette.text.secondary, fontSize: 12 }}>
              <Box component="b" sx={{ color: theme.palette.primary.main, fontSize: 14 }}>{sourceChapterCount(source)}</Box>
              {' · '}
              <Box component="span" sx={{ color: updated.stale ? theme.palette.warning.main : 'inherit' }}>{updated.text}</Box>
            </Typography>
            <Box sx={{ my: -1, mr: -1.25 }}>
              <Votes source={source} voting={voting} onVote={onVote} size={44} />
            </Box>
          </Box>
        </Box>
      </Box>
    );
  }

  return (
    <Box sx={{ ...rowSx, display: 'grid', gridTemplateColumns: SOURCE_COLUMNS, alignItems: 'center', columnGap: 2, px: 1, py: 1.25, minHeight: 76 }}>
      {link}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, minWidth: 0 }}>
        <Box sx={dim}><SourceCover source={source} /></Box>
        <Box sx={{ minWidth: 0 }}>
          {name}
          {subtitle(source.title)}
        </Box>
      </Box>
      <Box sx={dim}><Flag language={source.language} withName /></Box>
      <Typography variant="body2" sx={{ ...nowrap, ...dim }}>{edition}</Typography>
      <Box sx={{ minWidth: 0, ...dim }}>
        <Typography sx={{ fontWeight: 700, fontSize: 15, color: theme.palette.primary.main }}>{sourceChapterCount(source)}</Typography>
        {latest && subtitle(latest)}
      </Box>
      <Typography
        variant="body2"
        title={formatDate(source.last_chapter_update, i18n.language)}
        sx={{ ...dim, color: updated.stale ? theme.palette.warning.main : 'inherit' }}
      >
        {updated.text}
      </Typography>
      <Votes source={source} voting={voting} onVote={onVote} size={32} />
    </Box>
  );
};

export default SourceRow;
