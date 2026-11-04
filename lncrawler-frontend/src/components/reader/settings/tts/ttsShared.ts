import { PREVIEW_TEXT } from '../../tts/voiceCatalog';

// Helpers shared by the listening pages
export const formatMb = (bytes: number) => `${Math.round(bytes / 1e6)} MB`;
export const hasWebGpu = () => typeof navigator !== 'undefined' && 'gpu' in navigator;
export const previewText = (lang: string) => PREVIEW_TEXT[lang] ?? PREVIEW_TEXT.en;
