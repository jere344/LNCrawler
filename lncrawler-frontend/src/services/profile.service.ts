import api from './api';
import { LibraryFolder, Novel } from '@models/novels_types';
import { User, PublicProfile } from '@models/user_types';
import { ReadingListResponse } from '@models/readinglist_types';
import { Review } from './review.service';
import type { Comment } from '@models/comments_types';

export interface PublicLibraryQuery {
  page?: number;
  pageSize?: number;
  search?: string;
  folder?: string;
  sort?: string;
}

const profileService = {
  // Public profile header (bio, banner, socials, gated stats/genres/reads)
  getPublicProfile: async (username: string): Promise<PublicProfile> => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/`);
    return response.data;
  },

  // A user's public library (bookmarks), read-only mirror
  getUserLibrary: async (username: string, query: PublicLibraryQuery = {}) => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/library/`, {
      params: {
        page: query.page ?? 1,
        page_size: query.pageSize ?? 24,
        search: query.search || undefined,
        folder: query.folder || undefined,
        sort: query.sort || undefined,
      },
    });
    return response.data as {
      count: number;
      total_pages: number;
      current_page: number;
      results: Novel[];
      folders?: LibraryFolder[];
      sort?: string;
    };
  },

  // A user's reviews
  getUserReviews: async (username: string, page = 1, pageSize = 20) => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/reviews/`, {
      params: { page, page_size: pageSize },
    });
    return response.data as {
      reviews: Review[];
      pagination: {
        current_page: number;
        total_pages: number;
        total_reviews: number;
        has_next: boolean;
        has_previous: boolean;
      };
    };
  },

  // A user's comments
  getUserComments: async (username: string, page = 1, pageSize = 20) => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/comments/`, {
      params: { page, page_size: pageSize },
    });
    return response.data as {
      count: number;
      total_pages: number;
      current_page: number;
      results: Comment[];
    };
  },

  // A user's public reading lists
  getUserReadingLists: async (username: string, page = 1, pageSize = 20): Promise<ReadingListResponse> => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/reading-lists/`, {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  // A user's friends
  getUserFriends: async (username: string): Promise<User[]> => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/friends/`, {
      params: { page_size: 100 },
    });
    return response.data.results;
  },

  // Pin / unpin a novel on the current user's own profile
  pinNovel: async (novelId: string): Promise<void> => {
    await api.post(`/users/profile/pinned/${novelId}/`);
  },

  unpinNovel: async (novelId: string): Promise<void> => {
    await api.delete(`/users/profile/pinned/${novelId}/`);
  },
};

export { profileService };
