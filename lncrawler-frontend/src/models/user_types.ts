import { Novel } from './novels_types';

export interface User {
    id: string;
    username: string;
    profile_pic: string;
    bio?: string;
    banner?: string | null;
    social_links?: Record<string, string>;
    privacy_settings?: Record<string, PrivacyValue>;
}

export type PrivacyValue = 'public' | 'friends' | 'private';

export type PrivacySection =
    | 'library'
    | 'library_notes'
    | 'library_ratings'
    | 'reading_lists'
    | 'reviews'
    | 'comments'
    | 'stats'
    | 'reading_history'
    | 'friends';

export type FriendshipStatus = 'self' | 'friends' | 'request_sent' | 'request_received' | 'none';

export interface ProfileStats {
    word_read: number;
    chapters_read_count: number;
    chapters_not_read_yet_count: number;
    novels_count: number;
}

export interface ReadingProgress {
    novel: Novel;
    last_read_at: string;
    last_read_chapter: number | null;
    source_slug?: string | null;
}

export interface GenreCount {
    name: string;
    count: number;
}

export interface PublicProfile {
    id: string;
    username: string;
    profile_pic: string | null;
    banner: string | null;
    bio: string;
    date_joined: string;
    social_links: Record<string, string>;
    friendship_status: FriendshipStatus;
    friend_count: number;
    visibility: Record<PrivacySection, PrivacyValue>;
    pinned_novels: Novel[];
    stats: ProfileStats | null;
    currently_reading: ReadingProgress | null;
    top_genres: GenreCount[] | null;
    recent_reads: ReadingProgress[] | null;
}

export interface FriendRequest {
    id: string;
    requester: User;
    addressee: User;
    status: 'pending' | 'accepted';
    created_at: string;
}
