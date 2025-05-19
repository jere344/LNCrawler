import api from './api';

// Novel service functions updated for the new URL structure
export const novelService = {
  listNovels: async (page = 1, pageSize = 24) => {
    const response = await api.get(`/novels/?page=${page}&page_size=${pageSize}`);
    return response.data;
  },
  
  // Get novel details by slug
  getNovelDetail: async (novelSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/`);
    return response.data;
  },
  
  // Get source details by slug
  getSourceDetail: async (novelSlug: string, sourceSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/`);
    return response.data;
  },
  
  // Get chapters by novel and source slugs with pagination
  getNovelChapters: async (novelSlug: string, sourceSlug: string, page = 1, pageSize = 100) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapters/`, {
      params: { page, page_size: pageSize }
    });
    return response.data;
  },
  
  // Get chapter content by number
  getChapterContent: async (novelSlug: string, sourceSlug: string, chapterNumber: number) => {
    const response = await api.get(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/`);
    return response.data;
  },

  voteSource : async (novelSlug: string, sourceSlug: string, voteType: 'up' | 'down') => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/vote/`, 
      { vote_type: voteType }
    );
    return response.data;
  },

  // Rate a novel (1-5 stars)
  rateNovel: async (novelSlug: string, rating: number) => {
    const response = await api.post(`/novels/${novelSlug}/rate/`, { rating });
    return response.data;
  },

  // Get comments for a novel
  getNovelComments: async (novelSlug: string) => {
    const response = await api.get(`/novels/${novelSlug}/comments/`);
    return response.data;
  },
  
  // Add a comment to a novel
  addNovelComment: async (novelSlug: string, commentData: { 
    author_name: string; 
    message: string; 
    contains_spoiler: boolean;
    parent_id?: string; // Optional parent ID for replies
  }) => {
    const response = await api.post(
      `/novels/${novelSlug}/comments/add/`,
      commentData
    );
    return response.data;
  },
  
  // Get comments for a chapter
  getChapterComments: async (novelSlug: string, sourceSlug: string, chapterNumber: number) => {
    const response = await api.get(
      `/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/`
    );
    return response.data;
  },
  
  // Add a comment to a chapter
  addChapterComment: async (
    novelSlug: string,
    sourceSlug: string,
    chapterNumber: number,
    commentData: { 
      author_name: string; 
      message: string; 
      contains_spoiler: boolean;
      parent_id?: string; // Optional parent ID for replies
    }
  ) => {
    const response = await api.post(
      `/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}/comments/add/`,
      commentData
    );
    return response.data;
  },

  searchNovels: async (params: {
    query?: string;
    page?: number;
    page_size?: number;
    genre?: string[];
    tag?: string[];
    author?: string[];
    status?: string;
    language?: string;
    min_rating?: number;
    sort_by?: 'title' | 'rating' | 'date_added' | 'popularity' | 'trending' | 'last_updated';
    sort_order?: 'asc' | 'desc';
  }) => {
    // Build query string
    const queryParams = new URLSearchParams();
    
    if (params.query) queryParams.append('query', params.query);
    if (params.page) queryParams.append('page', params.page.toString());
    if (params.page_size) queryParams.append('page_size', params.page_size.toString());
    if (params.status) queryParams.append('status', params.status);
    if (params.language) queryParams.append('language', params.language);
    if (params.min_rating) queryParams.append('min_rating', params.min_rating.toString());
    if (params.sort_by) queryParams.append('sort_by', params.sort_by);
    if (params.sort_order) queryParams.append('sort_order', params.sort_order);
    
    // Handle array parameters
    if (params.genre && params.genre.length) {
      params.genre.forEach(genre => queryParams.append('genre', genre));
    }
    
    if (params.tag && params.tag.length) {
      params.tag.forEach(tag => queryParams.append('tag', tag));
    }
    
    if (params.author && params.author.length) {
      params.author.forEach(author => queryParams.append('author', author));
    }
    
    const response = await api.get(`/novels/search/?${queryParams}`);
    return response.data;
  },

  // Add this function to your novelService object
  getAutocompleteSuggestions: async (type: 'genre' | 'tag' | 'author', query: string): Promise<{ name: string; count: number }[]> => {
    const response = await api.get(`/novels/autocomplete/`, {
      params: {
        type,
        query,
        limit: 10
      }
    });
    return response.data;
  },

  // Get a random featured novel
  getRandomFeaturedNovel: async () => {
    const response = await api.get('/novels/featured/random/');
    return response.data;
  },
};
