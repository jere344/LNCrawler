import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import readerSettingsService, {
  ReaderSettingsConflict,
  type RemoteReaderSettings,
} from '@services/readerSettings.service';
import { READER_DEVICE_SLOT_KEY, READER_SYNC_KEY } from '@utils/storage';
import { defaultSettings } from '../readerDefaults';

vi.mock('@services/readerSettings.service', async () => {
  const actual = await vi.importActual<typeof import('@services/readerSettings.service')>('@services/readerSettings.service');
  return {
    ...actual,
    default: { getSlot: vi.fn(), putSlot: vi.fn() },
  };
});

type Store = typeof import('../readerSettingsStore');
type Sync = typeof import('./readerSettingsSync');

const remoteCopy = (fields: Record<string, unknown>, revision = 3): RemoteReaderSettings => ({
  slot: 'desktop',
  data: { ...defaultSettings, ...fields },
  schema_version: 1,
  revision,
  updated_at: '2026-01-01T00:00:00Z',
});

// Each test gets fresh modules, so the sync state starts empty
let store: Store;
let sync: Sync;

beforeEach(async () => {
  localStorage.clear();
  localStorage.setItem(READER_DEVICE_SLOT_KEY, JSON.stringify('desktop'));
  vi.useFakeTimers();
  vi.resetModules();
  vi.mocked(readerSettingsService.getSlot).mockReset();
  vi.mocked(readerSettingsService.putSlot).mockReset();
  vi.mocked(readerSettingsService.putSlot).mockImplementation(async (slot, data) => ({
    slot,
    data,
    schema_version: 1,
    revision: 4,
    updated_at: '2026-01-01T00:00:01Z',
  }));
  store = await import('../readerSettingsStore');
  sync = await import('./readerSettingsSync');
});

afterEach(() => {
  // Stops the sync of this module instance, so its listeners cannot push in a later test
  sync.stopReaderSync({ forget: true });
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('fresh device with a server copy', () => {
  it('takes the server settings and never sends its defaults', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }));

    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();
    expect(store.getReaderSettings().fontSize).toBe(22);

    await vi.advanceTimersByTimeAsync(10_000);
    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
    expect(sync.getReaderSyncSnapshot().status).toBe('synced');
  });

  it('does not send anything when the server answers with an error', async () => {
    vi.mocked(readerSettingsService.getSlot).mockRejectedValue(new Error('network'));

    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();
    expect(sync.getReaderSyncSnapshot().status).toBe('pending');

    store.updateReaderSetting('fontSize', 24);
    await vi.advanceTimersByTimeAsync(10_000);

    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
    expect(sync.getReaderSyncSnapshot().status).toBe('pending');
  });

  it('does not send anything when the server has no copy and local is untouched', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(null);

    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();
    await vi.advanceTimersByTimeAsync(10_000);

    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
    expect(sync.getReaderSyncSnapshot().status).toBe('synced');
  });
});

describe('after the first decision', () => {
  it('sends a local change once, after the debounce, on the server revision', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }, 3));
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();

    store.updateReaderSetting('fontSize', 24);
    await vi.advanceTimersByTimeAsync(1999);
    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(1);
    expect(readerSettingsService.putSlot).toHaveBeenCalledTimes(1);
    expect(vi.mocked(readerSettingsService.putSlot).mock.calls[0][3]).toBe(3);
    expect(vi.mocked(readerSettingsService.putSlot).mock.calls[0][1]).toEqual(expect.objectContaining({ fontSize: 24 }));
    expect(sync.getReaderSyncSnapshot().status).toBe('synced');
  });

  it('does not send back the settings it just received', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }));
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();

    window.dispatchEvent(new Event('online'));
    await vi.runAllTimersAsync();

    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
  });
});

describe('edited local settings that differ from the server', () => {
  const startWithChoice = async (): Promise<void> => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }));
    store.updateReaderSetting('margin', 4);
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();
  };

  it('waits for the user without sending anything', async () => {
    await startWithChoice();

    expect(sync.getReaderSyncSnapshot().status).toBe('needs-choice');
    expect(sync.getReaderSyncSnapshot().remoteUpdatedAt).toBe('2026-01-01T00:00:00Z');
    await vi.advanceTimersByTimeAsync(10_000);
    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
  });

  it('applies the saved settings when the user keeps them, without sending', async () => {
    await startWithChoice();

    sync.chooseSavedReaderSettings();
    await vi.runAllTimersAsync();

    expect(store.getReaderSettings().fontSize).toBe(22);
    expect(store.getReaderSettings().margin).toBe(defaultSettings.margin);
    expect(sync.getReaderSyncSnapshot().status).toBe('synced');
    expect(readerSettingsService.putSlot).not.toHaveBeenCalled();
  });

  it('sends this device settings on the saved revision when the user keeps them', async () => {
    await startWithChoice();

    sync.chooseDeviceReaderSettings();
    await vi.runAllTimersAsync();

    expect(store.getReaderSettings().margin).toBe(4);
    expect(readerSettingsService.putSlot).toHaveBeenCalledTimes(1);
    expect(vi.mocked(readerSettingsService.putSlot).mock.calls[0][3]).toBe(3);
    expect(vi.mocked(readerSettingsService.putSlot).mock.calls[0][1]).toEqual(expect.objectContaining({ margin: 4 }));
  });
});

describe('conflict with another device', () => {
  it('merges onto the newer server copy and sends again on its revision', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }, 3));
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();

    // Another device of this type saved a font size change first
    const conflictCopy = remoteCopy({ fontSize: 30 }, 5);
    vi.mocked(readerSettingsService.putSlot)
      .mockRejectedValueOnce(new ReaderSettingsConflict(conflictCopy))
      .mockResolvedValueOnce(remoteCopy({ fontSize: 30, margin: 4 }, 6));

    store.updateReaderSetting('margin', 4);
    await vi.advanceTimersByTimeAsync(2000);
    await vi.runAllTimersAsync();

    const calls = vi.mocked(readerSettingsService.putSlot).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][3]).toBe(3);
    expect(calls[1][3]).toBe(conflictCopy.revision);
    expect(calls[1][1]).toEqual(expect.objectContaining({ margin: 4, fontSize: 30 }));
    expect(store.getReaderSettings().margin).toBe(4);
    expect(sync.getReaderSyncSnapshot().status).toBe('synced');
  });
});

describe('stopping the sync', () => {
  it('forgets the sync record when asked to, and reports signed out', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValue(remoteCopy({ fontSize: 22 }));
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();
    expect(localStorage.getItem(READER_SYNC_KEY)).not.toBeNull();

    sync.stopReaderSync({ forget: true });

    expect(localStorage.getItem(READER_SYNC_KEY)).toBeNull();
    expect(sync.getReaderSyncSnapshot().status).toBe('signed-out');
  });
});

describe('late server answers', () => {
  it('ignores a server copy older than the one this device just saved', async () => {
    vi.mocked(readerSettingsService.getSlot).mockResolvedValueOnce(remoteCopy({}, 3));
    sync.startReaderSync('u1');
    await vi.runAllTimersAsync();

    store.updateReaderSetting('fontSize', 24);
    await vi.advanceTimersByTimeAsync(2_000);
    expect(readerSettingsService.putSlot).toHaveBeenCalledTimes(1);

    // A check sent before that save answers with revision 3, after the save reached revision 4
    vi.mocked(readerSettingsService.getSlot).mockResolvedValueOnce(remoteCopy({}, 3));
    document.dispatchEvent(new Event('visibilitychange'));
    vi.setSystemTime(Date.now() + 60_000);
    document.dispatchEvent(new Event('visibilitychange'));
    await vi.runAllTimersAsync();

    expect(store.getReaderSettings().fontSize).toBe(24);
    expect(JSON.parse(localStorage.getItem(READER_SYNC_KEY) ?? 'null').baseRevision).toBe(4);
  });
});
