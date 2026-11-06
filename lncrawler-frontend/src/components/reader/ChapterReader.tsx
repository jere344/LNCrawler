import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useMediaQuery } from '@mui/material';
import { useAuth } from '@context/AuthContext';
import type { ChapterContent as IChapterContent } from '@models/novels_types';
import { getChapterLabel } from '@utils/Misc';
import { updateReaderSetting } from './readerSettingsStore';
import ReaderDesktopToolbar from './controls/ReaderDesktopToolbar';
import ReaderTopBar from './controls/ReaderTopBar';
import ReaderBottomBar from './controls/ReaderBottomBar';
import ReaderControlsTheme from './theme/ReaderControlsTheme';
import ReaderPanels from './panels/ReaderPanels';
import { reservedEnd as panelReservedEnd, reservedStart as panelReservedStart } from './panels/panelLayout';
import ReaderKeyboardNavigation from './controls/ReaderKeyboardNavigation';
import ChapterArticle from './content/ChapterArticle';
import DimGestureStrip from './viewport/DimGestureStrip';
import ChapterStatusView from './content/ChapterStatusView';
import TtsPlayerBar from './tts/TtsPlayerBar';
import { TTS_BAR_HEIGHT } from './tts/ttsTypes';
import ReaderInfoOverlay from './overlay/ReaderInfoOverlay';
import ChapterSEO from '@components/reader/ChapterSEO';
import { useReaderSettings } from './hooks/useReaderSettings';
import { useReaderLayout } from './hooks/useReaderLayout';
import { useReaderPanels } from './hooks/useReaderPanels';
import { useReaderBarProps } from './hooks/useReaderBarProps';
import { useFullscreen } from './hooks/useFullscreen';
import { useChapterLoader } from './hooks/useChapterLoader';
import { useChapterStream } from './hooks/useChapterStream';
import { useStreamTrim } from './hooks/useStreamTrim';
import { findStreamChapter } from './hooks/chapterStream';
import { sectionKeyOf } from './hooks/chapterRange';
import { useReaderScrollSaving } from './hooks/useReaderScrollSaving';
import { useChapterReadTracking } from './hooks/useChapterReadTracking';
import { useChapterNavigation } from './hooks/useChapterNavigation';
import { useActiveChapter } from './hooks/useActiveChapter';
import { useReaderAudio } from './hooks/useReaderAudio';
import { buildKeyBindings, keyLabelFor, useReaderActions } from './hooks/useReaderActions';
import { useReaderTapInput } from './hooks/useReaderTapInput';
import { useReaderGestures } from './hooks/useReaderGestures';
import { useHideScrollbar } from './hooks/useHideScrollbar';
import { useRevealOnTopHover } from './hooks/useRevealOnTopHover';
import { chapterListCache } from './panels/chapterList';

// The chapter list page is fetched this long after a chapter opens, once the text has settled
const CHAPTER_LIST_PREFETCH_MS = 1500;

const ChapterReader = () => {
  const { t } = useTranslation();
  const { novelSlug, sourceSlug, chapterNumber } = useParams<{
    novelSlug: string;
    sourceSlug: string;
    chapterNumber: string
  }>();
  const { mode, isDesktop, isNarrow } = useReaderLayout();
  // Touch laptops have a desktop layout but still get the dim strip
  const coarsePointer = useMediaQuery('(any-pointer: coarse)');
  const { isAuthenticated } = useAuth();
  const readerSettings = useReaderSettings();
  const infinite = readerSettings.readingMode === 'infinite';
  const navigate = useNavigate();
  const location = useLocation();
  const {
    panel,
    pages,
    searching,
    threads,
    composing,
    toggleDisplay,
    toggleChapters,
    toggleComments,
    openComments,
    pushThread,
    startComposing,
    stopComposing,
    openSettings,
    openCustomize,
    closePanel,
    popPage,
    pushPage,
    setDeskPage,
    startSearch,
    closeThen,
  } = useReaderPanels({ isDesktop });
  const reservedStart = panelReservedStart(panel, mode);
  const reservedEnd = panelReservedEnd(panel, mode);
  // The desktop toolbar starts shown; the touch bars start hidden
  const [controlsVisible, setControlsVisible] = useState(isDesktop);

  // Each time the layout switches, the bars go back to their starting state for it
  useEffect(() => {
    setControlsVisible(isDesktop);
  }, [isDesktop]);

  // Sentinel placed after the chapter text, watched to detect the reader reaching its end
  const endOfChapterRef = useRef<HTMLDivElement>(null);
  // Key of the chapter whose text is currently on screen (null while loading)
  const loadedChapterKeyRef = useRef<string | null>(null);
  // Whether the TTS bar covers the bottom of the viewport (set once tts exists)
  const ttsOpenRef = useRef(false);
  // The chapters on the page in infinite mode, read by the loader to switch to one without loading it
  const streamChaptersRef = useRef<IChapterContent[]>([]);
  // Chapter number the active-chapter tracker last moved the URL to
  const syncedChapterRef = useRef<number | null>(null);
  // The number of the chapter whose comments are open when it is not the route's one (infinite mode), null for the route's chapter
  const [commentsTargetNumber, setCommentsTargetNumber] = useState<number | null>(null);
  // Closing the comments panel forgets its target
  useEffect(() => {
    if (panel !== 'comments') setCommentsTargetNumber(null);
  }, [panel]);

  // Current chapter key for scroll position tracking
  const currentChapterKey = `${novelSlug}|${sourceSlug}|${chapterNumber}`;

  const { chapter, loading, error, unavailableChapter, loadId, bumpCommentCount, fetchChapterContent } = useChapterLoader({
    novelSlug,
    sourceSlug,
    chapterNumber,
    onLoadStart: () => {
      loadedChapterKeyRef.current = null;
    },
    // Only the reader's own URL update switches in place: a pick from the chapter list or history loads the chapter afresh, and its saved position (if any) is restored
    findOnPage: (n) => (infinite && syncedChapterRef.current === n
      ? findStreamChapter(streamChaptersRef.current, novelSlug, sourceSlug, n)
      : null),
  });
  // The chapters after the route's one, in infinite mode
  const stream = useChapterStream({
    enabled: infinite,
    anchor: chapter,
    loadId,
    fetchChapterContent,
  });
  // Kept in step with the stream, so the loader sees the chapters on the page
  streamChaptersRef.current = stream.chapters;

  // Infinite mode: the section of the active chapter is what the position and progress are measured in
  const sectionKey = infinite && chapter ? sectionKeyOf(chapter) : null;

  const { saveScrollIfReady } = useReaderScrollSaving({
    currentChapterKey,
    sectionKey,
    loadId,
    chapter,
    loading,
    savePosition: readerSettings.savePosition,
    loadedChapterKeyRef,
  });

  const {
    markingAsRead,
    markReadSuccess,
    showMarkReadButton,
    handleMarkAsRead,
    markBeforeLeaving,
    markedChapters,
    markingChapters,
    markChapter,
  } = useChapterReadTracking({
    novelSlug,
    sourceSlug,
    chapterNumber,
    currentChapterKey,
    chapter,
    loading,
    isAuthenticated,
    isNarrow,
    markReadBehavior: readerSettings.markReadBehavior,
    endOfChapterRef,
    loadedChapterKeyRef,
    ttsOpenRef,
  });

  const markRead = {
    showMarkRead: showMarkReadButton,
    markReadSuccess,
    markingAsRead,
    onMarkAsRead: handleMarkAsRead,
  };

  const { goNext, goPrev, goToSource, goToChapterList, goToChapter } = useChapterNavigation({
    novelSlug,
    sourceSlug,
    chapter,
    saveScrollIfReady,
    markBeforeLeaving,
    closeThen,
    infinite,
    streamChapters: stream.chapters,
  });

  // Infinite mode: the route follows the section under the reading line, without adding history entries
  const onActiveChange = (key: string) => {
    const [, , activeId] = key.split('|');
    const activeNumber = parseInt(activeId);
    const currentNumber = parseInt(chapterNumber ?? '');
    if (activeNumber === currentNumber) return;
    // Scrolling on past a chapter leaves it read; scrolling back up marks nothing
    if (infinite && activeNumber > currentNumber) void markBeforeLeaving();
    // The open panels live in the history state, so it is carried over; keepScroll stops the app scrolling to the top
    syncedChapterRef.current = activeNumber;
    const state = { ...(location.state && typeof location.state === 'object' ? location.state : {}), keepScroll: true };
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${activeNumber}`, { replace: true, state });
  };
  useActiveChapter(infinite && !loading && !!chapter, stream.chapters.length, onActiveChange);

  const { tts, ttsChapter, novelLanguage, barHeight, handleListen, startNarration } = useReaderAudio({
    settings: readerSettings,
    chapter,
    loading,
    currentChapterKey,
    isNarrow,
    ttsOpenRef,
    onNextChapter: goNext,
    infinite,
    streamChapters: stream.chapters,
    streamEnded: stream.end !== null,
    loadMore: () => { void stream.loadMore(); },
    loadId,
    onOpenChapter: (n) => navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${n}`),
  });

  // Infinite mode: the sections the trim keeps on the page, the active chapter, the one TTS reads and the one the comments are open on
  const commentsTarget = commentsTargetNumber !== null
    ? findStreamChapter(stream.chapters, novelSlug, sourceSlug, commentsTargetNumber)
    : null;
  const protectedKeyText = [chapter, ttsChapter, commentsTarget]
    .flatMap((section) => (section ? [sectionKeyOf(section)] : []))
    .join('\n');
  const protectedKeys = useMemo(() => new Set(protectedKeyText.split('\n').filter(Boolean)), [protectedKeyText]);
  useStreamTrim(infinite && !loading, stream.chapters, protectedKeys, stream.trimTop);

  const fullscreen = useFullscreen();

  // Taps and keys share one set of actions
  const { runEdge, runKeyAction } = useReaderActions({
    goNext,
    goPrev,
    setControlsVisible,
    toggleDisplay,
    toggleComments,
    toggleFullscreen: fullscreen.toggle,
  });

  // A tap on the text seeks the TTS when it is playing and the text is not selected
  const seekTap = (target: Node) =>
    tts.open && readerSettings.ttsTapToSeek && (window.getSelection()?.isCollapsed ?? true) &&
    tts.seekToNode(target);

  const { tapProps, tapAt } = useReaderTapInput({
    settings: readerSettings,
    controlsVisible,
    panelOpen: panel !== 'none',
    setControlsVisible,
    closePanel,
    onEdge: runEdge,
    seekTap,
    onFullscreen: fullscreen.toggle,
  });

  // Swipes work on every touch device; they pause while a panel covers the text, except the sheet
  const { swipeHandlers } = useReaderGestures({
    chapter,
    disabled: panel !== 'none' && panel !== 'display',
    swipeLeftGesture: readerSettings.swipeLeftGesture,
    swipeRightGesture: readerSettings.swipeRightGesture,
    onNextChapter: goNext,
    onPrevChapter: goPrev,
    onToggleChapters: toggleChapters,
    onToggleComments: toggleComments,
  });

  const keyBindings = useMemo(() => buildKeyBindings(readerSettings), [readerSettings]);
  // Shortcut labels shown on the buttons, from the Keyboard settings
  const shortcuts = {
    prev: keyLabelFor(keyBindings, 'prevChapter'),
    next: keyLabelFor(keyBindings, 'nextChapter'),
    display: keyLabelFor(keyBindings, 'displaySheet'),
    comments: keyLabelFor(keyBindings, 'comments'),
    fullscreen: keyLabelFor(keyBindings, 'fullscreen'),
  };

  useHideScrollbar(readerSettings.hideScrollbar);

  // Desktop: moving the pointer to the top edge brings the hidden toolbar back
  const revealControls = useCallback(() => setControlsVisible(true), []);
  useRevealOnTopHover(isDesktop && !controlsVisible, revealControls);

  // The chapter's comments, the ones posted in this session included
  // Opened from a section: the panel is about that section, unless it is the route's chapter
  // The panel stays on the section it was opened from while the reader scrolls on
  const onOpenCommentsFor = (section: IChapterContent, opts?: { compose?: boolean }) => {
    setCommentsTargetNumber(section.chapter_id);
    openComments(opts);
  };

  // The chapter the comments panel is about: the one it was opened from, else the route's
  const commentKey = {
    novelSlug: novelSlug ?? '',
    sourceSlug: sourceSlug ?? '',
    // The route always has a number once the chapter is shown (the loader waits for it)
    chapterNumber: commentsTargetNumber ?? parseInt(chapterNumber ?? ''),
  };
  const commentCount = chapter?.comment_count ?? 0;

  const { barProps, chapterLabel } = useReaderBarProps({
    chapter,
    controlsVisible,
    isDesktop,
    panel,
    reservedStart,
    reservedEnd,
    shortcuts,
    setControlsVisible,
    markRead,
    fullscreen: { supported: fullscreen.supported, active: fullscreen.active, onToggle: fullscreen.toggle },
    navigation: { goPrev, goNext, goToSource },
    onToggleChapters: toggleChapters,
    onToggleDisplay: toggleDisplay,
    toggleComments,
    commentsOpen: panel === 'comments',
    commentCount,
    onOpenSettings: () => openSettings(),
    onListen: handleListen,
  });

  // The comments panel is about another section than the route's chapter: its live entry on the page, when it is still there
  const commentsOnOtherChapter = commentsTargetNumber !== null && commentsTargetNumber !== chapter?.chapter_id;
  const commentsSection = commentsOnOtherChapter
    ? findStreamChapter(stream.chapters, novelSlug, sourceSlug, commentsTargetNumber)
    : null;
  // The comments panel's caption and count follow the chapter it is about; the route chapter's count includes comments posted here
  const commentsLabel = commentsSection
    ? getChapterLabel(t, commentsSection.title, commentsSection.chapter_id)
    : chapterLabel;
  const commentsTotal = commentsOnOtherChapter ? (commentsSection?.comment_count ?? 0) : commentCount;

  // Once the reader settles, loads the list page around this chapter: the list then opens from the cache with no skeleton
  const chapterId = chapter?.chapter_id;
  useEffect(() => {
    if (!novelSlug || !sourceSlug || chapterId === undefined) return;
    const timer = window.setTimeout(() => {
      chapterListCache.load({ novelSlug, sourceSlug, around: chapterId }).catch(() => {});
    }, CHAPTER_LIST_PREFETCH_MS);
    return () => window.clearTimeout(timer);
  }, [novelSlug, sourceSlug, chapterId]);

  // Loading, unavailable and error states replace the reader; every hook above runs first
  if (loading || unavailableChapter || error || !chapter) {
    return (
      <ChapterStatusView
        loading={loading}
        error={error}
        unavailableChapter={unavailableChapter}
        novelSlug={novelSlug}
        sourceSlug={sourceSlug}
      />
    );
  }


  // The TTS bar sits at the bottom, so the touch bottom bar rises above it
  const bottomOffset = tts.open ? (isNarrow ? TTS_BAR_HEIGHT.mobile : TTS_BAR_HEIGHT.desktop) : 0;

  // The dim strip: only with the bars and panels hidden, and on touch (or when the layout is not desktop)
  const dimSide = readerSettings.dimGestureSide;
  const dimStripShown = panel === 'none' && !controlsVisible && (!isDesktop || coarsePointer);

  // The info overlay hides under the bars that would cover it, and while a panel is open
  const overlayBarCovers = controlsVisible && (!isDesktop || readerSettings.overlayPosition === 'top');
  const overlayShown = readerSettings.overlayEnabled && panel === 'none' && !overlayBarCovers;

  return (
    <>
      <ChapterSEO chapter={chapter} />

      <ReaderControlsTheme backgroundColor={readerSettings.backgroundColor}>
        {/* One toolbar on desktop, the top and bottom bars on touch layouts */}
        {isDesktop ? (
          <ReaderDesktopToolbar {...barProps} />
        ) : (
          <>
            <ReaderTopBar {...barProps} />
            <ReaderBottomBar
              {...barProps}
              bottomOffset={bottomOffset}
              ttsOpen={tts.open}
              isNarrow={isNarrow}
              isPhoneLandscape={mode === 'phoneLandscape'}
            />
          </>
        )}

        <ReaderPanels
          panel={panel}
          mode={mode}
          bottomOffset={bottomOffset}
          pages={pages}
          searching={searching}
          novelLanguage={novelLanguage}
          hasNarration={!!chapter.audio_url}
          chapterNumber={chapter.chapter_id}
          chapterList={{
            novelSlug: novelSlug ?? '',
            sourceSlug: sourceSlug ?? '',
            novelTitle: chapter.novel_title,
            currentChapterId: chapter.chapter_id,
            onOpenChapter: goToChapter,
            onOpenNovel: goToSource,
          }}
          onTtsBeforePreview={tts.pause}
          onClosePanel={closePanel}
          comments={{
            novelSlug: commentKey.novelSlug,
            sourceSlug: commentKey.sourceSlug,
            chapterNumber: commentKey.chapterNumber,
            chapterLabel: commentsLabel,
            totalCount: commentsTotal,
            threads,
            composing,
            onBack: popPage,
            onPushThread: pushThread,
            onStartComposing: startComposing,
            onStopComposing: stopComposing,
            // The count goes to the cached chapter it was posted to, which may no longer be on screen, and to every section of it on the page
            onPosted: (postedNumber) => {
              bumpCommentCount(postedNumber);
              stream.bumpCommentCount(novelSlug ?? '', postedNumber);
            },
          }}
          onBack={popPage}
          onPushPage={pushPage}
          onSetDeskPage={setDeskPage}
          onStartSearch={startSearch}
          onOpenCustomize={openCustomize}
          onOpenAllSettings={() => openSettings()}
        />
      </ReaderControlsTheme>

      <ChapterArticle
        chapter={chapter}
        novelSlug={novelSlug}
        sourceSlug={sourceSlug}
        endOfChapterRef={endOfChapterRef}
        stream={stream}
        infinite={infinite}
        tapProps={tapProps}
        swipeHandlers={swipeHandlers}
        onListen={handleListen}
        onOpenSettings={() => openSettings()}
        onOpenChapterList={goToChapterList}
        onNarrate={() => { void startNarration(chapter); }}
        markRead={markRead}
        onPrevious={goPrev}
        onNext={goNext}
        commentCount={commentCount}
        topComment={chapter.top_comment ?? null}
        onOpenComments={openComments}
        markedChapters={markedChapters}
        markingChapters={markingChapters}
        onMarkChapter={markChapter}
        onOpenCommentsFor={onOpenCommentsFor}
        ttsOpen={tts.open}
        barHeight={barHeight}
        reservedStart={reservedStart}
        reservedEnd={reservedEnd}
      />

      <ReaderKeyboardNavigation
        enabled={readerSettings.keyboardNavigation}
        paused={(panel === 'settings' || panel === 'customize' || panel === 'chapters' || panel === 'comments') && mode === 'phone'}
        bindings={keyBindings}
        onAction={runKeyAction}
        // Escape goes back one layer, like Back, and only while a panel is open, so it never hides the desktop toolbar
        onEscape={() => { if (panel !== 'none') popPage(); }}
      />

      {dimSide !== 'off' && dimStripShown && (
        <DimGestureStrip
          side={dimSide}
          savedWidth={readerSettings.dimGestureWidth}
          dimLevel={readerSettings.dimLevel}
          tapProps={tapProps}
          onTap={tapAt}
        />
      )}

      {overlayShown && novelSlug && sourceSlug && (
        <ReaderInfoOverlay
          items={readerSettings.overlayItems}
          position={readerSettings.overlayPosition}
          size={readerSettings.overlaySize}
          dimLevel={readerSettings.dimLevel}
          novelSlug={novelSlug}
          sourceSlug={sourceSlug}
          chapterId={chapter.chapter_id}
          sectionKey={sectionKey}
          reservedStart={reservedStart}
          reservedEnd={reservedEnd}
          bottomOffset={bottomOffset}
        />
      )}

      <TtsPlayerBar
        tts={tts}
        rate={readerSettings.ttsRate}
        onRateChange={rate => updateReaderSetting('ttsRate', rate)}
        onOpenSettings={() => openSettings({ page: 'listen' })}
        // In infinite mode the TTS can be reading another chapter than the one on screen
        chapterTitle={ttsChapter ? getChapterLabel(t, ttsChapter.title, ttsChapter.chapter_id) : chapterLabel}
        reservedStart={reservedStart}
      />
    </>
  );
};

export default ChapterReader;
