import { NovelFromSource } from "@models/novels_types";

export function formatTimeAgo(dateString: string): string {
    const date = new Date(dateString);
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
