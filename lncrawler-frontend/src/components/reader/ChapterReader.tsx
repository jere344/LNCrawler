import { useState, useEffect, useRef, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useSwipeable } from 'react-swipeable';
import {
  Container,
  Typography,
  Paper,
  Box,
  CircularProgress,
  useMediaQuery,
  useTheme,
  Snackbar,
  Alert,
  Tabs,
  Tab,
  IconButton,
} from '@mui/material';
import { novelService, userService } from '../../services/api';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import CommentIcon from '@mui/icons-material/Comment';
import SettingsIcon from '@mui/icons-material/Settings';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import ReaderSettings, { ReaderSettings as IReaderSettings, defaultSettings, EdgeTapBehavior } from './ReaderSettings';
import Cookies from 'js-cookie';
import BreadcrumbNav from '../common/BreadcrumbNav';
import { useAuth } from '@context/AuthContext';

import ReaderToolbar from './controls/ReaderToolbar';
import ReaderViewport from './viewport/ReaderViewport';
import ReaderContent from './content/ReaderContent';
import PagedContent from './content/PagedContent';
import ReaderControls from './controls/ReaderControls';
import CommentSection from '../comments/CommentSection';
import { getChapterNameWithNumber } from '@utils/Misc';
import ReaderKeyboardNavigation from './controls/ReaderKeyboardNavigation';
import ChapterSEO from '@components/reader/ChapterSEO';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

// Interface for scroll position storage
interface ScrollPositions {
  [key: string]: number; // Value is percentage of total scrollable height
}

const COOKIE_PREFIX = 'lncrawler_reader_';
const EDGE_TAP_WIDTH_PERCENTAGE = 15; // % of screen width for edge tap detection
const MAX_STORED_POSITIONS = 20; // Maximum number of scroll positions to store
const SCROLL_POSITION_STORAGE_KEY = 'lncrawler_scroll_positions';
const SCROLL_SAVE_THROTTLE = 1000; // Save scroll position at most every 1000ms

const ChapterReader = () => {
  const { novelSlug, sourceSlug, chapterNumber } = useParams<{ 
    novelSlug: string; 
    sourceSlug: string; 
    chapterNumber: string 
  }>();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  
  const [chapter, setChapter] = useState<IChapterContent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [markingAsRead, setMarkingAsRead] = useState(false);
  const [markReadSuccess, setMarkReadSuccess] = useState(false);
  const [isScrollLocked, setIsScrollLocked] = useState(false);
  
  // Get authentication state to check if the user is logged in
  const { isAuthenticated } = useAuth();
  
  // Reader settings state
  const [readerSettings, setReaderSettings] = useState<IReaderSettings>(defaultSettings);
  const [controlsVisible, setControlsVisible] = useState(false);
  
  // Add state for active tab
  const [activeTab, setActiveTab] = useState(0);
  
  // Create a ref to store our chapter cache that persists through renders
  const chapterCacheRef = useRef<ChapterCache>({});
  const contentRef = useRef<HTMLDivElement>(null);
  const pagedContentRef = useRef<{
    goToNextPage: () => boolean;
    goToPrevPage: () => boolean;
    goToPage: (page: number) => void;
    currentPage: number;
  }>(null);
  
  // Use state for scroll positions loaded from localStorage
  const [scrollPositions, setScrollPositions] = useState<ScrollPositions>({});
  
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

  // Helper function to generate a cache key
  const getCacheKey = (novel: string, source: string, chapter: number): string => {
    return `${novel}|${source}|${chapter}`;
  };

  // Function to fetch chapter content
  const fetchChapterContent = async (novel: string, source: string, chapterNum: number): Promise<IChapterContent> => {
    const cacheKey = getCacheKey(novel, source, chapterNum);
    
    // Check if chapter exists in cache
    if (chapterCacheRef.current[cacheKey]) {
      return chapterCacheRef.current[cacheKey];
    }
    
    // If not in cache, fetch from API
    const response = await novelService.getChapterContent(novel, source, chapterNum);
    
    // Store in cache
    chapterCacheRef.current[cacheKey] = response;
    return response;
  };

  // Function to preload next chapter
  const preloadNextChapter = async (nextChapterNum: number) => {
    if (!novelSlug || !sourceSlug || !nextChapterNum) return;
    
    try {
      await fetchChapterContent(novelSlug, sourceSlug, nextChapterNum);
    } catch (err) {
      console.error(`Error preloading chapter ${nextChapterNum}:`, err);
    }
  };

  // Load saved settings from cookies
  useEffect(() => {
    const loadSettingsFromCookies = () => {
      const newSettings = { ...defaultSettings };
      let hasChanges = false;

      Object.keys(defaultSettings).forEach(keyStr => {
        const key = keyStr as keyof IReaderSettings; // Use keyof for type safety
        const cookieValue = Cookies.get(COOKIE_PREFIX + key);

        if (cookieValue !== undefined) {
          try {
            const parsedValue = JSON.parse(cookieValue);
            
            // Check if the parsed value's type matches the default setting's type
            if (typeof parsedValue === typeof defaultSettings[key]) {
              // @ts-ignore TypeScript might complain about assigning to newSettings[key] directly
              // but this is safe due to the type check and keyof IReaderSettings.
              newSettings[key] = parsedValue;
              hasChanges = true;
            } else {
              // Log a warning if types don't match, and use the default value
              console.warn(
                `Cookie for ${key} has incorrect type. Expected ${typeof defaultSettings[key]}, got ${typeof parsedValue}. Using default.`
              );
              // newSettings[key] already holds the default value from the initial spread
            }
          } catch (e) {
            // Log an error if parsing fails, and use the default value
            console.error(`Error parsing cookie value for ${key}. Using default.`, e);
            // newSettings[key] already holds the default value
          }
        }
      });

      if (hasChanges) {
        setReaderSettings(newSettings);
      }
    };

    loadSettingsFromCookies();
  }, []);

  // Load saved scroll positions from localStorage
  useEffect(() => {
    try {
      const savedPositions = localStorage.getItem(SCROLL_POSITION_STORAGE_KEY);
      if (savedPositions) {
        setScrollPositions(JSON.parse(savedPositions));
      }
    } catch (error) {
      console.error('Error loading saved scroll positions:', error);
    }
  }, []);

  // Add a ref to track the last time we saved the scroll position
  const lastScrollSaveRef = useRef<number>(0);
  
  // Calculate scroll position as a percentage of total scrollable height
  const calculateScrollPercentage = (): number => {
    const scrollTop = window.scrollY;
    const scrollHeight = document.documentElement.scrollHeight;
    const clientHeight = document.documentElement.clientHeight;
    
    // If there's nothing to scroll, return 0
    if (scrollHeight <= clientHeight) return 0;
    
    // Calculate how far we've scrolled as a percentage
    const scrollableHeight = scrollHeight - clientHeight;
    return (scrollTop / scrollableHeight) * 100;
  };

  // Save current scroll position to localStorage with throttling
  const saveScrollPosition = () => {
    if (!currentChapterKey || !readerSettings.savePosition) return;
    
    const now = Date.now();
    // Throttle saves to avoid excessive writes
    if (now - lastScrollSaveRef.current < SCROLL_SAVE_THROTTLE) {
      return;
    }
    lastScrollSaveRef.current = now;

    let updatedPositions: ScrollPositions;
    // if we are in page mode we save the page number
    if (readerSettings.pageMode && pagedContentRef.current) {
      const currentPage = pagedContentRef.current.currentPage;
      updatedPositions = { ...scrollPositions, [currentChapterKey]: currentPage };
    }
    else {
      const scrollPercentage = calculateScrollPercentage();
      updatedPositions = { ...scrollPositions, [currentChapterKey]: scrollPercentage };
    }
    
    // Prune old entries if we have too many
    const keys = Object.keys(updatedPositions);
    if (keys.length > MAX_STORED_POSITIONS) {
      // Remove the oldest entries
      const keysToRemove = keys.slice(0, keys.length - MAX_STORED_POSITIONS);
      keysToRemove.forEach(key => {
        delete updatedPositions[key];
      });
    }
    
    // Save to state and localStorage
    setScrollPositions(updatedPositions);
    try {
      // Use requestAnimationFrame to batch DOM reads/writes
      requestAnimationFrame(() => {
        localStorage.setItem(SCROLL_POSITION_STORAGE_KEY, JSON.stringify(updatedPositions));
      });
    } catch (error) {
      console.error('Error saving scroll position to localStorage:', error);
    }
  };

  // Restore scroll position from percentage using requestAnimationFrame
  const restoreScrollPosition = () => {
    if (!currentChapterKey || !readerSettings.savePosition) return;
    
    const savedPercentage = scrollPositions[currentChapterKey];
    if (savedPercentage !== undefined) {
      

      // Use requestAnimationFrame to avoid layout thrashing
      requestAnimationFrame(() => {
        // If in page mode, restore to the correct page (we simply stored the page number)  
        if (readerSettings.pageMode && pagedContentRef.current) {
        pagedContentRef.current.goToPage(savedPercentage); // This is actually the page number
        return;
      }
        // Read scroll dimensions
        const scrollHeight = document.documentElement.scrollHeight;
        const clientHeight = document.documentElement.clientHeight;
        const scrollableHeight = scrollHeight - clientHeight;
        
        if (scrollableHeight <= 0) {
          // Try again later if content hasn't fully rendered
          setTimeout(() => restoreScrollPosition(), 100);
          return;
        }
        
        const scrollTop = (savedPercentage / 100) * scrollableHeight;
        
        // Write to scroll position in next frame
        requestAnimationFrame(() => {
          window.scrollTo({
            top: scrollTop,
            behavior: 'auto' // Use 'auto' instead of 'smooth' to avoid animation issues
          });
        });
      });
    }
  };

  useEffect(() => {
    const loadCurrentChapter = async () => {
      if (!novelSlug || !sourceSlug || !chapterNumber) return;
      
      setLoading(true);
      try {
        const chapterData = await fetchChapterContent(
          novelSlug, 
          sourceSlug, 
          parseInt(chapterNumber)
        );
        setChapter(chapterData);
        
        // Preload next chapter if it exists
        if (chapterData.next_chapter) {
          preloadNextChapter(chapterData.next_chapter);
        }
      } catch (err) {
        console.error('Error fetching chapter content:', err);
        setError('Failed to load chapter content. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    loadCurrentChapter();
  }, [novelSlug, sourceSlug, chapterNumber]);

  // Restore scroll position when chapter content is loaded
  useEffect(() => {
    if (!loading && chapter) {
      restoreScrollPosition();
    }
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
      saveScrollPosition(); // Save one last time when component unmounts
    };
  }, [chapter, loading, readerSettings.savePosition, currentChapterKey]);

  const handleBackToChapters = () => {
    saveScrollPosition();
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleBackToSource = () => {
    saveScrollPosition();
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };
  
  // Add this function to handle automatic marking as read when navigating
  const handleChapterNavigation = async (direction: 'prev' | 'next') => {
    // Save current scroll position
    saveScrollPosition();
    
    // Get the chapter number to navigate to
    const targetChapter = direction === 'next' 
      ? chapter?.next_chapter 
      : chapter?.prev_chapter;
    
    if (!targetChapter) return;
    
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
    
    // Navigate to the target chapter
    setActiveTab(0);
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${targetChapter}`);
  };

  const nonDefiniteHandleNextChapter = () => {
    // Handle page mode navigation
    if (readerSettings.pageMode && pagedContentRef.current) {
      const movedToNextPage = pagedContentRef.current.goToNextPage();
      if (movedToNextPage) {
        return; // Successfully moved to next page
      }
      // If we're on the last page, fall through to next chapter
    }
    
    // Original chapter navigation
    if (chapter?.next_chapter) {
      handleChapterNavigation('next');
    }
  }

  const nonDefiniteHandlePrevChapter = () => {
    // Handle page mode navigation
    if (readerSettings.pageMode && pagedContentRef.current) {
      const movedToPrevPage = pagedContentRef.current.goToPrevPage();
      if (movedToPrevPage) {
        return; // Successfully moved to previous page
      }
      // If we're on the first page, fall through to previous chapter
    }
    
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
    if (!isMobile) return;
    
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
    const tapX = e.nativeEvent.offsetX;
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
    readerSettings.showPages,
    readerSettings.showPageSlider,
  ]);

  // Handler for scroll lock changes
  const handleScrollLockChange = (locked: boolean) => {
    setIsScrollLocked(locked);
  };

  // Add these variables to generate navigation URLs
  const prevUrl = chapter?.prev_chapter ? `/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.prev_chapter}` : undefined;
  const nextUrl = chapter?.next_chapter ? `/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.next_chapter}` : undefined;
  const homeUrl = novelSlug && sourceSlug ? `/novels/${novelSlug}/${sourceSlug}` : undefined;
  const chapterListUrl = novelSlug && sourceSlug ? `/novels/${novelSlug}/${sourceSlug}/chapterlist` : undefined;

  // Handle swipe gestures
  const handleSwipeLeft = () => {
    const gesture = readerSettings.swipeLeftGesture;
    switch (gesture) {
      case 'nextChapter':
        if (chapter?.next_chapter) {
          nonDefiniteHandleNextChapter();
        }
        break;
      case 'prevChapter':
        nonDefiniteHandlePrevChapter();
        break;
      case 'none':
      default:
        // Do nothing
        break;
    }
  };

  const handleSwipeRight = () => {
    const gesture = readerSettings.swipeRightGesture;
    switch (gesture) {
      case 'prevChapter':
        nonDefiniteHandlePrevChapter();
        break;
      case 'nextChapter':
        nonDefiniteHandleNextChapter();
        break;
      case 'none':
      default:
        // Do nothing
        break;
    }
  };

  // Handle swipe gestures - simplified for non-page mode
  const handleGesture = (direction: 'left' | 'right') => {
    if (!isMobile || !chapter || controlsVisible) return;
    if (direction === 'left') {
      handleSwipeLeft();
    } else {
      handleSwipeRight();
    }
  };
  
  // Configure swipe handlers
  const swipeHandlers = useSwipeable({
    onSwipedLeft: () => handleGesture('left'),
    onSwipedRight: () => handleGesture('right'),
    trackMouse: false,
    preventScrollOnSwipe: false,
    // Only detect wider/more intentional swipes to prevent accidental activation
    delta: 50,
    swipeDuration: 500,
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

  if (error || !chapter) {
    return (
      <Container>
        <Box sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || 'Chapter not found'}</Typography>
        </Box>
      </Container>
    );
  }

  // Update the rendering of reader controls based on mark read behavior
  const shouldShowMarkReadButton = isAuthenticated && 
    (readerSettings.markReadBehavior === 'button' || 
     readerSettings.markReadBehavior === 'buttonAutomatic');

  return (
    <>
      <ChapterSEO chapter={chapter}></ChapterSEO>

      {/* Reader Toolbar */}
      <ReaderToolbar 
        isMobile={isMobile}
        controlsVisible={controlsVisible}
        title={getChapterNameWithNumber(chapter.title, chapter.chapter_id)}
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
        onCloseControls={() => setControlsVisible(false)}
        prevUrl={prevUrl}
        nextUrl={nextUrl}
        homeUrl={homeUrl}
        chapterListUrl={chapterListUrl}
      />

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
                link: `/novels/${novelSlug}`,
                icon: <BookIcon fontSize="inherit" />
              },
              {
                label: chapter.source_name,
                link: `/novels/${novelSlug}/${sourceSlug}`,
                icon: <LanguageIcon fontSize="inherit" />
              },
              {
                label: "Chapters",
                link: `/novels/${novelSlug}/${sourceSlug}/chapterlist`,
                icon: <ListAltIcon fontSize="inherit" />
              },
              {
                label: getChapterNameWithNumber(chapter.title, chapter.chapter_id),
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
              {getChapterNameWithNumber(chapter.title, chapter.chapter_id)}
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
            <Tabs value={activeTab} onChange={handleTabChange} aria-label="chapter tabs">
              <Tab label="Chapter" id="tab-0" />
              <Tab 
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    Comments
                    <CommentIcon sx={{ ml: 1 }} />
                  </Box>
                } 
                id="tab-1" 
              />
            </Tabs>
            
            <IconButton 
              onClick={() => setControlsVisible(true)}
              aria-label="Open reader settings"
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
                readerSettings.pageMode ? (
                  <PagedContent
                    ref={pagedContentRef}
                    chapter={memoizedChapterContent.chapter}
                    settings={memoizedChapterContent.settings}
                    isScrollLocked={isScrollLocked}
                    onScrollLockChange={handleScrollLockChange}
                    saveScrollPosition={saveScrollPosition}
                  />
                ) : (
                  <ReaderContent 
                    chapter={memoizedChapterContent.chapter} 
                    settings={memoizedChapterContent.settings}
                  />
                )
              )}
            </ReaderViewport>
          </Box>

          {/* Comments Tab */}
          <Box role="tabpanel" hidden={activeTab !== 1} sx={{ mb: 4 }}>
            {chapterDataForComments && activeTab === 1 && (
              <CommentSection 
                chapterData={chapterDataForComments}
                title="Chapter Comments"
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

          {/* Success Notification */}
          <Snackbar 
            open={markReadSuccess} 
            autoHideDuration={3000} 
            onClose={() => setMarkReadSuccess(false)}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}
          >
            <Alert onClose={() => setMarkReadSuccess(false)} severity="success" sx={{ width: '100%' }}>
              Chapter marked as read successfully!
            </Alert>
          </Snackbar>
        </Paper>
      </Container>

      {/* Settings Drawer */}
      <ReaderSettings
        open={controlsVisible}
        onClose={() => setControlsVisible(false)}
        settings={readerSettings}
        onSettingChange={setReaderSettings}
        chapterInfo={{
          title: getChapterNameWithNumber(chapter.title, chapter.chapter_id),
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
    </>
  );
};

export default ChapterReader;
