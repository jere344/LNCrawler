export interface SourceDetail {
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  source_slug: string;
  cover_url: string | null;
  authors: string[];
  genres: string[];
  tags: string[];
  language: string;
  status: string;
  synopsis: string;
  chapters_count: number;
  volumes_count: number;
  last_updated: string;
  novel_id: string;
  novel_slug: string;
  novel_title: string;
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user_vote: 'up' | 'down' | null;
}

export interface Novel {
  id: string;
  title: string;
  slug: string;
  cover_url: string | null;
  sources_count: number;
  total_chapters: number;
  avg_rating: number | null;
  rating_count: number;
}

export interface NovelListResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: Novel[];
}

export interface NovelSource {
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  source_slug: string;
  cover_url: string | null;
  authors: string[];
  genres: string[];
  tags: string[];
  language: string;
  status: string;
  synopsis: string;
  chapters_count: number;
  volumes_count: number;
  last_updated: string;
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user_vote: 'up' | 'down' | null;
}

export interface NovelDetail {
  id: string;
  title: string;
  slug: string;
  sources: NovelSource[];
  created_at: string;
  updated_at: string;
  avg_rating: number | null;
  rating_count: number;
  user_rating: number | null;
}

export interface ChapterContent {
  id: string;
  chapter_id: number;
  title: string;
  novel_title: string;
  novel_id: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  body: string;
  prev_chapter?: { chapter_id: number } | null;
  next_chapter?: { chapter_id: number } | null;
}

export interface Chapter {
  id: string;
  chapter_id: number;
  title: string;
  url: string;
  volume: number;
  volume_title: string | null;
  has_content: boolean;
}

export interface ChapterListResponse {
  novel_id: string;
  novel_title: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  chapters: Chapter[];
}
