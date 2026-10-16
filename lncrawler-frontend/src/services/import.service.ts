import api from './api';
import type { Novel } from '@models/novels_types';

export type NuImportMatchStatus = 'matched' | 'ambiguous' | 'unmatched';

export interface NuImportEntry {
  index: number;
  title: string;
  list_name: string;
  folder: string;
  volume: number;
  chapter: number;
  status: NuImportMatchStatus;
  novel: Novel | null;
  candidates: Novel[];
}

export interface NuImportParseResponse {
  count: number;
  entries: NuImportEntry[];
}

export interface NuImportApplyItem {
  novel_id: string;
  folder?: string;
  volume?: number;
  chapter?: number;
}

export interface NuImportApplyResponse {
  bookmarked: number;
  already_bookmarked: number;
  skipped: number;
  progress_set: number;
  folders_created: number;
}

const importService = {
  parseNovelupdatesExport: async (file: File): Promise<NuImportParseResponse> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/imports/novelupdates/parse/', formData);
    return response.data;
  },

  applyNovelupdatesImport: async (
    entries: NuImportApplyItem[]
  ): Promise<NuImportApplyResponse> => {
    const response = await api.post('/imports/novelupdates/apply/', { entries });
    return response.data;
  },
};

export { importService };
