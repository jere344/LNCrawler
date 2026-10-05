import api from './api';
import { ChatPageResponse, ChatMessagePayload } from '@models/chat_types';

export const chatService = {
  listChat: async (page = 1, pageSize = 100): Promise<ChatPageResponse> => {
    const response = await api.get('/chat/', { params: { page, page_size: pageSize } });
    return response.data;
  },

  addChatMessage: async (data: ChatMessagePayload) => {
    const response = await api.post('/chat/add/', data);
    return response.data;
  },
};
