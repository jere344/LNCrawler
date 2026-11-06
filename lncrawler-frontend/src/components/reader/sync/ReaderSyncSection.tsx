import { useState } from 'react';
import { Box, MenuItem, Select } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@context/AuthContext';
import { SettingGroupHeading, SettingRow } from '../settings/SettingRows';
import {
  detectDeviceSlot,
  getDeviceSlotPreference,
  setDeviceSlotPreference,
  type DeviceSlotPreference,
} from './deviceSlot';
import { restartReaderSync, type SyncStatus } from './readerSettingsSync';
import { useReaderSyncStatus } from './useReaderSettingsSync';

const STATUS_KEYS: Record<SyncStatus, string> = {
  'signed-out': 'readerSettings.syncStatusSignedOut',
  off: 'readerSettings.syncStatusOff',
  pending: 'readerSettings.syncStatusPending',
  syncing: 'readerSettings.syncStatusSyncing',
  synced: 'readerSettings.syncStatusSynced',
  error: 'readerSettings.syncStatusError',
  'needs-choice': 'readerSettings.syncStatusNeedsChoice',
};

// Sync status and the device type this device saves its settings under
const ReaderSyncSection = () => {
  const { t } = useTranslation();
  const { isAuthenticated } = useAuth();
  const { status, slot } = useReaderSyncStatus();
  const [preference, setPreference] = useState<DeviceSlotPreference>(getDeviceSlotPreference);

  const typeLabel = (type: 'mobile' | 'desktop') =>
    t(type === 'mobile' ? 'readerSettings.syncTypeMobile' : 'readerSettings.syncTypeDesktop');

  const changePreference = (next: DeviceSlotPreference) => {
    setPreference(next);
    setDeviceSlotPreference(next);
    restartReaderSync();
  };

  return (
    <Box sx={{ mb: 2 }}>
      <SettingGroupHeading>{t('readerSettings.syncTitle')}</SettingGroupHeading>
      <SettingRow
        title={t('readerSettings.syncDevice')}
        sub={t(STATUS_KEYS[status], { type: slot === 'off' ? '' : typeLabel(slot) })}
        settingId="syncDevice"
        control={
          <Select
            size="small"
            value={preference}
            disabled={!isAuthenticated}
            onChange={(event) => changePreference(event.target.value as DeviceSlotPreference)}
            SelectDisplayProps={{ 'aria-label': t('readerSettings.syncDevice') }}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="auto">{t('readerSettings.syncDeviceAuto', { type: typeLabel(detectDeviceSlot()) })}</MenuItem>
            <MenuItem value="mobile">{t('readerSettings.syncDeviceMobile')}</MenuItem>
            <MenuItem value="desktop">{t('readerSettings.syncDeviceDesktop')}</MenuItem>
            <MenuItem value="off">{t('readerSettings.syncDeviceOff')}</MenuItem>
          </Select>
        }
      />
    </Box>
  );
};

export default ReaderSyncSection;
