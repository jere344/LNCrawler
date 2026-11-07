import api, { type ApiError } from './api';
import type { DeviceSlot } from '@components/reader/sync/deviceSlot';

// The server's copy of one device type's settings
export interface RemoteReaderSettings {
  slot: DeviceSlot;
  data: Record<string, unknown>;
  schema_version: number;
  revision: number;
  updated_at: string;
}

// The server refused a write made from an outdated revision; `current` is its copy, or null when it has none
export class ReaderSettingsConflict extends Error {
  constructor(public current: RemoteReaderSettings | null) {
    super('Reader settings changed on the server');
  }
}

const statusOf = (error: unknown): number | undefined => (error as ApiError).response?.status;

const readerSettingsService = {
  // null when the server has no copy for this device type
  getSlot: async (slot: DeviceSlot): Promise<RemoteReaderSettings | null> => {
    try {
      const response = await api.get(`/users/reader-settings/${slot}/`);
      return response.data;
    } catch (error) {
      if (statusOf(error) === 404) return null;
      throw error;
    }
  },

  // baseRevision is the server revision these settings were made from, or null for a first save
  putSlot: async (
    slot: DeviceSlot,
    data: Record<string, unknown>,
    schemaVersion: number,
    baseRevision: number | null,
  ): Promise<RemoteReaderSettings> => {
    try {
      const response = await api.put(`/users/reader-settings/${slot}/`, {
        data,
        schema_version: schemaVersion,
        base_revision: baseRevision,
      });
      return response.data;
    } catch (error) {
      if (statusOf(error) === 409) {
        const current = (error as ApiError).response?.data;
        throw new ReaderSettingsConflict(current?.revision == null ? null : current);
      }
      throw error;
    }
  },
};

export default readerSettingsService;
