import api from './api';
import { NovelListResponse } from '../models/novels_types'; // Assuming NovelListResponse is appropriate

export const userService = {
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

  // List bookmarked novels
  listBookmarkedNovels: async (page = 1, pageSize = 24): Promise<NovelListResponse> => {
    const response = await api.get(`/users/bookmarks/novels/?page=${page}&page_size=${pageSize}`);
    return response.data;
  },
};
