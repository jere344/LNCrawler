import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { useParams } from 'react-router-dom';
import { useMediaQuery } from '@mui/material';
import { useAuth } from '@context/AuthContext';
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
import ChapterSEO from '@components/reader/ChapterSEO';
import { useReaderSettings } from './hooks/useReaderSettings';
import { useReaderLayout } from './hooks/useReaderLayout';
import { useReaderPanels } from './hooks/useReaderPanels';
import { useReaderBarProps } from './hooks/useReaderBarProps';
import { useFullscreen } from './hooks/useFullscreen';
import { useChapterLoader } from './hooks/useChapterLoader';
import { useReaderScrollSaving } from './hooks/useReaderScrollSaving';
import { useChapterReadTracking } from './hooks/useChapterReadTracking';
import { useChapterNavigation } from './hooks/useChapterNavigation';
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

  // Current chapter key for scroll position tracking
  const currentChapterKey = `${novelSlug}|${sourceSlug}|${chapterNumber}`;

  const { chapter, loading, error, unavailableChapter, bumpCommentCount } = useChapterLoader({
    novelSlug,
    sourceSlug,
    chapterNumber,
    onLoadStart: () => {
      loadedChapterKeyRef.current = null;
    },
  });

  const { saveScrollIfReady } = useReaderScrollSaving({
    currentChapterKey,
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
  });

  const { tts, novelLanguage, barHeight, handleListen, startNarration } = useReaderAudio({
    settings: readerSettings,
    chapter,
    loading,
    currentChapterKey,
    isNarrow,
    ttsOpenRef,
    onNextChapter: goNext,
  });

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
  });

  // Swipes work on every touch device; they pause while a panel covers the text, except the sheet
  const { swipeHandlers } = useReaderGestures({
    chapter,
    disabled: panel !== 'none' && panel !== 'display',
    swipeLeftGesture: readerSettings.swipeLeftGesture,
    swipeRightGesture: readerSettings.swipeRightGesture,
    onNextChapter: goNext,
    onPrevChapter: goPrev,
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
  const commentKey = {
    novelSlug: novelSlug ?? '',
    sourceSlug: sourceSlug ?? '',
    // The route always has a number once the chapter is shown (the loader waits for it)
    chapterNumber: parseInt(chapterNumber ?? ''),
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
            chapterLabel,
            totalCount: commentCount,
            threads,
            composing,
            onBack: popPage,
            onPushThread: pushThread,
            onStartComposing: startComposing,
            onStopComposing: stopComposing,
            // The count goes to the cached chapter it was posted to, which may no longer be on screen
            onPosted: bumpCommentCount,
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

      <TtsPlayerBar
        tts={tts}
        rate={readerSettings.ttsRate}
        onRateChange={rate => updateReaderSetting('ttsRate', rate)}
        onOpenSettings={() => openSettings({ page: 'listen' })}
        chapterTitle={chapterLabel}
        reservedStart={reservedStart}
      />
    </>
  );
};

export default ChapterReader;
