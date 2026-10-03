import api from './api';
import { Novel } from '@models/novels_types';
import { User, PublicProfile } from '@models/user_types';
import { ReadingListResponse } from '@models/readinglist_types';
import { Review } from './review.service';
import type { Comment } from '@models/comments_types';

const profileService = {
  // Public profile header (bio, banner, socials, gated stats/genres/reads)
  getPublicProfile: async (username: string): Promise<PublicProfile> => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/`);
    return response.data;
  },

  // A user's public library (bookmarks)
  getUserLibrary: async (username: string, page = 1, pageSize = 20) => {
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/library/`, {
      params: { page, page_size: pageSize },
    });
    return response.data as {
      count: number;
      total_pages: number;
      current_page: number;
      results: Novel[];
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
    const response = await api.get(`/users/profile/${encodeURIComponent(username)}/friends/`);
    return response.data;
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
