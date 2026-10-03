import { User } from './user_types';

export interface Comment {
  id: string;
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  created_at: string;
  source_name?: string;
  type?: 'novel' | 'chapter' | 'board';
  chapter_title?: string;
  chapter_id?: number;
  source_slug?: string;
  board_name?: string;
  board_slug?: string;
  replies?: Comment[];
  has_replies?: boolean;
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user: User;
  user_vote?: 'up' | 'down';
  edited: boolean;
  target_type?: 'novel' | 'chapter' | 'board';
  target_title?: string;
  target_slug?: string;
  target_novel_slug?: string;
  target_source_slug?: string;
  target_chapter_number?: number;
}

export interface CommentFormData {
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  parent_id?: string;
}
