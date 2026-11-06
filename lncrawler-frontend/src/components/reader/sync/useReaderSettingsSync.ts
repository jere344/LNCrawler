import { useEffect, useRef, useSyncExternalStore } from 'react';
import { useAuth } from '@context/AuthContext';
import { getReaderSyncSnapshot, startReaderSync, stopReaderSync, subscribeReaderSync } from './readerSettingsSync';

// Mounted once at the app root: syncs reader settings while someone is signed in
export const useReaderSettingsSync = (): void => {
  const { user } = useAuth();
  const userId = user?.id ?? null;
  // undefined until the first run, so the signed-out state at startup is not taken for a logout
  const previous = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (userId) startReaderSync(userId);
    else stopReaderSync({ forget: previous.current != null });
    previous.current = userId;
  }, [userId]);
};

export const useReaderSyncStatus = () => useSyncExternalStore(subscribeReaderSync, getReaderSyncSnapshot);
