import { useSyncExternalStore } from 'react';
import { getReaderSettings, subscribeReaderSettings } from '../readerSettingsStore';
import type { ReaderSettings } from '../readerSettingsSchema';

export const useReaderSettings = () => useSyncExternalStore(subscribeReaderSettings, getReaderSettings);

// One setting only: the component re-renders when that value changes, not on every setting
export const useReaderSetting = <K extends keyof ReaderSettings>(key: K): ReaderSettings[K] =>
  useSyncExternalStore(subscribeReaderSettings, () => getReaderSettings()[key]);
