export function formatTimeAgo(date : Date): string {
    const seconds = Math.floor((new Date().getTime() - date.getTime()) / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    const months = Math.floor(days / 30);
    const years = Math.floor(months / 12);

    if (seconds < 60) {
        return `${seconds} seconds ago`;
    } else if (minutes < 60) {
        return `${minutes} minutes ago`;
    } else if (hours < 24) {
        return `${hours} hours ago`;
    } else if (days < 30) {
        return `${days} days ago`;
    } else if (months < 12) {
        return `${months} months ago`;
    } else {
        return `${years} years ago`;
    }
}

export const getChapterName = (title: string): string => {
    const re = new RegExp("(((Chapter|Chapitre|Ch) ?|C)[0-9]+(.[0-9]+)? ?(-|[:;.])?)|^[0-9]+(.[0-9]+)?");
    const latestChapterTitle = title.replace(re, "").trim();
    return latestChapterTitle || "";
};

export const getChapterNameWithNumber = (title?: string, chapterNumber?: number): string => {
    if (!chapterNumber) {
        return "";
    }
    title = getChapterName(title || "");
    return "Chapter " + chapterNumber + (title ? " - " + title : "");
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

export const languageCodeToName = (language: string): string => {
    const languageMap: { [key: string]: string } = {
        'en': 'English',
        'fr': 'French',
        'es': 'Spanish',
        'de': 'German',
        'it': 'Italian',
        'ja': 'Japanese',
        'ko': 'Korean',
        'zh': 'Chinese',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'th': 'Thai',
        'vi': 'Vietnamese',
        'id': 'Indonesian',
        'tr': 'Turkish',
        'pl': 'Polish',
        'nl': 'Dutch',
        'sv': 'Swedish',
        'unknown': 'Unknown',
    };
    return languageMap[language] || '?';
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