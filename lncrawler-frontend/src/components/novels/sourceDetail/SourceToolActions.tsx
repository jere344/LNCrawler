import { Box, CircularProgress, Menu, MenuItem } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ViewListIcon from '@mui/icons-material/ViewList';
import CollectionsIcon from '@mui/icons-material/Collections';
import DownloadIcon from '@mui/icons-material/Download';
import ActionButton from '../../common/ActionButton';
import { useEpubDownload } from '@utils/useEpubDownload';
import { NovelFromSource as ISourceDetail } from '@models/novels_types';

const SourceToolActions = ({
  source,
  novelSlug,
  sourceSlug,
  isDmca,
  downloadAnchor,
  setDownloadAnchor,
  preparingKey,
  startDownload,
}: {
  source: ISourceDetail;
  novelSlug: string | undefined;
  sourceSlug: string | undefined;
  isDmca: boolean;
  downloadAnchor: HTMLElement | null;
  setDownloadAnchor: (anchor: HTMLElement | null) => void;
  preparingKey: ReturnType<typeof useEpubDownload>['preparingKey'];
  startDownload: ReturnType<typeof useEpubDownload>['startDownload'];
}) => {
  const { t } = useTranslation();
  return (
    <>
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
        <ActionButton
          compact
          fullWidth={false}
          title={t('sourceDetail.chapterList')}
          startIcon={<ViewListIcon />}
          color="info"
          to={`/novels/${novelSlug}/${sourceSlug}/chapterlist`}
          disabled={!source?.latest_available_chapter}
          tooltip={t('sourceDetail.browseAllChapters')}
        />

        <ActionButton
          compact
          fullWidth={false}
          title={t('sourceDetail.imageGallery')}
          startIcon={<CollectionsIcon />}
          color="secondary"
          to={`/novels/${novelSlug}/${sourceSlug}/gallery`}
          tooltip={t('sourceDetail.viewImageGallery')}
        />

        <ActionButton
          compact
          fullWidth={false}
          title={t('sourceDetail.download')}
          startIcon={<DownloadIcon />}
          color="info"
          onClick={(e) => setDownloadAnchor(e.currentTarget)}
          disabled={isDmca || !source?.chapters_count}
          tooltip={isDmca ? t('sourceDetail.dmcaNotice') : t('sourceDetail.downloadTooltip')}
        />
      </Box>

      <Menu
        anchorEl={downloadAnchor}
        open={Boolean(downloadAnchor)}
        onClose={() => setDownloadAnchor(null)}
      >
        <MenuItem
          disabled={preparingKey !== null}
          onClick={() => {
            setDownloadAnchor(null);
            startDownload();
          }}
        >
          {preparingKey === 'full' && <CircularProgress size={16} sx={{ mr: 1 }} />}
          {t('sourceDetail.downloadFull')}
        </MenuItem>
        {source?.volumes && source.volumes.length > 1 && source.volumes.map((v) => (
          <MenuItem
            key={v.volume_id}
            disabled={preparingKey !== null}
            onClick={() => {
              setDownloadAnchor(null);
              startDownload(v.volume_id);
            }}
          >
            {preparingKey === String(v.volume_id) && <CircularProgress size={16} sx={{ mr: 1 }} />}
            {v.title || t('sourceDetail.volumeN', { n: v.volume_id })}
          </MenuItem>
        ))}
      </Menu>
    </>
  );
};

export default SourceToolActions;
