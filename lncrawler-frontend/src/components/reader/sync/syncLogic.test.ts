import { describe, it, expect } from 'vitest';
import { defaultSettings } from '../readerDefaults';
import type { ReaderSettings } from '../readerSettingsSchema';
import { mergeThreeWay, resolveInitial, sameSettings, type RemoteState, type SyncMeta } from './syncLogic';

const edited: ReaderSettings = { ...defaultSettings, fontSize: defaultSettings.fontSize + 2 };
const remoteEdited: ReaderSettings = { ...defaultSettings, margin: defaultSettings.margin + 4 };

const remoteAt = (settings: ReaderSettings, revision = 3): RemoteState => ({ settings, revision });

const metaWith = (fields: Partial<SyncMeta>): SyncMeta => ({
  userId: 'u1',
  slot: 'desktop',
  baseRevision: 3,
  base: defaultSettings,
  dirty: false,
  ...fields,
});

describe('resolveInitial without a server copy', () => {
  it('does nothing when local is untouched', () => {
    expect(resolveInitial(defaultSettings, defaultSettings, null, null)).toEqual({ kind: 'none' });
  });

  it('pushes edited settings with no base revision', () => {
    expect(resolveInitial(edited, defaultSettings, null, null)).toEqual({ kind: 'push', baseRevision: null });
  });

  it('pushes untouched settings that are still marked dirty', () => {
    const meta = metaWith({ baseRevision: null, base: null, dirty: true });

    expect(resolveInitial(defaultSettings, defaultSettings, meta, null)).toEqual({ kind: 'push', baseRevision: null });
  });
});

describe('resolveInitial with a server copy and no meta', () => {
  // A fresh device on defaults must never overwrite the saved settings
  it('applies the server copy when local is untouched', () => {
    expect(resolveInitial(defaultSettings, defaultSettings, null, remoteAt(remoteEdited))).toEqual({ kind: 'apply' });
  });

  it('applies the server copy when local already equals it', () => {
    expect(resolveInitial(edited, defaultSettings, null, remoteAt(edited))).toEqual({ kind: 'apply' });
  });

  it('asks the user when local is edited and differs from the server copy', () => {
    expect(resolveInitial(edited, defaultSettings, null, remoteAt(remoteEdited))).toEqual({ kind: 'ask' });
  });
});

describe('resolveInitial when meta matches the server revision', () => {
  it('pushes dirty changes on that revision', () => {
    const meta = metaWith({ baseRevision: 3, dirty: true });

    expect(resolveInitial(edited, defaultSettings, meta, remoteAt(defaultSettings, 3))).toEqual({
      kind: 'push',
      baseRevision: 3,
    });
  });

  it('does nothing when clean', () => {
    const meta = metaWith({ baseRevision: 3, dirty: false });

    expect(resolveInitial(defaultSettings, defaultSettings, meta, remoteAt(defaultSettings, 3))).toEqual({ kind: 'none' });
  });
});

describe('resolveInitial when the server moved on', () => {
  it('applies the server copy when local has no changes', () => {
    const meta = metaWith({ baseRevision: 2, dirty: false });

    expect(resolveInitial(defaultSettings, defaultSettings, meta, remoteAt(remoteEdited, 3))).toEqual({ kind: 'apply' });
  });

  it('merges when local has changes: local keys win, the others take the server values', () => {
    const meta = metaWith({ baseRevision: 2, base: defaultSettings, dirty: true });

    expect(resolveInitial(edited, defaultSettings, meta, remoteAt(remoteEdited, 3))).toEqual({
      kind: 'merge',
      settings: { ...defaultSettings, fontSize: edited.fontSize, margin: remoteEdited.margin },
    });
  });
});

describe('mergeThreeWay', () => {
  it('keeps a key changed locally', () => {
    const merged = mergeThreeWay(defaultSettings, edited, defaultSettings);

    expect(merged.fontSize).toBe(edited.fontSize);
  });

  it('takes a key changed only on the server', () => {
    const merged = mergeThreeWay(defaultSettings, defaultSettings, remoteEdited);

    expect(merged.margin).toBe(remoteEdited.margin);
  });

  it('keeps the local value when both sides changed the same key', () => {
    const remoteSide: ReaderSettings = { ...defaultSettings, fontSize: defaultSettings.fontSize + 6 };

    expect(mergeThreeWay(defaultSettings, edited, remoteSide).fontSize).toBe(edited.fontSize);
  });
});

describe('sameSettings', () => {
  it('is true for equal values', () => {
    expect(sameSettings({ ...defaultSettings }, defaultSettings)).toBe(true);
  });

  it('is false when one value differs', () => {
    expect(sameSettings(edited, defaultSettings)).toBe(false);
  });
});

describe('resolveInitial with changes made while sync was off', () => {
  // The dirty flag is not set while sync is off or signed out, so the settings differ from the base without it
  it('merges instead of applying the server copy when the server moved on', () => {
    const resolution = resolveInitial(edited, defaultSettings, metaWith({ baseRevision: 2 }), remoteAt(remoteEdited, 3));
    expect(resolution).toEqual({ kind: 'merge', settings: { ...remoteEdited, fontSize: edited.fontSize } });
  });

  it('pushes them when the server did not move', () => {
    expect(resolveInitial(edited, defaultSettings, metaWith({}), remoteAt(defaultSettings, 3))).toEqual({
      kind: 'push',
      baseRevision: 3,
    });
  });
});
