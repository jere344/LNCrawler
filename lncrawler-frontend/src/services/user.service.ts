import api from './api';
import { LibraryFolder, NovelListResponse, ReadingHistory } from '@models/novels_types';

export type LibrarySort = 'custom' | 'title' | 'date_added' | 'rating';

export interface LibraryQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  folder?: string;
  sort?: LibrarySort;
}

const buildLibraryParams = (query: LibraryQuery = {}) => ({
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
  listBookmarkedNovels: async (query: LibraryQuery = {}): Promise<NovelListResponse> => {
    const response = await api.get(`/users/bookmarks/novels/`, {
      params: buildLibraryParams(query),
    });
    return response.data;
  },

  // Library folders
  getLibraryFolders: async (): Promise<LibraryFolder[]> => {
    const response = await api.get(`/users/library/folders/`);
    return response.data;
  },

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

  // Mark a chapter as read
  markChapterAsRead: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number
  ): Promise<ReadingHistory> => {
    const response = await api.post(
      `/users/reading-history/mark-read/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/`
    );
    return response.data;
  },

  // List reading history
  listReadingHistory: async (page = 1, pageSize = 24) => {
    const response = await api.get(`/users/reading-history/?page=${page}&page_size=${pageSize}`);
    return response.data;
  },

  // Delete a reading history entry
  deleteReadingHistory: async (historyId: string) => {
    const response = await api.delete(`/users/reading-history/${historyId}/delete/`);
    return response.data;
  },
};

export { userService };
