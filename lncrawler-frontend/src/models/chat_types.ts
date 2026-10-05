import { User } from './user_types';

export interface ChatParent {
  id: string;
  author_name: string;
  message: string;
}

export interface ChatMessage {
  id: string;
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  created_at: string;
  edited: boolean;
  user: User | null;
  parent: ChatParent | null;
}

export interface ChatPageResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: ChatMessage[];
}

export interface ChatMessagePayload {
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  parent_id?: string;
}
