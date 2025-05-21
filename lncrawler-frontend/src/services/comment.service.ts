import api from './api';

export const commentService = {
  voteComment: async (commentId: string, voteType: 'up' | 'down') => {
    const response = await api.post(`/comments/${commentId}/vote/`, { vote_type: voteType });
    return response.data; // Expects { id, upvotes, downvotes, vote_score }
  },
  
  editComment: async (commentId: string, data: { message: string; contains_spoiler: boolean }) => {
    const response = await api.put(`/comments/${commentId}/edit/`, data);
    return response.data;
  },
};
