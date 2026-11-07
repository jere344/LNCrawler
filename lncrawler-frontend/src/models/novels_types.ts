import { ReadingList } from './readinglist_types';
import type { CommentPreview } from './comments_types';

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
  created_at?: string;
  reading_history?: ReadingHistory | null;
  reading_source?: NovelFromSource | null;
  similar_novels?: SimilarNovel[];
  is_dmca?: boolean;
  is_adult?: boolean;
  has_audiobook?: boolean;
}

export interface LibraryFolder {
  id: string;
  name: string;
  count: number;
}

export interface NovelListResponse {
  count: number;
  total_pages: number;
  current_page: number;
  results: Novel[];
  recommendations?: Novel[];
  folders?: LibraryFolder[];
  sort?: string;
}

// The library payload (the API's 'library' profiles): only what a library card reads.
// Novel is assignable to these types, so the card helpers accept both.
export type LibrarySource = Pick<
  NovelFromSource,
  'title' | 'source_slug' | 'novel_slug' | 'novel_id' | 'cover_min_url' | 'available_chapters_count' | 'latest_available_chapter' | 'is_adult'
>;

export type LibraryReadingHistory = Pick<
  ReadingHistory,
  'source_slug' | 'source_name' | 'current_chapter' | 'position' | 'unread_chapters' | 'source_latest_chapter' | 'resume'
>;

export type LibraryNovel = Pick<Novel, 'id' | 'title' | 'slug' | 'is_adult' | 'is_dmca' | 'is_bookmarked'> & {
  prefered_source: LibrarySource | null;
  reading_source?: LibrarySource | null;
  reading_history?: LibraryReadingHistory | null;
  // The bookmark's own columns, and the owner's rating of the novel.
  bookmark_id?: string;
  note?: string | null;
  folder?: string | null;
  folder_name?: string | null;
  user_rating?: number | null;
};

export interface LibraryListResponse extends Omit<NovelListResponse, 'results'> {
  results: LibraryNovel[];
}

// What the source page can render: the full source, or the library card's preview of it (see isFullSource).
export type SourceView = NovelFromSource | LibrarySource;

export interface NovelFromSource {
  audiobook?: { slug: string; language: string; duration_s: number; is_adult?: boolean } | null;
  id: string;
  title: string;
  source_url: string;
  source_name: string;
  // Free-form edition label from the crawler (or its title); null when unknown.
  edition?: string | null;
  source_slug: string;
  has_crawler: boolean | null;
  cover_path: string | null;
  authors: string[];
  tags: string[];
  language: string;
  status: string;
  synopsis: string | null;
  chapters_count: number;
  available_chapters_count?: number;
  volumes?: NovelVolume[];
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
  first_available_chapter: Chapter | null;
  reading_history?: ReadingHistory | null;
  novelupdates_url: string | null;
  editors: string[];
  translators: string[];
  alternative_titles: string[];
  original_publisher: string | null;
  english_publisher: string | null;
  is_adult?: boolean;
  adult_tags?: string[];
}

interface NovelVolume {
  volume_id: number;
  title: string;
  start_chapter: number;
  final_chapter: number;
  chapter_count: number;
}

export interface NovelDetail {
  id: string;
  title: string;
  slug: string;
  sources: NovelFromSource[];
  avg_rating: number | null;
  rating_count: number;
  user_rating: number | null;
  total_views: number;
  weekly_views: number;
  prefered_source: NovelFromSource | null;
  is_bookmarked?: boolean | null;
  comment_count: number;
  reading_history?: ReadingHistory | null;
  similar_novels?: SimilarNovel[];
  reading_lists?: ReadingList[];
  is_dmca?: boolean;
  is_adult?: boolean;
  audiobooks?: { language: string; duration_s: number }[];
}

export interface SourceDetailResponse extends NovelFromSource {
  novel: NovelDetail;
  audiobook?: { language: string; duration_s: number; slug: string; is_adult?: boolean } | null;
}

export interface SimilarNovel extends Novel {
  similarity: number;
}

export interface ChapterContent {
  id: string;
  chapter_id: number;
  title: string;
  // The title as readers see it, numbered and in the novel's language; use this instead of title
  display_title: string;
  novel_title: string;
  novel_id: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  body: string;
  prev_chapter?: number | null;
  next_chapter?: number | null;
  prev_chapter_id?: number | null;
  next_chapter_id?: number | null;
  images_path?: string;
  source_overview_image_url?: string | null;
  language?: string | null;
  audio_url?: string | null;
  audio_duration_s?: number | null;
  // Comments of the chapter, replies included, shared by every source with this chapter number
  comment_count?: number;
  top_comment?: CommentPreview | null;
}

export interface UnavailableChapterInfo {
  chapter_id: number;
  title: string;
  display_title: string;
  novel_title: string;
  prev_chapter?: number | null;
  next_chapter?: number | null;
}

export interface Chapter {
  id: string;
  chapter_id: number;
  title: string;
  display_title: string;
  url: string;
  volume: number;
  volume_title: string | null;
  has_content: boolean;
  has_audio?: boolean;
}

// One page of a source's chapter list, as the chapters endpoint returns it
export interface NovelChaptersResponse {
  chapters: Chapter[];
  count: number;
  total_pages: number;
  current_page: number;
  novel_title: string;
  source_name: string;
  is_dmca: boolean;
  source_overview_image_url?: string | null;
  // Whether the source has several volumes or titled ones: the list shows volume headings
  has_volumes: boolean;
}

// Where the reader resumes: the chapter, and how far through it (0..1)
export interface ReadingResume {
  chapter: Chapter;
  progress: number;
}

// The user's reading position in one novel: the chapter being read, and where Continue resumes
export interface ReadingHistory {
  id: string;
  novel_slug: string;
  source_slug: string;
  // Display name of the source the row points at
  source_name: string;
  // The chapter being read, and how far through it (0..1)
  current_chapter: Chapter | null;
  position: number;
  last_read_at: string;
  // Null when up to date, or when there is no pointer
  resume: ReadingResume | null;
  // Content chapters after current_chapter
  unread_chapters: number;
  source_latest_chapter: Chapter | null;
}
