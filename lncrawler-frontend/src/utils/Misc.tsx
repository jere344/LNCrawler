import type { TFunction } from 'i18next';
import type { Novel, NovelFromSource } from '@models/novels_types';
import defaultCover from '@assets/default-cover.jpg';
import { LANGUAGE_CODES, type LanguageCode } from '../generated/sharedConstants';

export function formatTimeAgo(date: Date, t: TFunction): string {
    const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(months / 12);

    if (seconds < 60) {
        return t('units.timeAgo', { count: seconds });
    } else if (minutes < 60) {
        return t('units.timeAgoMinutes', { count: minutes });
    } else if (hours < 24) {
        return t('units.timeAgoHours', { count: hours });
    } else if (days < 30) {
        return t('units.timeAgoDays', { count: days });
    } else if (months < 12) {
        return t('units.timeAgoMonths', { count: months });
    } else {
        return t('units.timeAgoYears', { count: years });
    }
}

// Relative time for an ISO date, or the translated "unknown" when there is no date.
export function formatTimeAgoOrUnknown(date: string | null | undefined, t: TFunction): string {
    return date ? formatTimeAgo(new Date(date), t) : t('common.unknown');
}

// Known edition spellings (lowercased, letters only) -> i18n key suffix under novelSources.edition.
const KNOWN_EDITIONS: Record<string, 'wn' | 'ln' | 'raw'> = {
    webnovel: 'wn',
    wn: 'wn',
    lightnovel: 'ln',
    ln: 'ln',
    raw: 'raw',
};

// Chip label for a source edition: known editions are translated, others shown as given.
// A missing or blank edition gives '' (nothing to show).
export function editionLabel(edition: string | null | undefined, t: TFunction): string {
    if (!edition?.trim()) {
        return '';
    }
    const key = KNOWN_EDITIONS[edition.toLowerCase().replace(/[^a-z]/g, '')];
    return key ? t(`novelSources.edition.${key}`) : edition;
}

export function formatDate(dateString: string, locale?: string): string {
    return new Date(dateString).toLocaleDateString(locale, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
    });
}

export function formatDateTime(dateString: string, locale?: string): string {
    return new Date(dateString).toLocaleDateString(locale, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: 'numeric',
        minute: 'numeric',
    });
}

export function formatCount(count: number): string {
    if (count >= 1000000) {
        return `${(count / 1000000).toFixed(1)}M`;
    } else if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}K`;
    }
    return `${count}`;
}

export const formatNumber = (value: number, locale?: string): string =>
    value.toLocaleString(locale);

// Cover of a novel's source, or the placeholder cover when it has none.
export const novelCoverUrl = (source: { cover_min_url?: string | null } | null | undefined): string =>
    source?.cover_min_url || defaultCover;

export const getChapterName = (title: string): string => {
    const chapterMarkers = [
        'chapter', 
        'c', 
        'ch', 
        'chapitre', 
        'chương', 
        'capítulo', 
    ]
    const escaped = chapterMarkers.map(m => m.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
    const markerGroup = `(?:${escaped.join('|')})`;

    const re = new RegExp(
        `(^(?:${markerGroup})?\\s*\\d+[-:, ]+)|([-:, ]+(?:${markerGroup})\\s*\\d+)`,
        'gi'
    );

    const latestChapterTitle = title.replace(re, "").trim();
    return latestChapterTitle || "";
};

interface NovelSourceTarget {
    slug: string;
    prefered_source?: { source_slug?: string | null } | null;
    reading_history?: { source_slug?: string | null } | null;
    reading_source?: { source_slug?: string | null } | null;
}

export const getNovelSourcePath = (novel: NovelSourceTarget): string | undefined => {
    const sourceSlug = novel.reading_source?.source_slug
        || novel.reading_history?.source_slug
        || novel.prefered_source?.source_slug;
    return sourceSlug ? `/novels/${novel.slug}/${sourceSlug}` : undefined;
};

// Language-aware display title: the preferred source's title, falling back to Novel.title.
export const getNovelDisplayTitle = (novel: {
    title: string;
    reading_source?: { title?: string | null } | null;
    prefered_source?: { title?: string | null } | null;
}): string => (novel.reading_source ?? novel.prefered_source)?.title || novel.title;

interface SourceLinkProps {
    to?: string;
    state?: unknown;
}

export const getNovelSourceLink = (novel: Novel): SourceLinkProps => {
    const to = getNovelSourcePath(novel);
    if (!to) return {};
    return { to, state: { novel, source: novel.reading_source ?? novel.prefered_source ?? null } };
};

export const getSourceLink = (source: NovelFromSource): SourceLinkProps =>
    source?.novel_slug && source?.source_slug
        ? { to: `/novels/${source.novel_slug}/${source.source_slug}`, state: { source } }
        : {};

export const getChapterLabel = (t: TFunction, title?: string | null, chapterId?: number | null): string => {
    const trimmed = title?.trim();
    if (trimmed) {
        return trimmed;
    }
    return chapterId != null ? t('units.chapter', { number: chapterId }) : "";
}


const languageCodeToFlag = (language?: string | null): string => {
    const languageMap: Record<LanguageCode, string> = {
        'en': 'gb',
        'fr': 'fr',
        'es': 'es',
        'de': 'de',
        'it': 'it',
        'ja': 'jp',
        'ko': 'kr',
        'zh': 'cn',
        'pt': 'pt',
        'ru': 'ru',
        'ar': 'sa',
        'hi': 'in',
        'th': 'th',
        'vi': 'vn',
        'id': 'id',
        'tr': 'tr',
        'pl': 'pl',
        'nl': 'nl',
        'sv': 'se',
        'da': 'dk',
    };
    return languageMap[(language || '').toLowerCase() as LanguageCode] || 'unknown';
}

export const languageFlagUrl = (language: string): string =>
    `/flags/${languageCodeToFlag(language)}.svg`;

export const languageCodeToName = (t: TFunction, language: string): string => {
    const code = (language || '').toLowerCase();
    return availableLanguages.includes(code) ? t(`languages.${code}`) : t('common.unknown');
}

// Typed as string[] so callers can check arbitrary values with includes().
export const availableLanguages: string[] = [...LANGUAGE_CODES];