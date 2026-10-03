import type { TFunction } from 'i18next';
import type { Novel, NovelFromSource } from '@models/novels_types';

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

export function formatCount(count: number): string {
    if (count >= 1000000) {
        return `${(count / 1000000).toFixed(1)}M`;
    } else if (count >= 1000) {
        return `${(count / 1000).toFixed(1)}K`;
    }
    return `${count}`;
}

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

export interface NovelSourceTarget {
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

export interface SourceLinkProps {
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


export const languageCodeToFlag = (language: string): string => {
    const languageMap: { [key: string]: string } = {
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
    return languageMap[language.toLowerCase()] || 'unknown';
}

export const languageCodeToName = (t: TFunction, language: string): string => {
    const code = (language || '').toLowerCase();
    return availableLanguages.includes(code) ? t(`languages.${code}`) : t('common.unknown');
}

export const availableLanguages = [
    'en',
    'fr',
    'es',
    'de',
    'it',
    'ja',
    'ko',
    'zh',
    'pt',
    'ru',
    'ar',
    'hi',
    'th',
    'vi',
    'id',
    'tr',
    'pl',
    'nl',
    'sv',
    'da',
];