import api from './api';
import { ReadingList, ReadingListResponse, ReadingListItem, ReadingListCollaborator } from '@models/readinglist_types';
import { User } from '@models/user_types';

const readingListService = {
  // Get all reading lists with pagination and search
  getAllReadingLists: async (page = 1, pageSize = 20, search = ''): Promise<ReadingListResponse> => {
    const params = new URLSearchParams();
    params.append('page', page.toString());
    params.append('page_size', pageSize.toString());
    if (search) params.append('search', search);

    const response = await api.get(`/reading-lists/?${params.toString()}`);
    return response.data;
  },

  // Get reading lists for a specific user
  getUserReadingLists: async (page = 1, pageSize = 20): Promise<ReadingListResponse> => {
    const params = new URLSearchParams();
    params.append('page', page.toString());
    params.append('page_size', pageSize.toString());

    const response = await api.get(`/users/reading-lists/?${params.toString()}`);
    return response.data;
  },

  // Get a single reading list by ID with all novel items
  getReadingListDetail: async (listId: string): Promise<ReadingList> => {
    const response = await api.get(`/reading-lists/${listId}/`);
    return response.data;
  },

  // Create a new reading list
  createReadingList: async (title: string, description?: string, isPublic = true): Promise<ReadingList> => {
    const response = await api.post('/reading-lists/create/', {
      title,
      description,
      is_public: isPublic
    });
    return response.data;
  },

  // Update an existing reading list
  updateReadingList: async (listId: string, data: { title?: string, description?: string, is_public?: boolean }): Promise<ReadingList> => {
    const response = await api.put(`/reading-lists/${listId}/update/`, data);
    return response.data;
  },

  // Delete a reading list
  deleteReadingList: async (listId: string): Promise<void> => {
    await api.delete(`/reading-lists/${listId}/delete/`);
  },

  // Add a novel to a reading list
  addNovelToList: async (listId: string, novelId: string, note?: string): Promise<ReadingListItem> => {
    const response = await api.post(`/reading-lists/${listId}/add-novel/`, {
      novel_id: novelId,
      note
    });
    return response.data;
  },

  // Update a novel item in a reading list
  updateListItem: async (listId: string, itemId: string, data: { note?: string, position?: number }): Promise<ReadingListItem> => {
    const response = await api.put(`/reading-lists/${listId}/items/${itemId}/update/`, data);
    return response.data;
  },

  // Remove a novel from a reading list
  removeNovelFromList: async (listId: string, itemId: string): Promise<void> => {
    await api.delete(`/reading-lists/${listId}/items/${itemId}/remove/`);
  },

  // Reorder items in a reading list
  reorderListItems: async (listId: string, items: { id: string, position: number }[]): Promise<ReadingList> => {
    const response = await api.post(`/reading-lists/${listId}/reorder/`, items);
    return response.data;
  },

  // Search users by username (for adding collaborators)
  searchUsers: async (query: string): Promise<User[]> => {
    const response = await api.get(`/users/search/?q=${encodeURIComponent(query)}`);
    return response.data;
  },

  // Add a collaborator to a reading list (owner only)
  addCollaborator: async (listId: string, data: { username?: string, user_id?: string, role: 'editor' | 'reader' }): Promise<ReadingListCollaborator> => {
    const response = await api.post(`/reading-lists/${listId}/collaborators/`, data);
    return response.data;
  },

  // Change a collaborator's role (owner only)
  updateCollaborator: async (listId: string, collaboratorId: string, role: 'editor' | 'reader'): Promise<ReadingListCollaborator> => {
    const response = await api.put(`/reading-lists/${listId}/collaborators/${collaboratorId}/`, { role });
    return response.data;
  },

  // Remove a collaborator (owner only)
  removeCollaborator: async (listId: string, collaboratorId: string): Promise<void> => {
    await api.delete(`/reading-lists/${listId}/collaborators/${collaboratorId}/`);
  }
};

export { readingListService };
