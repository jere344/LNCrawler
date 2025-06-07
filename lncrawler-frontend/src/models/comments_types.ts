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
}
