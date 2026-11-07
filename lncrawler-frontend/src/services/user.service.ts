import api, { getCsrfToken } from './api';
import { API_BASE_URL } from './config';
import { LibraryFolder, LibraryListResponse, ReadingHistory } from '@models/novels_types';
import type { HistoryKind } from '@models/audiobook_types';

export type LibrarySort = 'custom' | 'title' | 'date_added' | 'rating';

export const LIBRARY_SORTS: LibrarySort[] = ['custom', 'title', 'date_added', 'rating'];

interface LibraryQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  folder?: string;
  sort?: LibrarySort;
  languages?: string[];
}

// Shared by the own and the public library lists. `sort` is a plain string so the public tab can pass its state as is.
export const buildLibraryParams = (query: Pick<LibraryQuery, 'page' | 'pageSize' | 'search' | 'folder'> & { sort?: string } = {}) => ({
  page: query.page ?? 1,
  page_size: query.pageSize ?? 24,
  search: query.search || undefined,
  folder: query.folder || undefined,
  sort: query.sort || undefined,
});

const userService = {
  // Bookmark a novel
  addNovelBookmark: async (novelSlug: string) => {
    const response = await api.post(`/users/bookmarks/novels/${novelSlug}/add/`);
    return response.data;
  },

  // Remove a novel bookmark
  removeNovelBookmark: async (novelSlug: string) => {
    const response = await api.delete(`/users/bookmarks/novels/${novelSlug}/remove/`);
    return response.data;
  },

  // List bookmarked novels (library) with search/folder/sort
  listBookmarkedNovels: async (query: LibraryQuery = {}): Promise<LibraryListResponse> => {
    const response = await api.get('/users/bookmarks/novels/', {
      params: { languages: query.languages, ...buildLibraryParams(query) },
    });
    return response.data;
  },

  // Library folders
  createLibraryFolder: async (name: string): Promise<LibraryFolder> => {
    const response = await api.post(`/users/library/folders/`, { name });
    return response.data;
  },

  renameLibraryFolder: async (folderId: string, name: string): Promise<LibraryFolder> => {
    const response = await api.put(`/users/library/folders/${folderId}/`, { name });
    return response.data;
  },

  deleteLibraryFolder: async (folderId: string): Promise<void> => {
    await api.delete(`/users/library/folders/${folderId}/`);
  },

  // Update a library item's note and/or folder
  updateLibraryItem: async (
    bookmarkId: string,
    data: { note?: string | null; folder?: string | null }
  ) => {
    const response = await api.patch(`/users/library/items/${bookmarkId}/`, data);
    return response.data;
  },

  // Persist the custom order of the whole library
  reorderLibrary: async (items: { id: string; position: number }[]) => {
    const response = await api.post(`/users/library/reorder/`, items);
    return response.data;
  },

  // Save the reading position: the chapter being read, and the progress through it (0..1).
  // keepalive lets the request outlive the page, for saves sent as it is left.
  saveReadingPosition: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number,
    progress: number,
    options?: { keepalive?: boolean }
  ): Promise<ReadingHistory> => {
    const path = `/users/reading-history/position/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/`;
    if (!options?.keepalive) {
      const response = await api.post(path, { progress });
      return response.data;
    }
    // The http client does not pass keepalive on, so this is a plain fetch with the same headers
    const csrfToken = getCsrfToken();
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: 'POST',
      keepalive: true,
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...api.defaults.headers.common,
        ...(csrfToken ? { 'X-CSRFToken': csrfToken } : {}),
      },
      body: JSON.stringify({ progress }),
    });
    if (!response.ok) {
      // Shaped like the http client's error, so the status can be read the same way
      throw Object.assign(new Error(`Request failed with status code ${response.status}`), {
        response: { status: response.status },
      });
    }
    return response.json();
  },

  // List reading history: read entries, listening entries, or both merged by date (`kind`)
  listReadingHistory: async (page = 1, pageSize = 24, kind: HistoryKind = 'all') => {
    const response = await api.get(`/users/reading-history/?kind=${kind}&page=${page}&page_size=${pageSize}`);
    return response.data;
  },

  // Delete a listening history entry (the audiobook progress row)
  deleteListeningHistory: async (progressId: number) => {
    const response = await api.delete(`/users/listening-history/${progressId}/delete/`);
    return response.data;
  },

  // Delete a reading history entry
  deleteReadingHistory: async (historyId: string) => {
    const response = await api.delete(`/users/reading-history/${historyId}/delete/`);
    return response.data;
  },
};

export { userService };
