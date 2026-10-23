import api from './api';
import { FriendRequest } from '@models/user_types';

const friendService = {
  // Friend requests: incoming (default) or outgoing
  listRequests: async (direction: 'incoming' | 'outgoing' = 'incoming'): Promise<FriendRequest[]> => {
    const response = await api.get('/friends/requests/', { params: { type: direction } });
    return response.data;
  },

  sendRequest: async (username: string): Promise<{ status: string; friendship_id: string }> => {
    const response = await api.post(`/friends/requests/${encodeURIComponent(username)}/send/`);
    return response.data;
  },

  respond: async (friendshipId: string, action: 'accept' | 'decline'): Promise<void> => {
    await api.post(`/friends/requests/${friendshipId}/respond/`, { action });
  },

  removeFriend: async (username: string): Promise<void> => {
    await api.delete(`/friends/${encodeURIComponent(username)}/remove/`);
  },
};

export { friendService };
