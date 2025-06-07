import { Novel } from './novels_types';
import { User } from './user_types';

export interface ReadingListItem {
  id: string;
  novel: Novel;
  note?: string;
  position: number;
  added_at: string;
}

export interface ReadingList {
  id: string;
  title: string;
  description?: string;
  user: User;
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
