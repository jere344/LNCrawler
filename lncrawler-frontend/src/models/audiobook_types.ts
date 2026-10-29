export type AudiobookFormat = 'opus' | 'aac';

// The viewer's own progress on an audiobook (null when they have none).
export interface ListeningProgress {
  chapter_id: number | null;
  chapter_number: number | null;
  chapter_title: string | null;
  position_s: number;
  speed: number;
  finished: boolean;
  updated_at: string | null;
}

// A list or home card. Serialized by audiobook_card() in the backend.
export interface AudiobookCard {
  slug: string;
  language: string;
  title: string;
  authors: string[];
  cover_url: string | null;
  cover_jpg_url: string | null;
  duration_s: number;
  parts: number;
  chapters: number;
  first_published_at: string | null;
  last_part_at: string | null;
  featured: boolean;
  // Adult source or novel. Guests and 'blur'/'yes' viewers see it blurred; 'no' viewers never get it.
  is_adult: boolean;
  progress: ListeningProgress | null;
}

export interface AudiobookChapter {
  chapter_id: number;
  number: number;
  title: string;
  audio_url: string;
  duration_s: number;
  offset_s: number;
  volume: number;
  volume_title: string | null;
}

// A volume of the source that a part covers.
export interface AudiobookVolume {
  number: number;
  title: string | null;
}

export interface AudiobookPart {
  index: number;
  state: 'available' | 'in_production';
  chapter_start: number;
  chapter_end: number;
  word_count: number;
  duration_s: number;
  estimated_duration_s: number;
  // Engine that narrated the part; null while it is in production.
  engine: string | null;
  size_bytes: number | null;
  // Build progress (0 to 1) while in production; null once available.
  progress: number | null;
  downloads: Record<AudiobookFormat, { cached: boolean }> | null;
  chapters: AudiobookChapter[] | null;
  volumes: AudiobookVolume[];
}

export interface AudiobookCastMember {
  name: string;
  role: string | null;
  engine: string | null;
  voice: string | null;
  gender: string | null;
  // Short plain-text description of the voice, when the worker sent one.
  description: string | null;
}

// The detail page: the card plus the synopsis, links, credits, feed, cast and parts.
// The narrator is in `credits.narrator` (the backend does not expose a top-level `narrator`).
export interface AudiobookDetail extends Omit<AudiobookCard, 'parts'> {
  synopsis: string;
  // The novel is DMCA-removed from the site; the audiobook page stays reachable with a notice.
  is_dmca: boolean;
  novel_slug: string;
  source_slug: string;
  credits: { narrator: string | null } & Record<string, string | null | undefined>;
  feed_url: string;
  cast: AudiobookCastMember[];
  parts: AudiobookPart[];
  // The source's chapters span more than one volume.
  has_volumes: boolean;
  // Languages of the other visible audiobooks of the same novel.
  other_languages: string[];
}

// The audiobook block of the home page.
export interface HomeAudiobooks {
  featured: AudiobookCard | null;
  popular: AudiobookCard[];
  continue_listening: AudiobookCard[];
}

export type AudiobookSort = 'popular' | 'new' | 'updated' | 'longest';

// Query params of GET /audiobooks/. Tag and author names are sent as repeated params.
export interface AudiobookListParams {
  sort?: AudiobookSort;
  q?: string;
  tag?: string[];
  exclude_tag?: string[];
  author?: string[];
  listening?: boolean;
  lang?: string;
  page?: number;
  page_size?: number;
}

export interface AudiobookListResponse {
  count: number;
  total_pages: number;
  current_page: number;
  // RSS news feed of new parts, without the adult parameter (add ?adult=exclude|include|only).
  catalog_feed_url: string;
  // Sorted languages of every visible audiobook, for the language filter.
  languages: string[];
  results: AudiobookCard[];
}

// Body of PUT/POST /audiobooks/<slug>/progress/.
export interface ListeningProgressUpdate {
  chapter_id: number;
  position_s: number;
  speed?: number;
  finished?: boolean;
}

// Body of POST /audiobooks/<slug>/play/. Counted once per listening session by the caller.
export interface AudiobookPlayBody {
  chapter_id: number;
  listened_s?: number;
}

// Result of AudiobookService.prepare: the file is cached or still building.
export type AudiobookPrepareResult =
  | { status: 'ready'; url: string }
  | { status: 'building'; progress: number | null; retryAfter: number };

// Reading history filter: `kind` query param of GET users/reading-history/.
export type HistoryKind = 'all' | 'read' | 'listen';

// A listening entry of the history: the ListeningProgress id (for delete) and its audiobook card with progress.
export interface ListeningHistoryEntry {
  kind: 'listen';
  id: number;
  at: string;
  audiobook: AudiobookCard;
}
