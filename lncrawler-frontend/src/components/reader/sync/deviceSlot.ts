import { READER_DEVICE_SLOT_KEY, readLocalStorage, writeLocalStorage } from '@utils/storage';

// Each device type keeps its own settings on the server
export type DeviceSlot = 'mobile' | 'desktop';
// The device's choice: a type, or no sync at all
export type DeviceSlotChoice = DeviceSlot | 'off';
// What the settings page shows: 'auto' follows detection
export type DeviceSlotPreference = DeviceSlotChoice | 'auto';

const PREFERENCES: DeviceSlotPreference[] = ['auto', 'mobile', 'desktop', 'off'];
// Below this shorter screen side, a touch device counts as a phone
const MOBILE_MAX_SIDE = 900;

export const detectDeviceSlot = (): DeviceSlot => {
  if (typeof window === 'undefined') return 'desktop';
  const coarse = window.matchMedia?.('(pointer: coarse)').matches ?? false;
  return coarse && Math.min(window.screen.width, window.screen.height) < MOBILE_MAX_SIDE ? 'mobile' : 'desktop';
};

export const getDeviceSlotPreference = (): DeviceSlotPreference => {
  const stored = readLocalStorage<unknown>(READER_DEVICE_SLOT_KEY, 'auto');
  return PREFERENCES.includes(stored as DeviceSlotPreference) ? (stored as DeviceSlotPreference) : 'auto';
};

export const setDeviceSlotPreference = (preference: DeviceSlotPreference): void => {
  if (preference === 'auto') {
    try {
      localStorage.removeItem(READER_DEVICE_SLOT_KEY);
    } catch {
      // storage unavailable: detection is used anyway
    }
    return;
  }
  writeLocalStorage(READER_DEVICE_SLOT_KEY, preference);
};

export const getDeviceSlotChoice = (): DeviceSlotChoice => {
  const preference = getDeviceSlotPreference();
  return preference === 'auto' ? detectDeviceSlot() : preference;
};
