import { Box, ButtonBase, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';

export type ScreenZone = 'left' | 'middle' | 'right';

interface ScreenZoneItem {
  label: string;
  // What the zone currently does
  value: string;
}

interface ScreenZoneMapProps {
  zone: ScreenZone;
  onZoneChange: (zone: ScreenZone) => void;
  items: Record<ScreenZone, ScreenZoneItem>;
  // The edge whose slide-to-dim is on, if any
  dimEdge: 'left' | 'right' | null;
}

const ZONES: ScreenZone[] = ['left', 'middle', 'right'];

// The screen as three zones. Choosing one shows what it does in the panel below.
const ScreenZoneMap = ({ zone, onZoneChange, items, dimEdge }: ScreenZoneMapProps) => {
  const { t } = useTranslation();

  return (
    <Box
      role="group"
      aria-label={t('readerSettingsPages.screenZones')}
      sx={{ display: 'flex', height: 168, overflow: 'hidden', borderRadius: 4, border: 1, borderColor: 'divider', bgcolor: 'background.paper' }}
    >
      {ZONES.map((id) => {
        const selected = zone === id;
        return (
          <ButtonBase
            key={id}
            aria-pressed={selected}
            onClick={() => onZoneChange(id)}
            sx={{
              flex: id === 'middle' ? 1 : '0 0 22%',
              flexDirection: 'column',
              gap: 0.5,
              p: 1,
              minWidth: 44,
              textAlign: 'center',
              bgcolor: selected ? 'action.selected' : 'transparent',
              outline: selected ? '2px solid' : 'none',
              outlineColor: 'primary.main',
              outlineOffset: -2,
            }}
          >
            <Typography variant="caption" color="text.secondary">{items[id].label}</Typography>
            <Typography variant="body2" sx={{ fontWeight: 600 }}>{items[id].value}</Typography>
            {dimEdge === id && (
              <Typography variant="caption" color="primary">{t('readerSettingsPages.dimTag')}</Typography>
            )}
          </ButtonBase>
        );
      })}
    </Box>
  );
};

export default ScreenZoneMap;
