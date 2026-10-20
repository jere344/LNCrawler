import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Container,
  Typography,
  Paper,
  Box,
  CircularProgress,
  useMediaQuery,
  useTheme,
  Tabs,
  Tab,
  IconButton,
} from '@mui/material';
import { userService } from '../../services/api';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import CommentIcon from '@mui/icons-material/Comment';
import SettingsIcon from '@mui/icons-material/Settings';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import { alpha } from '@mui/material/styles';
import { ChapterContent as IChapterContent, UnavailableChapterInfo } from '@models/novels_types';
import ReaderSettings, { ReaderSettings as IReaderSettings, EdgeTapBehavior } from './ReaderSettings';
import { defaultSettings } from './readerDefaults';
import { setCookie } from '@utils/cookies';
import { READER_COOKIE_PREFIX, READER_COOKIE_DAYS } from '@utils/storage';
import { getChapterLabel } from '@utils/Misc';
import BreadcrumbNav from '../common/BreadcrumbNav';
import { useAuth } from '@context/AuthContext';
import { useNotification } from '@context/NotificationContext';

import ReaderToolbar from './controls/ReaderToolbar';
import ReaderViewport from './viewport/ReaderViewport';
import ReaderContent from './content/ReaderContent';
import ReaderControls from './controls/ReaderControls';
import CommentSection from '../comments/CommentSection';

import ReaderKeyboardNavigation from './controls/ReaderKeyboardNavigation';
import TtsPlayerBar from './tts/TtsPlayerBar';
import { useTtsPlayer } from './tts/useTtsPlayer';
import { TTS_BAR_HEIGHT, type TtsPrefs } from './tts/ttsTypes';
import UnavailableChapter from './UnavailableChapter';
import ChapterSEO from '@components/reader/ChapterSEO';
import { useChapterCache } from './hooks/useChapterCache';
import { useScrollPersistence, SCROLL_SAVE_THROTTLE } from './hooks/useScrollPersistence';
import { useReaderGestures } from './hooks/useReaderGestures';
import { useLoadReaderSettingsFromCookies } from './hooks/useLoadReaderSettingsFromCookies';

const EDGE_TAP_WIDTH_PERCENTAGE = 15; // % of screen width for edge tap detection

const ChapterReader = () => {
  const { novelSlug, sourceSlug, chapterNumber } = useParams<{ 
    novelSlug: string; 
    sourceSlug: string; 
    chapterNumber: string 
  }>();
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  
  const [chapter, setChapter] = useState<IChapterContent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [unavailableChapter, setUnavailableChapter] = useState<UnavailableChapterInfo | null>(null);
  const [markingAsRead, setMarkingAsRead] = useState(false);
  const [markReadSuccess, setMarkReadSuccess] = useState(false);
  
  // Get authentication state to check if the user is logged in
  const { isAuthenticated } = useAuth();
  const { notify } = useNotification();
  
  // Reader settings state
  const [readerSettings, setReaderSettings] = useState<IReaderSettings>(defaultSettings);
  const [controlsVisible, setControlsVisible] = useState(false);
  const [settingsFocusTts, setSettingsFocusTts] = useState(false);

  // Close the settings drawer resets which section it opens on
  useEffect(() => {
    if (!controlsVisible) setSettingsFocusTts(false);
  }, [controlsVisible]);
  
  // Add state for active tab
  const [activeTab, setActiveTab] = useState(0);
  
  // Chapter content cache and preload
  const { fetchChapterContent, preloadNextChapter } = useChapterCache(novelSlug, sourceSlug);
  const contentRef = useRef<HTMLDivElement>(null);
  
  // Tags each chapter fetch so a slow older request can't overwrite a newer one
  const loadRequestIdRef = useRef(0);
  
  // Current chapter key for scroll position tracking
  const currentChapterKey = `${novelSlug}|${sourceSlug}|${chapterNumber}`;

  // Memoize chapterData for CommentSection to prevent re-renders on scroll
  const chapterDataForComments = useMemo(() => {
    if (novelSlug && sourceSlug && chapterNumber) {
      return {
        novelSlug,
        sourceSlug,
        chapterNumber: parseInt(chapterNumber),
      };
    }
    return null;
  }, [novelSlug, sourceSlug, chapterNumber]);

  // Load saved settings from cookies
  useLoadReaderSettingsFromCookies(setReaderSettings);

  // Scroll position save/restore for the current chapter
  const { saveScrollPosition, restoreScrollPosition, scrollRestoreTimeoutRef } = useScrollPersistence({
    currentChapterKey,
    savePosition: readerSettings.savePosition,
  });

  useEffect(() => {
    const loadCurrentChapter = async () => {
      if (!novelSlug || !sourceSlug || !chapterNumber) return;
      
      const requestId = ++loadRequestIdRef.current;
      setError(null);
      setUnavailableChapter(null);
      setLoading(true);
      try {
        const chapterData = await fetchChapterContent(
          novelSlug, 
          sourceSlug, 
          parseInt(chapterNumber)
        );
        // Ignore a stale response if the user navigated to another chapter.
        if (requestId !== loadRequestIdRef.current) return;
        setChapter(chapterData);
        
        // Preload next chapter if it exists
        if (chapterData.next_chapter) {
          preloadNextChapter(chapterData.next_chapter);
        }
      } catch (err) {
        if (requestId !== loadRequestIdRef.current) return;
        console.error('Error fetching chapter content:', err);
        const response = (err as {
          response?: { status?: number; data?: UnavailableChapterInfo };
        })?.response;
        const unavailable = response?.status === 404 ? response.data : undefined;
        if (response?.status === 451) {
          setError(t('reader.dmcaUnavailable'));
        } else if (unavailable && typeof unavailable.chapter_id === 'number') {
          // The chapter exists but has no content: show the unavailable page
          // instead of a generic error, with working next/prev navigation.
          setChapter(null);
          setUnavailableChapter(unavailable);
        } else {
          setError(t('reader.loadFailed'));
        }
      } finally {
        if (requestId === loadRequestIdRef.current) {
          setLoading(false);
        }
      }
    };

    loadCurrentChapter();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t/loader intentionally omitted; route params are the inputs
  }, [novelSlug, sourceSlug, chapterNumber]);

  // A previous chapter's "mark as read" success must not bleed into the next.
  useEffect(() => {
    setMarkReadSuccess(false);
  }, [novelSlug, sourceSlug, chapterNumber]);

  // Restore scroll position when chapter content is loaded
  useEffect(() => {
    if (!loading && chapter) {
      restoreScrollPosition();
    }
    return () => {
      if (scrollRestoreTimeoutRef.current !== null) {
        clearTimeout(scrollRestoreTimeoutRef.current);
        scrollRestoreTimeoutRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run only on the listed scroll inputs
  }, [loading, chapter]);

  // Save scroll position when navigating or every minute
  useEffect(() => {
    // Save position periodically while reading
    const saveInterval = setInterval(() => {
      if (chapter && !loading && readerSettings.savePosition) {
        saveScrollPosition();
      }
    }, 60000); // Save every minute
    
    // Save on page visibility change (tab switching, etc.)
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'hidden') {
        saveScrollPosition();
      }
    };
    
    // Use passive scroll listener with throttling
    let scrollTimeout: number | null = null;
    const handleScroll = () => {
      if (scrollTimeout === null) {
        scrollTimeout = window.setTimeout(() => {
          scrollTimeout = null;
          saveScrollPosition();
        }, SCROLL_SAVE_THROTTLE);
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('scroll', handleScroll, { passive: true });
    
    // Cleanup
    return () => {
      clearInterval(saveInterval);
      if (scrollTimeout) {
        clearTimeout(scrollTimeout);
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('scroll', handleScroll);
      saveScrollPosition(true); // Save one last time when component unmounts
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-subscribe only when the listed save inputs change
  }, [chapter, loading, readerSettings.savePosition, currentChapterKey]);

  const handleBackToChapters = () => {
    saveScrollPosition(true);
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleBackToSource = () => {
    saveScrollPosition(true);
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };
  
  // Add this function to handle automatic marking as read when navigating
  const handleChapterNavigation = async (direction: 'prev' | 'next') => {
    // Save current scroll position
    saveScrollPosition(true);
    
    // Get the chapter number to navigate to
    const targetChapter = direction === 'next' 
      ? chapter?.next_chapter 
      : chapter?.prev_chapter;

    // The immediate neighbour exists but isn't the next *available* chapter:
    // there's a gap. Route through the unavailable chapter's page so the skip
    // is deliberate rather than silent.
    const neighbor = direction === 'next' ? chapter?.next_chapter_id : chapter?.prev_chapter_id;
    const gapChapter = neighbor != null && neighbor !== targetChapter ? neighbor : null;
    
    if (!targetChapter && gapChapter == null) return;
    
    // For automatic marking settings, mark the current chapter as read when navigating away
    if (isAuthenticated && 
        chapterNumber && 
        novelSlug && 
        sourceSlug && 
        (readerSettings.markReadBehavior === 'automatic' || 
         readerSettings.markReadBehavior === 'buttonAutomatic')) {
      try {
        await userService.markChapterAsRead(
          novelSlug,
          sourceSlug,
          parseInt(chapterNumber)
        );
      } catch (error) {
        console.error('Error automatically marking chapter as read:', error);
      }
    }
    
    // Navigate to the target (or to the unavailable chapter that sits in between)
    setActiveTab(0);
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${gapChapter ?? targetChapter}`);
  };

  const nonDefiniteHandleNextChapter = () => {
    // Original chapter navigation
    if (chapter?.next_chapter) {
      handleChapterNavigation('next');
    }
  }

  const nonDefiniteHandlePrevChapter = () => {
    // Original chapter navigation
    if (chapter?.prev_chapter) {
      handleChapterNavigation('prev');
    }
  }

  // Update the navigation handlers to use the new function
  const handleNextChapter = () => {
    if (chapter?.next_chapter) {
      handleChapterNavigation('next');
    }
  };

  const handlePrevChapter = () => {
    if (chapter?.prev_chapter) {
      handleChapterNavigation('prev');
    }
  };

  // Handler for settings navigation
  const handleSettingsNavigate = (type: 'prev' | 'home' | 'next') => {
    if (type === 'prev' && chapter?.prev_chapter) {
      handlePrevChapter();
    } else if (type === 'home') {
      handleBackToSource();
    } else if (type === 'next' && chapter?.next_chapter) {
      handleNextChapter();
    }
    setControlsVisible(false);
  };

  // Function to execute the appropriate behavior based on edge settings
  const handleEdgeBehavior = (edge: 'left' | 'right', behavior: EdgeTapBehavior) => {
    switch (behavior) {
      case 'none':
        // Do nothing
        break;
      case 'scrollUp':
        // Scroll up by 80% of viewport height
        window.scrollBy({
          top: -window.innerHeight * 0.8,
          behavior: 'smooth'
        });
        break;
      case 'scrollDown':
        // Scroll down by 80% of viewport height
        window.scrollBy({
          top: window.innerHeight * 0.8,
          behavior: 'smooth'
        });
        break;
      case 'chapter':
        // Navigate to previous or next chapter
        if (edge === 'left') {
          nonDefiniteHandlePrevChapter();
        } else if (edge === 'right') {
          nonDefiniteHandleNextChapter();
        }
        break;
    }
  };

  // Unified handler for content tap on mobile
  const handleContentClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const ttsSeek = () =>
      tts.open && readerSettings.ttsTapToSeek && (window.getSelection()?.isCollapsed ?? true) &&
      tts.seekToNode(e.target as Node);
    if (!isMobile) { ttsSeek(); return; }

    // If controls are open, close them unless the click was inside the controls
    if (controlsVisible) {
      const target = e.target as HTMLElement;
      const isSettingsClick = target.closest('.MuiDrawer-paper');
      const isAppBarClick = target.closest('.MuiAppBar-root');
      if (!isSettingsClick && !isAppBarClick) {
        setControlsVisible(false);
      }
      return;
    }

    // Handle edge taps
    const containerWidth = e.currentTarget.clientWidth;
    const tapX = e.clientX - e.currentTarget.getBoundingClientRect().left;
    const edgeWidth = containerWidth * (EDGE_TAP_WIDTH_PERCENTAGE / 100);

    // Left edge tap
    if (tapX <= edgeWidth) {
      handleEdgeBehavior('left', readerSettings.leftEdgeTapBehavior);
      return;
    }
    // Right edge tap
    if (tapX >= containerWidth - edgeWidth) {
      handleEdgeBehavior('right', readerSettings.rightEdgeTapBehavior);
      return;
    }

    if (ttsSeek()) return;

    // Center tap - only toggle controls if setting is enabled
    if (readerSettings.centerTapToOpenSettings) {
      setControlsVisible(!controlsVisible);
    }
  };

  // Function to mark the current chapter as read
  const handleMarkAsRead = async () => {
    if (!novelSlug || !sourceSlug || !chapterNumber || !isAuthenticated) return;
    
    try {
      setMarkingAsRead(true);
      await userService.markChapterAsRead(
        novelSlug,
        sourceSlug,
        parseInt(chapterNumber)
      );
      setMarkReadSuccess(true);
      notify({ message: t('reader.markedRead'), severity: 'success', duration: 3000 });
    } catch (error) {
      console.error('Error marking chapter as read:', error);
    } finally {
      setMarkingAsRead(false);
    }
  };

  // Function to switch to comments tab
  const handleSwitchToComments = () => {
    setActiveTab(1);
    // Scroll back to top
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Function to handle tab changes
  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
  };
  
  // Add effect to apply scrollbar hiding based on settings
  useEffect(() => {
    if (readerSettings.hideScrollbar) {
      // Add a style to hide scrollbar
      const styleElement = document.createElement('style');
      styleElement.id = 'hide-scrollbar-style';
      styleElement.textContent = `
        html { scrollbar-width: none; }
        body { -ms-overflow-style: none; }
        body::-webkit-scrollbar, body::-webkit-scrollbar-button { display: none; }
      `;
      document.head.appendChild(styleElement);
    } else {
      // Remove the style if it exists
      const existingStyle = document.getElementById('hide-scrollbar-style');
      if (existingStyle) {
        existingStyle.remove();
      }
    }

    return () => {
      // Cleanup: remove the style when component unmounts
      const existingStyle = document.getElementById('hide-scrollbar-style');
      if (existingStyle) {
        existingStyle.remove();
      }
    };
  }, [readerSettings.hideScrollbar]);

  // Memoize the chapter and settings for ReaderContent to prevent re-renders on scroll
  const memoizedChapterContent = useMemo(() => ({
    chapter,
    settings: readerSettings
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tracks primitive fields so the memo stays stable across scroll
  }), [
    chapter?.body,
    chapter?.images_path,
    readerSettings.fontSize,
    readerSettings.lineSpacing,
    readerSettings.wordSpacing,
    readerSettings.letterSpacing,
    readerSettings.textAlign,
    readerSettings.fontFamily,
    readerSettings.textSelectable,
    readerSettings.hideScrollbar,
    readerSettings.paragraphIndent,
    readerSettings.paragraphSpacing,
  ]);

  const handleSettingChange = (newSettings: IReaderSettings) => {
    setReaderSettings(newSettings);
  };

  // Persist one setting in state and cookie
  const updateSetting = <K extends keyof IReaderSettings>(key: K, value: IReaderSettings[K]) => {
    setReaderSettings(prev => ({ ...prev, [key]: value }));
    setCookie(READER_COOKIE_PREFIX + key, JSON.stringify(value), READER_COOKIE_DAYS);
  };

  // Add these variables to generate navigation URLs
  const prevUrl = chapter?.prev_chapter ? `/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.prev_chapter}` : undefined;
  const nextUrl = chapter?.next_chapter ? `/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.next_chapter}` : undefined;
  const homeUrl = novelSlug && sourceSlug ? `/novels/${novelSlug}/${sourceSlug}` : undefined;
  const chapterListUrl = novelSlug && sourceSlug ? `/novels/${novelSlug}/${sourceSlug}/chapterlist` : undefined;

  // Handle swipe gestures
  const { swipeHandlers } = useReaderGestures({
    chapter,
    isMobile,
    controlsVisible,
    readerSettings,
    onNextChapter: nonDefiniteHandleNextChapter,
    onPrevChapter: nonDefiniteHandlePrevChapter,
  });

  // Sources store ISO codes, but tolerate regional forms like 'zh-CN'.
  const novelLanguage = (chapter?.language || i18n.language || 'en').slice(0, 2).toLowerCase();
  const ttsLanguage = readerSettings.ttsLanguage || novelLanguage;
  const ttsHighlightColors = useMemo(() => ({
    block: alpha(theme.palette.primary.main, 0.12),
    sentence: alpha(theme.palette.primary.main, 0.3),
  }), [theme.palette.primary.main]);
  const tts = useTtsPlayer({
    prefs: readerSettings,
    lang: ttsLanguage,
    chapterKey: !loading && chapter ? currentChapterKey : null,
    chapterTitle: chapter ? getChapterLabel(t, chapter.title, chapter.chapter_id) : '',
    novelTitle: chapter?.novel_title ?? '',
    artwork: chapter?.source_overview_image_url,
    hasNextChapter: !!chapter?.next_chapter,
    onNextChapter: handleNextChapter,
    onPrefChange: <K extends keyof TtsPrefs>(key: K, value: TtsPrefs[K]) =>
      updateSetting(key, value as IReaderSettings[K]),
    highlightColors: ttsHighlightColors,
    topOffset: isMobile ? 0 : 64,
    bottomOffset: isMobile ? TTS_BAR_HEIGHT.mobile : TTS_BAR_HEIGHT.desktop,
  });

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (unavailableChapter) {
    return (
      <UnavailableChapter
        info={unavailableChapter}
        onNextAvailable={
          unavailableChapter.next_chapter != null
            ? () => navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${unavailableChapter.next_chapter}`)
            : undefined
        }
        onPrevious={
          unavailableChapter.prev_chapter != null
            ? () => navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${unavailableChapter.prev_chapter}`)
            : undefined
        }
        onChapterList={() => navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`)}
      />
    );
  }

  if (error || !chapter) {
    return (
      <Container>
        <Box sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || t('reader.notFound')}</Typography>
        </Box>
      </Container>
    );
  }

  // Update the rendering of reader controls based on mark read behavior
  const shouldShowMarkReadButton = isAuthenticated && 
    (readerSettings.markReadBehavior === 'button' || 
     readerSettings.markReadBehavior === 'buttonAutomatic');

  const toolbarElement = (
    <ReaderToolbar 
      isMobile={isMobile}
      controlsVisible={controlsVisible}
      title={getChapterLabel(t, chapter.title, chapter.chapter_id)}
      prevChapter={chapter.prev_chapter}
      nextChapter={chapter.next_chapter}
      isAuthenticated={isAuthenticated}
      markReadSuccess={markReadSuccess}
      markingAsRead={markingAsRead}
      showMarkReadButton={shouldShowMarkReadButton}
      onMarkAsRead={handleMarkAsRead}
      onChapterList={handleBackToChapters}
      onHome={handleBackToSource}
      onPrevious={handlePrevChapter}
      onNext={handleNextChapter}
      onSettings={() => setControlsVisible(true)}
      onListen={() => { setControlsVisible(false); tts.start(); }}
      onCloseControls={() => setControlsVisible(false)}
      prevUrl={prevUrl}
      nextUrl={nextUrl}
      homeUrl={homeUrl}
      chapterListUrl={chapterListUrl}
    />
  );

  return (
    <>
      <ChapterSEO chapter={chapter}></ChapterSEO>

      <>
      {toolbarElement}
      <Container 
        maxWidth="md" 
        sx={{
          padding: { xs: 0, md: 4 },
        }}
        {...swipeHandlers}
      >
        {/* Add breadcrumbs for desktop view only */}
        {!isMobile && (
          <BreadcrumbNav
            items={[
              {
                label: chapter.novel_title,
                icon: <BookIcon fontSize="inherit" />
              },
              {
                label: chapter.source_name,
                link: `/novels/${novelSlug}/${sourceSlug}`,
                icon: <LanguageIcon fontSize="inherit" />
              },
              {
                label: t('reader.chapters'),
                link: `/novels/${novelSlug}/${sourceSlug}/chapterlist`,
                icon: <ListAltIcon fontSize="inherit" />
              },
              {
                label: getChapterLabel(t, chapter.title, chapter.chapter_id),
                icon: <MenuBookIcon fontSize="inherit" />
              }
            ]}
          />
        )}
        
        <Paper 
          elevation={3} 
          sx={{ 
            p: { xs: 2, md: 4 }, 
            mt: 2, 
            mb: 8,
            backgroundColor: readerSettings.backgroundColor || undefined,
            color: readerSettings.fontColor || undefined,
            mx: `${readerSettings.margin}%`
          }}
        >
          {/* Chapter title and content */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom align="center" sx={{ color: readerSettings.fontColor || undefined }}>
              {getChapterLabel(t, chapter.title, chapter.chapter_id)}
            </Typography>
            <Typography variant="subtitle1" sx={{ color: 'text.secondary', textAlign: 'center' }}>
              {chapter.novel_title}
            </Typography>
          </Box>
          
          {/* Tab controls */}
          <Box sx={{ 
            borderBottom: 1, 
            borderColor: 'divider', 
            mb: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}>
            <Tabs value={activeTab} onChange={handleTabChange} aria-label={t('reader.chapters')}>
              <Tab label={t('reader.chapterTab')} id="tab-0" />
              <Tab 
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    {t('reader.commentsTab')}
                    <CommentIcon sx={{ ml: 1 }} />
                  </Box>
                } 
                id="tab-1" 
              />
            </Tabs>
            
            <Box sx={{ display: 'flex', alignItems: 'center' }}>
              <IconButton
                onClick={tts.start}
                aria-label={t('reader.listen')}
                sx={{ color: 'text.secondary', '&:hover': { color: 'primary.main' }, scale: '1.2' }}
              >
                <HeadphonesIcon />
              </IconButton>
              <IconButton 
                onClick={() => setControlsVisible(true)}
                aria-label={t('reader.openSettings')}
                sx={{ 
                  color: 'text.secondary',
                  '&:hover': {
                    color: 'primary.main'
                  },
                  scale: '1.2'
                }}
              >
                <SettingsIcon />
              </IconButton>
            </Box>
          </Box>
          
          {/* Chapter content Tab */}
          <Box role="tabpanel" hidden={activeTab !== 0} sx={{ mb: 4 }}>
            <ReaderViewport
              ref={contentRef}
              isMobile={isMobile}
              controlsVisible={controlsVisible}
              edgeTapWidthPercentage={EDGE_TAP_WIDTH_PERCENTAGE}
              dimLevel={readerSettings.dimLevel}
              nightMode={readerSettings.nightMode}
              nightModeStrength={readerSettings.nightModeStrength}
              nightModeScheduleEnabled={readerSettings.nightModeScheduleEnabled}
              nightModeStartTime={readerSettings.nightModeStartTime}
              nightModeEndTime={readerSettings.nightModeEndTime}
              leftEdgeTapBehavior={readerSettings.leftEdgeTapBehavior}
              rightEdgeTapBehavior={readerSettings.rightEdgeTapBehavior}
              onContentClick={handleContentClick}
            >
              {memoizedChapterContent.chapter && (
                <ReaderContent 
                  chapter={memoizedChapterContent.chapter} 
                  settings={memoizedChapterContent.settings}
                />
              )}
            </ReaderViewport>
          </Box>

          {/* Comments Tab */}
          <Box role="tabpanel" hidden={activeTab !== 1} sx={{ mb: 4 }}>
            {chapterDataForComments && activeTab === 1 && (
              <CommentSection 
                chapterData={chapterDataForComments}
                title={t('reader.chapterComments')}
              />
            )}
          </Box>
            
          {/* Reader Controls */}
          <ReaderControls
            prevChapter={chapter.prev_chapter}
            nextChapter={chapter.next_chapter}
            isAuthenticated={isAuthenticated && shouldShowMarkReadButton}
            markReadSuccess={markReadSuccess}
            markingAsRead={markingAsRead}
            onMarkAsRead={handleMarkAsRead}
            onPrevious={handlePrevChapter}
            onNext={handleNextChapter}
            onGoToComments={handleSwitchToComments}
            prevUrl={prevUrl}
            nextUrl={nextUrl}
          />
        </Paper>
      </Container>
      {tts.open && <Box sx={{ height: { xs: TTS_BAR_HEIGHT.mobile, sm: TTS_BAR_HEIGHT.desktop + 16 } }} />}
      </>

      {/* Settings Drawer */}
      <ReaderSettings
        open={controlsVisible}
        onClose={() => setControlsVisible(false)}
        settings={readerSettings}
        onSettingChange={handleSettingChange}
        novelLanguage={novelLanguage}
        onTtsBeforePreview={tts.pause}
        focusTts={settingsFocusTts}
        chapterInfo={{
          title: getChapterLabel(t, chapter.title, chapter.chapter_id),
          novelTitle: chapter.novel_title,
          prevChapter: chapter.prev_chapter,
          nextChapter: chapter.next_chapter
        }}
        onNavigate={handleSettingsNavigate}
        isAuthenticated={isAuthenticated}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        homeUrl={homeUrl}
      />

      {/* Add keyboard navigation handler */}
      <ReaderKeyboardNavigation 
        enabled={readerSettings.keyboardNavigation}
        onNextChapter={nonDefiniteHandleNextChapter}
        onPrevChapter={nonDefiniteHandlePrevChapter}
        controlsVisible={controlsVisible}
      />

      <TtsPlayerBar
        tts={tts}
        rate={readerSettings.ttsRate}
        onRateChange={rate => updateSetting('ttsRate', rate)}
        onOpenSettings={() => { setSettingsFocusTts(true); setControlsVisible(true); }}
        chapterTitle={getChapterLabel(t, chapter.title, chapter.chapter_id)}
      />
    </>
  );
};

export default ChapterReader;
