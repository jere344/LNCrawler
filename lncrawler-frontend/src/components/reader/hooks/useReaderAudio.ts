import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject } from 'react';
import { useTranslation } from 'react-i18next';
import { useTheme } from '@mui/material';
import { alpha } from '@mui/material/styles';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import { useAudioPlayer } from '@context/AudioPlayerContext';
import { getChapterLabel } from '@utils/Misc';
import { ReaderSettings as IReaderSettings } from '../readerSettingsSchema';
import { updateReaderSetting } from '../readerSettingsStore';
import { useTtsPlayer } from '../tts/useTtsPlayer';
import { TTS_BAR_HEIGHT, type TtsPrefs } from '../tts/ttsTypes';
import { sectionKeyOf } from './chapterRange';
import { findStreamChapter } from './chapterStream';
import { ttsNextStep } from './ttsChapter';

interface ReaderAudioOptions {
  settings: IReaderSettings;
  chapter: IChapterContent | null;
  // True while the chapter loads: the TTS only starts once the text is there
  loading: boolean;
  currentChapterKey: string;
  isNarrow: boolean;
  // Written here from the TTS state, read by the read tracking; owned by the reader
  ttsOpenRef: MutableRefObject<boolean>;
  onNextChapter: () => void;
  // readingMode === 'infinite'
  infinite: boolean;
  // The chapters on the page, in infinite mode
  streamChapters: IChapterContent[];
  // The stream has stopped: no more chapters will be added to the page
  streamEnded: boolean;
  loadMore: () => void;
  // Bumped by the loader on each real load
  loadId: number;
  // A normal route navigation to a chapter
  onOpenChapter: (n: number) => void;
}

// A chapter TTS waits for the stream to load, asked for in the load with this id
interface PendingNext {
  loadId: number;
  novelSlug: string;
  sourceSlug: string;
  chapter: number;
}

// Text-to-speech, the audiobook player hand-off and the listen action
export function useReaderAudio({
  settings,
  chapter,
  loading,
  currentChapterKey,
  isNarrow,
  ttsOpenRef,
  onNextChapter,
  infinite,
  streamChapters,
  streamEnded,
  loadMore,
  loadId,
  onOpenChapter,
}: ReaderAudioOptions) {
  const { t, i18n } = useTranslation();
  const theme = useTheme();

  // Sources store ISO codes, but tolerate regional forms like 'zh-CN'.
  const novelLanguage = (chapter?.language || i18n.language || 'en').slice(0, 2).toLowerCase();
  const ttsLanguage = settings.ttsLanguage || novelLanguage;
  const ttsHighlightColors = useMemo(() => ({
    block: alpha(theme.palette.primary.main, 0.12),
    sentence: alpha(theme.palette.primary.main, 0.3),
  }), [theme.palette.primary.main]);

  // Infinite mode: the chapter TTS reads is pinned while engaged, so scrolling on does not move it
  const [pin, setPin] = useState<{ chapter: IChapterContent; loadId: number } | null>(null);
  // The next chapter, while the stream loads it
  const [pending, setPending] = useState<PendingNext | null>(null);
  // A pin holds only for the load it was made in, and only while its chapter is on the page
  const pinned = infinite && pin && pin.loadId === loadId
    ? findStreamChapter(streamChapters, pin.chapter.novel_slug, pin.chapter.source_slug, pin.chapter.chapter_id)
    : null;
  const ttsChapter = infinite ? (pinned ?? chapter) : chapter;
  const ttsKey = ttsChapter ? sectionKeyOf(ttsChapter) : null;
  // Read through a ref, so the root getter keeps its identity; no text while a chapter loads, like chapterKey
  const ttsKeyRef = useRef(ttsKey);
  ttsKeyRef.current = loading ? null : ttsKey;
  const getTtsRoot = useCallback(() => {
    const key = ttsKeyRef.current;
    return key ? document.querySelector<HTMLElement>(`[data-chapter-key="${CSS.escape(key)}"] .reader-content`) : null;
  }, []);

  // Infinite mode: the next chapter is read from the page, loaded onto it, or opened when it cannot be
  const ttsNext = () => {
    if (!ttsChapter) return;
    const step = ttsNextStep(ttsChapter, streamChapters);
    // The navigation is a real load, which releases the pin by itself
    if (step?.kind === 'open') {
      onOpenChapter(step.chapter);
    } else if (step?.kind === 'pin') {
      setPin({ chapter: step.chapter, loadId });
    } else if (step?.kind === 'load') {
      setPending({ loadId, novelSlug: ttsChapter.novel_slug, sourceSlug: ttsChapter.source_slug, chapter: step.chapter });
      loadMore();
    }
  };

  const tts = useTtsPlayer({
    prefs: settings,
    lang: ttsLanguage,
    chapterKey: infinite
      ? (loading ? null : ttsKey)
      : (!loading && chapter ? currentChapterKey : null),
    chapterTitle: ttsChapter ? getChapterLabel(t, ttsChapter.title, ttsChapter.chapter_id) : '',
    novelTitle: ttsChapter?.novel_title ?? '',
    artwork: ttsChapter?.source_overview_image_url,
    hasNextChapter: !!ttsChapter?.next_chapter,
    onNextChapter: infinite ? ttsNext : onNextChapter,
    onPrefChange: <K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) =>
      updateReaderSetting(key, value as IReaderSettings[K]),
    highlightColors: ttsHighlightColors,
    topOffset: isNarrow ? 0 : 64,
    bottomOffset: isNarrow ? TTS_BAR_HEIGHT.mobile : TTS_BAR_HEIGHT.desktop,
    getRoot: infinite ? getTtsRoot : undefined,
  });
  ttsOpenRef.current = tts.open;

  // Pinned from the route's chapter while TTS is in the middle of reading, released when it stops or ends;
  // an error keeps it, so Retry reads the same chapter
  const engaged = tts.open && tts.status !== 'idle';
  useEffect(() => {
    if (!infinite || !engaged) {
      setPin(null);
      setPending(null);
      return;
    }
    if (!pinned && !loading && chapter) setPin({ chapter, loadId });
  }, [infinite, engaged, pinned, loading, chapter, loadId]);

  // The chapter waited for is read once it is on the page; if the stream stops first, it is opened
  const awaited = pending && pending.loadId === loadId ? pending : null;
  useEffect(() => {
    if (!awaited || !engaged) return;
    const onPage = findStreamChapter(streamChapters, awaited.novelSlug, awaited.sourceSlug, awaited.chapter);
    if (onPage) {
      setPin({ chapter: onPage, loadId });
      setPending(null);
    } else if (streamEnded) {
      setPending(null);
      onOpenChapter(awaited.chapter);
    }
  }, [awaited, engaged, streamChapters, streamEnded, loadId, onOpenChapter]);

  // The audiobook mini bar hides while the TTS bar is open, so the two never stack at the bottom.
  const { setSuppressed, barHeight, playAudiobook } = useAudioPlayer();
  useEffect(() => {
    setSuppressed(tts.open);
    return () => setSuppressed(false);
  }, [tts.open, setSuppressed]);

  /** Narrate the chapter with its audiobook recording, through the global player. */
  const startNarration = (c: IChapterContent) =>
    playAudiobook(c.novel_slug, c.language ?? 'en', { chapterId: Number(c.id) });

  // The listen button narrates when the audiobook is preferred and the chapter has a recording.
  // If the player fails it has already shown a toast, so client TTS takes over.
  const handleListen = async () => {
    if (chapter?.audio_url && settings.ttsPreferAudiobook && await startNarration(chapter)) return;
    tts.start();
  };

  return { tts, novelLanguage, barHeight, startNarration, handleListen, ttsChapter };
}
