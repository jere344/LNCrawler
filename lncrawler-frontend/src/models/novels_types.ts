import { ReadingList } from './readinglist_types';

export interface Novel {
  id: string;
  title: string;
  slug: string;
  sources_count: number;
  avg_rating: number | null;
  rating_count: number;
  total_views?: number;
  weekly_views?: number;
  prefered_source: NovelFromSource | null;
  languages: string[];
  is_bookmarked?: boolean | null;
  comment_count: number;
  reading_history?: DetailedReadingHistory | null;
  similar_novels?: SimilarNovel[];
}

export interface NovelListResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: Novel[];
  recommendations?: Novel[];
}

export interface NovelFromSource {
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  source_slug: string;
  cover_path: string | null;
  authors: string[];
  tags: string[];
  language: string;
  status: string;
  synopsis: string;
  chapters_count: number;
  volumes_count: number;
  last_chapter_update: string;
  upvotes: number;
  downvotes: number;
  vote_score: number;
  user_vote: 'up' | 'down' | null;
  novel_id: string;
  novel_slug: string;
  novel_title: string;
  cover_url: string | null;
  cover_min_url: string | null;
  overview_url: string | null;
  latest_available_chapter: Chapter | null;
  reading_history?: ReadingHistory | null;
}

export interface NovelDetail {
  id: string;
  title: string;
  slug: string;
  sources: NovelFromSource[];
  created_at: string;
  updated_at: string;
  avg_rating: number | null;
  rating_count: number;
  user_rating: number | null;
  total_views: number;
  weekly_views: number;
  prefered_source: NovelFromSource | null;
  is_bookmarked?: boolean | null;
  comment_count: number;
  reading_history?: DetailedReadingHistory | null;
  similar_novels?: SimilarNovel[];
  reading_lists?: ReadingList[];
}

export interface SimilarNovel extends Novel {
  similarity: number;
}

export interface NovelFeaturedResponse {
  novel: Novel;
  description: string;
  featured_since: string;
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
  prev_chapter?: number | null;
  next_chapter?: number | null;
  images_path?: string;
  source_overview_image_url?: string | null;
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
  source_overview_image_url?: string | null;
}

export interface ReadingHistory {
  id: string;
  last_read_chapter : Chapter;
  last_read_at: string;
}

export interface DetailedReadingHistory {
  id: string;
  last_read_chapter : Chapter;
  last_read_at: string;
  next_chapter?: Chapter;
  source_slug?: string;
  novel_slug?: string;
  source_latest_chapter?: Chapter;
}