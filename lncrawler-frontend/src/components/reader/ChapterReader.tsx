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
import { reservedEnd as panelReservedEnd } from './panels/panelLayout';
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
    settingsPage,
    toggleDisplay,
    openSettings,
    openCustomize,
    closeCustomize,
    closePanel,
  } = useReaderPanels();
  const reservedEnd = panelReservedEnd(panel, mode);
  // The desktop toolbar starts shown; the touch bars start hidden
  const [controlsVisible, setControlsVisible] = useState(isDesktop);
  const [activeTab, setActiveTab] = useState(0);

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

  const { chapter, loading, error, unavailableChapter } = useChapterLoader({
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
    activeTab,
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

  const { goNext, goPrev, goToSource, goToChapterList } = useChapterNavigation({
    novelSlug,
    sourceSlug,
    chapter,
    saveScrollIfReady,
    markBeforeLeaving,
    setActiveTab,
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

  // Taps and keys share one set of actions
  const { runEdge, runKeyAction } = useReaderActions({
    goNext,
    goPrev,
    setControlsVisible,
    toggleDisplay,
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
  };

  useHideScrollbar(readerSettings.hideScrollbar);

  // Desktop: moving the pointer to the top edge brings the hidden toolbar back
  const revealControls = useCallback(() => setControlsVisible(true), []);
  useRevealOnTopHover(isDesktop && !controlsVisible, revealControls);

  const { barProps, switchToComments, chapterLabel } = useReaderBarProps({
    chapter,
    controlsVisible,
    isDesktop,
    panel,
    reservedEnd,
    shortcuts,
    setControlsVisible,
    setActiveTab,
    markRead,
    navigation: { goPrev, goNext, goToSource, goToChapterList },
    onToggleDisplay: toggleDisplay,
    onOpenSettings: () => openSettings(),
    onListen: handleListen,
  });

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
          settingsPage={settingsPage}
          novelLanguage={novelLanguage}
          hasNarration={!!chapter.audio_url}
          onTtsBeforePreview={tts.pause}
          onClosePanel={closePanel}
          onOpenCustomize={openCustomize}
          onCloseCustomize={closeCustomize}
          onOpenAllSettings={() => openSettings()}
        />
      </ReaderControlsTheme>

      <ChapterArticle
        chapter={chapter}
        novelSlug={novelSlug}
        sourceSlug={sourceSlug}
        chapterNumber={chapterNumber}
        activeTab={activeTab}
        onTabChange={(_event, value) => setActiveTab(value)}
        endOfChapterRef={endOfChapterRef}
        tapProps={tapProps}
        swipeHandlers={swipeHandlers}
        onListen={handleListen}
        onOpenSettings={() => openSettings()}
        onNarrate={() => { void startNarration(chapter); }}
        markRead={markRead}
        onPrevious={goPrev}
        onNext={goNext}
        onGoToComments={switchToComments}
        ttsOpen={tts.open}
        barHeight={barHeight}
        reservedEnd={reservedEnd}
      />

      <ReaderKeyboardNavigation
        enabled={readerSettings.keyboardNavigation}
        paused={(panel === 'settings' || panel === 'customize') && mode === 'phone'}
        bindings={keyBindings}
        onAction={runKeyAction}
        // Escape closes an open panel only, so it never hides the desktop toolbar
        onEscape={() => { if (panel !== 'none') closePanel(); }}
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
      />
    </>
  );
};

export default ChapterReader;
