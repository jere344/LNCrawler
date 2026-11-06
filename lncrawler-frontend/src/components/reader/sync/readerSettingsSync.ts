import { READER_SYNC_KEY, readLocalStorage, writeLocalStorage } from '@utils/storage';
import readerSettingsService, {
  ReaderSettingsConflict,
  type RemoteReaderSettings,
} from '@services/readerSettings.service';
import {
  STORAGE_VERSION,
  applyRemoteReaderSettings,
  baseDefaults,
  buildReaderSettings,
  getReaderSettings,
  subscribeReaderSettingsChanges,
} from '../readerSettingsStore';
import { getDeviceSlotChoice, type DeviceSlot, type DeviceSlotChoice } from './deviceSlot';
import { mergeThreeWay, resolveInitial, sameSettings, type RemoteState, type SyncMeta } from './syncLogic';

export type SyncStatus =
  | 'signed-out'
  | 'off'
  // Waiting for the server: nothing is sent until it has answered once
  | 'pending'
  | 'syncing'
  | 'synced'
  | 'error'
  // The user has to pick between this device's settings and the saved ones
  | 'needs-choice';

export interface SyncSnapshot {
  status: SyncStatus;
  slot: DeviceSlotChoice;
  // When the saved settings offered in 'needs-choice' were last changed
  remoteUpdatedAt: string | null;
}

const PUSH_DELAY_MS = 2000;
// A tab coming back into view checks the server again, at most this often
const PULL_INTERVAL_MS = 30_000;
const RETRY_DELAY_MS = 30_000;

let userId: string | null = null;
let slot: DeviceSlotChoice = 'off';
// Bumped on every start and stop, so answers for an older run are dropped
let generation = 0;
// True once the server has answered and the first decision is made: until then nothing is sent
let resolved = false;
// Settings with a newer schema than this client: shown, never sent back
let readOnly = false;
let pendingRemote: RemoteReaderSettings | null = null;
let pushTimer: ReturnType<typeof setTimeout> | undefined;
let pushing = false;
let pushAgain = false;
let lastPull = 0;
let unsubscribeChanges: (() => void) | null = null;

let snapshot: SyncSnapshot = { status: 'signed-out', slot: 'off', remoteUpdatedAt: null };
const listeners = new Set<() => void>();

const setStatus = (status: SyncStatus): void => {
  snapshot = { status, slot, remoteUpdatedAt: status === 'needs-choice' ? (pendingRemote?.updated_at ?? null) : null };
  listeners.forEach((listener) => listener());
};

export const getReaderSyncSnapshot = (): SyncSnapshot => snapshot;

export const subscribeReaderSync = (listener: () => void): (() => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

// The stored meta, only when it belongs to the current user and device type
const readMeta = (): SyncMeta | null => {
  const meta = readLocalStorage<SyncMeta | null>(READER_SYNC_KEY, null);
  return meta && meta.userId === userId && meta.slot === slot ? meta : null;
};

const writeMeta = (fields: Pick<SyncMeta, 'baseRevision' | 'base' | 'dirty'>): void => {
  if (!userId) return;
  writeLocalStorage(READER_SYNC_KEY, { userId, slot, ...fields });
};

const clearMeta = (): void => {
  try {
    localStorage.removeItem(READER_SYNC_KEY);
  } catch {
    // storage unavailable: nothing was stored either
  }
};

const toRemoteState = (remote: RemoteReaderSettings): RemoteState => ({
  settings: buildReaderSettings(remote.data),
  revision: remote.revision,
});

const syncing = (): boolean => userId !== null && slot !== 'off';

const applyRemote = (remote: RemoteReaderSettings): void => {
  readOnly = remote.schema_version > STORAGE_VERSION;
  applyRemoteReaderSettings(remote.data);
  writeMeta({ baseRevision: remote.revision, base: getReaderSettings(), dirty: false });
};

const schedulePush = (delay = PUSH_DELAY_MS): void => {
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => void push(), delay);
};

const push = async (retried = false): Promise<void> => {
  clearTimeout(pushTimer);
  if (!syncing() || !resolved || readOnly) return;
  if (pushing) {
    pushAgain = true;
    return;
  }
  const meta = readMeta();
  if (!meta?.dirty) return;

  const run = generation;
  const sent = getReaderSettings();
  pushing = true;
  setStatus('syncing');
  try {
    const saved = await readerSettingsService.putSlot(
      slot as DeviceSlot,
      sent as unknown as Record<string, unknown>,
      STORAGE_VERSION,
      meta.baseRevision,
    );
    if (run !== generation) return;
    // Changes made while the request was out stay dirty and go in the next push
    const changedSince = !sameSettings(sent, getReaderSettings());
    writeMeta({ baseRevision: saved.revision, base: sent, dirty: changedSince });
    setStatus('synced');
    if (changedSince) pushAgain = true;
  } catch (error) {
    if (run !== generation) return;
    if (!(error instanceof ReaderSettingsConflict) || retried) {
      setStatus(error instanceof ReaderSettingsConflict ? 'error' : 'pending');
      // Offline or server error: the changes stay dirty and are sent again later
      if (!(error instanceof ReaderSettingsConflict)) schedulePush(RETRY_DELAY_MS);
      return;
    }
    // Another device of this type saved first: merge onto its copy and try once more
    const current = error.current;
    if (!current) {
      writeMeta({ baseRevision: null, base: meta.base, dirty: true });
    } else {
      const remote = toRemoteState(current);
      const merged = mergeThreeWay(meta.base ?? baseDefaults(), getReaderSettings(), remote.settings);
      readOnly = current.schema_version > STORAGE_VERSION;
      applyRemoteReaderSettings(merged);
      writeMeta({ baseRevision: remote.revision, base: remote.settings, dirty: true });
      if (readOnly) {
        setStatus('synced');
        return;
      }
    }
    pushing = false;
    await push(true);
    return;
  } finally {
    if (run === generation) pushing = false;
  }
  if (pushAgain) {
    pushAgain = false;
    schedulePush();
  }
};

// Reads the server copy and makes the first decision. Safe to call again: later calls pick up other devices' changes.
const pull = async (): Promise<void> => {
  if (!syncing() || pushing) return;
  const run = generation;
  lastPull = Date.now();
  if (snapshot.status !== 'needs-choice') setStatus(resolved ? 'syncing' : 'pending');

  let remote: RemoteReaderSettings | null;
  try {
    remote = await readerSettingsService.getSlot(slot as DeviceSlot);
  } catch {
    if (run === generation) setStatus(resolved ? 'error' : 'pending');
    return;
  }
  // A push that finished while the request was out is newer than this answer
  if (run !== generation || pushing) return;

  const meta = readMeta();
  if (remote && meta?.baseRevision != null && remote.revision < meta.baseRevision) return;
  const resolution = resolveInitial(getReaderSettings(), baseDefaults(), meta, remote && toRemoteState(remote));
  readOnly = !!remote && remote.schema_version > STORAGE_VERSION;

  switch (resolution.kind) {
    case 'ask':
      pendingRemote = remote;
      setStatus('needs-choice');
      return;
    case 'apply':
      applyRemote(remote!);
      break;
    case 'none':
      if (!meta) {
        writeMeta({ baseRevision: remote?.revision ?? null, base: remote ? getReaderSettings() : null, dirty: false });
      }
      break;
    case 'push':
      writeMeta({ baseRevision: resolution.baseRevision, base: meta?.base ?? null, dirty: true });
      break;
    case 'merge': {
      const remoteState = toRemoteState(remote!);
      applyRemoteReaderSettings(resolution.settings);
      writeMeta({ baseRevision: remoteState.revision, base: remoteState.settings, dirty: true });
      break;
    }
  }
  resolved = true;
  pendingRemote = null;
  setStatus('synced');
  if (resolution.kind === 'push' || resolution.kind === 'merge') await push();
};

// A change made on this device. Before the first decision it only marks known settings as dirty.
const onLocalChange = (): void => {
  if (!syncing()) return;
  const meta = readMeta();
  if (meta && !meta.dirty) writeMeta({ ...meta, dirty: true });
  if (resolved) schedulePush();
};

const onVisibility = (): void => {
  if (!syncing()) return;
  if (document.visibilityState === 'hidden') {
    if (resolved) void push();
  } else if (Date.now() - lastPull > PULL_INTERVAL_MS || !resolved) {
    void pull();
  }
};

const onOnline = (): void => {
  if (!syncing()) return;
  if (resolved) void push();
  else void pull();
};

let installed = false;
const install = (): void => {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  document.addEventListener('visibilitychange', onVisibility);
  window.addEventListener('online', onOnline);
};

const reset = (): void => {
  generation += 1;
  clearTimeout(pushTimer);
  resolved = false;
  readOnly = false;
  pendingRemote = null;
  pushing = false;
  pushAgain = false;
  lastPull = 0;
};

export const startReaderSync = (id: string): void => {
  if (id === userId && slot === getDeviceSlotChoice()) return;
  reset();
  userId = id;
  slot = getDeviceSlotChoice();
  if (slot === 'off') {
    setStatus('off');
    return;
  }
  install();
  unsubscribeChanges ??= subscribeReaderSettingsChanges(onLocalChange);
  void pull();
};

// Signed out: settings stay on the device, but they are no longer tied to that account
export const stopReaderSync = ({ forget }: { forget: boolean }): void => {
  reset();
  userId = null;
  slot = 'off';
  if (forget) clearMeta();
  setStatus('signed-out');
};

// The device type changed on the settings page
export const restartReaderSync = (): void => {
  const id = userId;
  if (!id) return;
  userId = null;
  startReaderSync(id);
};

// Answers to 'needs-choice'
export const chooseSavedReaderSettings = (): void => {
  if (!pendingRemote) return;
  applyRemote(pendingRemote);
  resolved = true;
  pendingRemote = null;
  setStatus('synced');
};

export const chooseDeviceReaderSettings = (): void => {
  if (!pendingRemote) return;
  const remote = toRemoteState(pendingRemote);
  readOnly = pendingRemote.schema_version > STORAGE_VERSION;
  writeMeta({ baseRevision: remote.revision, base: remote.settings, dirty: true });
  resolved = true;
  pendingRemote = null;
  setStatus('synced');
  void push();
};
