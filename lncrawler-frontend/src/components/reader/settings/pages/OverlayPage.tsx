import { Box, Chip, ToggleButton, ToggleButtonGroup, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { SettingGroupHeading, SettingRow, SettingSelect, SettingStepper, SettingSwitch, PageFootReset } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import { OVERLAY_ITEMS, type OverlayItem, type OverlayPosition, type OverlaySize } from '../../readerSettingsSchema';

const POSITIONS: OverlayPosition[] = ['top', 'bottom'];
const SIZES: OverlaySize[] = ['full', 'center', 'left', 'right'];

// Whether this browser exposes the battery level (Chromium only)
const BATTERY_SUPPORTED = typeof navigator !== 'undefined' && 'getBattery' in navigator;

const isItemAvailable = (item: OverlayItem) => item !== 'battery' || BATTERY_SUPPORTED;

// A small strip of reading info over the text: where it sits, how wide it is and what it shows
const OverlayPage = () => {
  const { t } = useTranslation();
  const { overlayEnabled, overlaySize, overlayEdgeOffset, overlayItems } = useReaderSettings();

  // Items keep the order they were turned on in, which is the order the overlay shows them
  const toggleItem = (item: OverlayItem) => {
    updateReaderSetting(
      'overlayItems',
      overlayItems.includes(item) ? overlayItems.filter((i) => i !== item) : [...overlayItems, item],
    );
  };

  return (
    <Box>
      <SettingSwitch
        settingKey="overlayEnabled"
        settingId="overlayEnabled"
        title={t('readerSettingsPages.overlay.enable')}
        sub={t('readerSettingsPages.overlay.enableHint')}
      />

      <SettingGroupHeading>{t('readerSettingsPages.overlay.layout')}</SettingGroupHeading>
      <SettingSelect
        settingKey="overlayPosition"
        settingId="overlayPosition"
        title={t('readerSettingsPages.overlay.position')}
        disabled={!overlayEnabled}
        options={POSITIONS.map((value) => ({ value, label: t(`readerSettingsPages.overlay.positions.${value}`) }))}
      />
      <SettingRow
        settingId="overlaySize"
        title={t('readerSettingsPages.overlay.size')}
        control={null}
      />
      <ToggleButtonGroup
        exclusive
        fullWidth
        size="small"
        disabled={!overlayEnabled}
        value={overlaySize}
        aria-label={t('readerSettingsPages.overlay.size')}
        onChange={(_, value: OverlaySize | null) => {
          if (value) updateReaderSetting('overlaySize', value);
        }}
      >
        {SIZES.map((value) => (
          <ToggleButton key={value} value={value}>{t(`readerSettingsPages.overlay.sizes.${value}`)}</ToggleButton>
        ))}
      </ToggleButtonGroup>

      <SettingStepper
        title={t('readerSettingsPages.overlay.edgeOffset')}
        sub={t('readerSettingsPages.overlay.edgeOffsetHint')}
        settingKey="overlayEdgeOffset"
        value={overlayEdgeOffset}
        step={2}
        min={0}
        max={80}
        disabled={!overlayEnabled}
        format={(value) => `${value}px`}
      />

      <SettingGroupHeading>{t('readerSettingsPages.overlay.content')}</SettingGroupHeading>
      <Box data-setting-id="overlayItems" sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, pb: 1 }}>
        {OVERLAY_ITEMS.filter(isItemAvailable).map((item) => {
          const order = overlayItems.indexOf(item);
          return (
            <Chip
              key={item}
              clickable
              disabled={!overlayEnabled}
              color={order === -1 ? 'default' : 'primary'}
              variant={order === -1 ? 'outlined' : 'filled'}
              label={order === -1 ? t(`readerSettingsPages.overlay.items.${item}`) : `${order + 1}. ${t(`readerSettingsPages.overlay.items.${item}`)}`}
              aria-pressed={order !== -1}
              onClick={() => toggleItem(item)}
            />
          );
        })}
      </Box>
      <Typography variant="body2" color="text.secondary">{t('readerSettingsPages.overlay.contentHint')}</Typography>

      <PageFootReset keys={['overlayEnabled', 'overlayPosition', 'overlaySize', 'overlayEdgeOffset', 'overlayItems']} />
    </Box>
  );
};

export default OverlayPage;
