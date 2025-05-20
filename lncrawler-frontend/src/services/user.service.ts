import api from './api';
import { Novel, NovelListResponse, ReadingHistory } from '@models/novels_types';

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

  // List bookmarked novels
  listBookmarkedNovels: async (page = 1, pageSize = 24): Promise<NovelListResponse> => {
    const response = await api.get(`/users/bookmarks/novels/?page=${page}&page_size=${pageSize}`);
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
