import api from './api';
import type { Comment, CommentFormData } from '@models/comments_types';

export const commentService = {
  voteComment: async (commentId: string, voteType: 'up' | 'down') => {
    const response = await api.post(`/comments/${commentId}/vote/`, { vote_type: voteType });
    return response.data; // Expects { id, upvotes, downvotes, vote_score }
  },
  
  editComment: async (commentId: string, data: { message: string; contains_spoiler: boolean }) => {
    const response = await api.put(`/comments/${commentId}/edit/`, data);
    return response.data;
  },

  // Get every root comment of a novel, with their replies, highest score first
  getNovelComments: async (novelSlug: string): Promise<Comment[]> => {
    const response = await api.get(`/novels/${novelSlug}/comments/`);
    return response.data;
  },

  // Add a comment to a novel; the created comment is returned
  addNovelComment: async (novelSlug: string, commentData: CommentFormData): Promise<Comment> => {
    const response = await api.post(`/novels/${novelSlug}/comments/add/`, commentData);
    return response.data;
  },

  // Get every root comment of a chapter, highest score first, shared by every source with this chapter number
  getChapterComments: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number,
  ): Promise<Comment[]> => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/`);
    return response.data;
  },

  // Add a comment to a chapter; the created comment is returned
  addChapterComment: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number,
    commentData: CommentFormData,
  ): Promise<Comment> => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/add/`,
      commentData
    );
    return response.data;
  },
};
