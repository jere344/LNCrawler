import { useEffect, useMemo, type MutableRefObject } from 'react';
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
  const tts = useTtsPlayer({
    prefs: settings,
    lang: ttsLanguage,
    chapterKey: !loading && chapter ? currentChapterKey : null,
    chapterTitle: chapter ? getChapterLabel(t, chapter.title, chapter.chapter_id) : '',
    novelTitle: chapter?.novel_title ?? '',
    artwork: chapter?.source_overview_image_url,
    hasNextChapter: !!chapter?.next_chapter,
    onNextChapter,
    onPrefChange: <K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) =>
      updateReaderSetting(key, value as IReaderSettings[K]),
    highlightColors: ttsHighlightColors,
    topOffset: isNarrow ? 0 : 64,
    bottomOffset: isNarrow ? TTS_BAR_HEIGHT.mobile : TTS_BAR_HEIGHT.desktop,
  });
  ttsOpenRef.current = tts.open;

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

  return { tts, novelLanguage, barHeight, startNarration, handleListen };
}
