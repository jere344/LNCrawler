export interface Comment {
  id: string;
  author_name: string;
  message: string;
  contains_spoiler: boolean;
  created_at: string;
  from_other_source?: boolean;
  source_name?: string;
  type?: 'novel' | 'chapter';
  chapter_title?: string;
  chapter_id?: number;
  source_slug?: string;
  replies?: Comment[];
  has_replies?: boolean;
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user: {
    id: string;
    username: string;
    profile_pic: string;
  }
}
