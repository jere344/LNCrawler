import React from 'react';
import { Chip, Grid, Tooltip } from '@mui/material';
import VisibilityIcon from '@mui/icons-material/Visibility';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import UpdateIcon from '@mui/icons-material/Update';
import { Novel, NovelFromSource } from '@models/novels_types';
import { formatCount, formatTimeAgoOrUnknown } from '@utils/Misc';
import { useTranslation } from 'react-i18next';

interface NovelStatsChipsProps {
  novel: Novel;
  source?: NovelFromSource | null;
  // Wraps each chip in a Grid item: chapters and views share a row, the update chip takes the full width.
  asGrid?: boolean;
}

// Available chapters, views and last update, as small chips. The caller lays them out.
const NovelStatsChips: React.FC<NovelStatsChipsProps> = ({ novel, source, asGrid = false }) => {
  const { t } = useTranslation();

  const chips = [
    {
      key: 'chapters',
      size: 6 as const,
      tooltip: t('cards.availableChapters'),
      icon: <MenuBookIcon />,
      label: source?.available_chapters_count != null ? formatCount(source.available_chapters_count) : t('common.unknown'),
    },
    {
      key: 'views',
      size: 6 as const,
      tooltip: t('cards.views'),
      icon: <VisibilityIcon />,
      label: novel.total_views !== undefined ? formatCount(novel.total_views) : t('common.unknown'),
    },
    {
      key: 'updated',
      size: 12 as const,
      tooltip: t('cards.lastUpdated'),
      icon: <UpdateIcon />,
      label: formatTimeAgoOrUnknown(source?.last_chapter_update, t),
    },
  ];

  return (
    <>
      {chips.map(({ key, size, tooltip, icon, label }) => {
        const chip = (
          <Tooltip title={tooltip}>
            <Chip icon={icon} label={label} size="small" variant="outlined" />
          </Tooltip>
        );
        return asGrid ? (
          <Grid key={key} size={size}>
            {chip}
          </Grid>
        ) : (
          <React.Fragment key={key}>{chip}</React.Fragment>
        );
      })}
    </>
  );
};

export default NovelStatsChips;
