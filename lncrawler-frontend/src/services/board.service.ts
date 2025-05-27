import api from './api';

export const boardService = {
  listBoards: async () => {
    const response = await api.get('/boards/');
    return response.data;
  },
  
  getBoardDetail: async (boardSlug: string) => {
    const response = await api.get(`/boards/${boardSlug}/`);
    return response.data;
  },
  
  getBoardComments: async (boardSlug: string) => {
    const response = await api.get(`/boards/${boardSlug}/comments/`);
    return response.data;
  },
  
  addBoardComment: async (boardSlug: string, commentData: {
    author_name: string;
    message: string;
    contains_spoiler: boolean;
    parent_id?: string;
  }) => {
    const response = await api.post(`/boards/${boardSlug}/comments/add/`, commentData);
    return response.data;
  },
};
