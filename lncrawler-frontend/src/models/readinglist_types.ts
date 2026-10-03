import { Novel } from './novels_types';
import { User } from './user_types';

export interface ReadingListItem {
  id: string;
  novel: Novel;
  note?: string;
  position: number;
  added_at: string;
}

export type ReadingListRole = 'owner' | 'editor' | 'reader';

export interface ReadingListCollaborator {
  id: string;
  user: User;
  role: 'editor' | 'reader';
  created_at: string;
}

export interface ReadingList {
  id: string;
  title: string;
  description?: string;
  is_public: boolean;
  user: User;
  user_role?: ReadingListRole | null;
  collaborators?: ReadingListCollaborator[];
  items_count?: number;
  created_at: string;
  updated_at: string;
  items?: ReadingListItem[];
  first_item?: ReadingListItem;
  items_names?: string[];
}

export interface ReadingListResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: ReadingList[];
}
