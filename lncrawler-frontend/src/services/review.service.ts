import api from './api';

export interface Review {
  id: string;
  novel_title: string;
  novel_slug: string;
  user: {
    id: string;
    username: string;
    profile_pic?: string;
  };
  title: string;
  content: string;
  rating: number;
  created_at: string;
  updated_at: string;
  reaction_count: number;
  reactions: ReviewReaction[];
  current_user_reaction: ReviewReaction | null;
}

export interface ReviewReaction {
  id: string;
  reaction: string;
}

export interface CreateReviewData {
  title: string;
  content: string;
  rating: number;
}

export interface ReviewsResponse {
  reviews: Review[];
  pagination: {
    current_page: number;
    total_pages: number;
    total_reviews: number;
    has_next: boolean;
    has_previous: boolean;
  };
}

export const reviewService = {
  // Get reviews for a novel
  getNovelReviews: async (novelSlug: string, page = 1, pageSize = 4): Promise<ReviewsResponse> => {
    const response = await api.get(`/novels/${novelSlug}/reviews/`, {
      params: { page, page_size: pageSize }
    });
    return response.data;
  },

  // Add a review for a novel
  addReview: async (novelSlug: string, reviewData: CreateReviewData): Promise<Review> => {
    const response = await api.post(`/novels/${novelSlug}/reviews/add/`, reviewData);
    return response.data;
  },

  // Get, update, or delete a specific review
  getReview: async (reviewId: string): Promise<Review> => {
    const response = await api.get(`/reviews/${reviewId}/`);
    return response.data;
  },

  updateReview: async (reviewId: string, reviewData: Partial<CreateReviewData>): Promise<Review> => {
    const response = await api.put(`/reviews/${reviewId}/`, reviewData);
    return response.data;
  },

  deleteReview: async (reviewId: string): Promise<void> => {
    await api.delete(`/reviews/${reviewId}/`);
  },

  // Add a reaction to a review
  addReaction: async (reviewId: string, reaction: string): Promise<{ message: string }> => {
    const response = await api.post(`/reviews/${reviewId}/reactions/add/`, { reaction });
    return response.data;
  },

  // Remove a reaction from a review
  removeReaction: async (reviewId: string): Promise<{ message: string }> => {
    const response = await api.delete(`/reviews/${reviewId}/reactions/remove/`);
    return response.data;
  },

  // Get user's reviews
  getUserReviews: async (page = 1, pageSize = 20): Promise<ReviewsResponse> => {
    const response = await api.get(`/users/reviews/`, {
      params: { page, page_size: pageSize }
    });
    return response.data;
  }
};
