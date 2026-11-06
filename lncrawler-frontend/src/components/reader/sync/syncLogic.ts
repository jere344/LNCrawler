import type { ReaderSettings } from '../readerSettingsSchema';

// What this device last agreed on with the server, for one user and device type
export interface SyncMeta {
  userId: string;
  slot: string;
  // Server revision the local settings were made from; null while the server has no copy
  baseRevision: number | null;
  // The settings at that revision, the common ancestor for a merge
  base: ReaderSettings | null;
  // Local changes the server does not have yet
  dirty: boolean;
}

export interface RemoteState {
  settings: ReaderSettings;
  revision: number;
}

export type Resolution =
  // Take the server copy as it is
  | { kind: 'apply' }
  // Already in line with the server
  | { kind: 'none' }
  // Send the local settings, made from this server revision (null: the server has none)
  | { kind: 'push'; baseRevision: number | null }
  // Both sides changed: keep the merged settings, then send them
  | { kind: 'merge'; settings: ReaderSettings }
  // Never synced here, and the local settings were edited: the user picks a side
  | { kind: 'ask' };

const sameValue = (a: unknown, b: unknown): boolean => a === b || JSON.stringify(a) === JSON.stringify(b);

export const sameSettings = (a: ReaderSettings, b: ReaderSettings): boolean =>
  (Object.keys(a) as (keyof ReaderSettings)[]).every((key) => sameValue(a[key], b[key]));

// Per key: a value changed locally since `base` wins, every other key takes the server value
export const mergeThreeWay = (base: ReaderSettings, local: ReaderSettings, remote: ReaderSettings): ReaderSettings => {
  const merged = { ...remote };
  (Object.keys(local) as (keyof ReaderSettings)[]).forEach((key) => {
    if (!sameValue(local[key], base[key])) (merged as Record<string, unknown>)[key] = local[key];
  });
  return merged;
};

// First decision after reading the server copy. `meta` is null unless it belongs to this user and device type.
// A device that never synced and still has its defaults never sends anything: the server copy wins.
export const resolveInitial = (
  local: ReaderSettings,
  defaults: ReaderSettings,
  meta: SyncMeta | null,
  remote: RemoteState | null,
): Resolution => {
  const untouched = sameSettings(local, defaults);
  // Changes made while sync was off or signed out never set the flag, so the settings are compared too
  const dirty = !!meta && (meta.dirty || !sameSettings(local, meta.base ?? defaults));

  if (!remote) return untouched && !dirty ? { kind: 'none' } : { kind: 'push', baseRevision: null };

  if (!meta) {
    if (untouched || sameSettings(local, remote.settings)) return { kind: 'apply' };
    return { kind: 'ask' };
  }

  if (meta.baseRevision === remote.revision) {
    return dirty ? { kind: 'push', baseRevision: remote.revision } : { kind: 'none' };
  }

  if (!dirty) return { kind: 'apply' };
  return { kind: 'merge', settings: mergeThreeWay(meta.base ?? defaults, local, remote.settings) };
};
