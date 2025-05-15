// Search-related types
export interface SearchResponse {
  status: string;
  message: string;
  job_id: string;
}

export interface SearchStatus {
  status: string;
  status_display: string;
  search_completed: boolean;
  has_results: boolean;
  error?: string;
  progress?: number;
  total_items?: number;
  progress_percentage?: number;
}

export interface Novel {
  id: string;
  title: string;
  url: string;
}

export interface SearchSource {
  url: string;
  info: string;
  index: number;
}

export interface SearchResult {
  index: number;
  title: string;
  sources: SearchSource[];
}

export interface SearchResults {
  status: string;
  results: SearchResult[];
}

// Download-related types
export interface DownloadParams {
  novel_index: number;
  source_index: number;
}

export interface DownloadResponse {
  status: string;
  message: string;
  job_id: string;
}

export interface DownloadStatus {
  status: string;
  job_status: string;
  status_display: string;
  download_completed: boolean;
  progress: number;
  total_chapters: number;
  progress_percentage: number;
  selected_novel: {
    title: string;
    volumes: number;
    chapters: number;
    url: string;
  };
}

export interface DownloadResults {
  status: string;
  output_path: string;
  output_files: string[];
  selected_novel: {
    title: string;
    volumes: number;
    chapters: number;
    url: string;
  };
  output_slug: string;
}

// Job-related types
export interface Job {
  id: string;
  status: string;
  status_display: string;
  query: string;
  created_at: string;
  updated_at: string;
  progress: number;
  total_items: number;
  progress_percentage: number;
  search_results: any;
  selected_novel: any;
  output_path: string | null;
  output_files: string[] | null;
  error_message: string | null;
}
