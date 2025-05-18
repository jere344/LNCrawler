import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Paper,
  Box,
  Button,
  CircularProgress,
  Divider,
  IconButton,
  Toolbar,
  AppBar,
  Tabs,
  Tab,
  useMediaQuery,
  useTheme,
  Slide,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import HomeIcon from '@mui/icons-material/Home';
import ListIcon from '@mui/icons-material/List';
import CommentIcon from '@mui/icons-material/Comment';
import SettingsIcon from '@mui/icons-material/Settings';
import CommentSection from '../comments/CommentSection';
import { ChapterContent as IChapterContent } from '@models/novels_types';
import ReaderSettings, { ReaderSettings as IReaderSettings, defaultSettings, EdgeTapBehavior } from './ReaderSettings';
import Cookies from 'js-cookie';
import CloseIcon from '@mui/icons-material/Close';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

// Interface for scroll position storage
interface ScrollPositions {
  [key: string]: number;
}

const COOKIE_PREFIX = 'lncrawler_reader_';
const EDGE_TAP_WIDTH_PERCENTAGE = 15; // % of screen width for edge tap detection
const MAX_STORED_POSITIONS = 20; // Maximum number of scroll positions to store

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
  const [activeTab, setActiveTab] = useState(0);
  const [commentsLoaded, setCommentsLoaded] = useState(false);
  
  // Reader settings state
  const [readerSettings, setReaderSettings] = useState<IReaderSettings>(defaultSettings);
  const [controlsVisible, setControlsVisible] = useState(false);
  
  // Create a ref to store our chapter cache that persists through renders
  const chapterCacheRef = useRef<ChapterCache>({});
  const contentRef = useRef<HTMLDivElement>(null);
  
  // Create a ref to store scroll positions for different chapters
  const scrollPositionsRef = useRef<ScrollPositions>({});
  
  // Current chapter key for scroll position tracking
  const currentChapterKey = `${novelSlug}|${sourceSlug}|${chapterNumber}`;

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

      Object.keys(defaultSettings).forEach(key => {
        const cookieValue = Cookies.get(COOKIE_PREFIX + key);
        if (cookieValue !== undefined) {
          try {
            const parsedValue = JSON.parse(cookieValue);
            // @ts-ignore
            newSettings[key] = parsedValue;
            hasChanges = true;
          } catch (e) {
            console.error(`Error parsing cookie value for ${key}`, e);
          }
        }
      });

      if (hasChanges) {
        setReaderSettings(newSettings);
      }
    };

    loadSettingsFromCookies();
  }, []);

  // Save current scroll position
  const saveScrollPosition = () => {
    if (!currentChapterKey || !readerSettings.savePosition) return;
    scrollPositionsRef.current[currentChapterKey] = window.scrollY;
    
    // Prune old entries if we have too many
    const keys = Object.keys(scrollPositionsRef.current);
    if (keys.length > MAX_STORED_POSITIONS) {
      // Remove the oldest entries
      const keysToRemove = keys.slice(0, keys.length - MAX_STORED_POSITIONS);
      keysToRemove.forEach(key => {
        delete scrollPositionsRef.current[key];
      });
    }
  };

  // Restore scroll position
  const restoreScrollPosition = () => {
    if (!currentChapterKey || !readerSettings.savePosition) return;
    
    const savedPosition = scrollPositionsRef.current[currentChapterKey];
    if (savedPosition !== undefined) {
      // Use setTimeout to ensure the DOM has been fully rendered
      window.scrollTo(0, savedPosition);
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

  // Save scroll position when component unmounts
  useEffect(() => {
    return () => {
      saveScrollPosition();
    };
  }, []);

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    
    // Load comments only when switching to the comments tab for the first time
    if (newValue === 1 && !commentsLoaded) {
      setCommentsLoaded(true);
    }
  };

  const handleBackToChapters = () => {
    saveScrollPosition();
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleBackToSource = () => {
    saveScrollPosition();
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };
  
  const handleNextChapter = () => {
    if (chapter?.next_chapter) {
      saveScrollPosition();
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.next_chapter}`);
    }
  };

  const handlePrevChapter = () => {
    if (chapter?.prev_chapter) {
      saveScrollPosition();
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.prev_chapter}`);
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

  // Function to handle edge taps
  const handleEdgeTap = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!isMobile) return;
    if (controlsVisible) return; // Don't handle edge taps when controls are visible

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

    // If tap is in the middle, toggle controls
    setControlsVisible(!controlsVisible);
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
        if (edge === 'left' && chapter?.prev_chapter) {
          handlePrevChapter();
        } else if (edge === 'right' && chapter?.next_chapter) {
          handleNextChapter();
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
    handleEdgeTap(e);
  };

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
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate(-1)} sx={{ mt: 2 }}>
          Back
        </Button>
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || 'Chapter not found'}</Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <>
      {/* Desktop Toolbar */}
      {!isMobile && (
        <AppBar position="sticky" color="default" elevation={1} sx={{ top: 0 }}>
          <Toolbar>
            <IconButton edge="start" color="inherit" onClick={handleBackToChapters}>
              <ListIcon />
            </IconButton>
            <IconButton color="inherit" onClick={handleBackToSource}>
              <HomeIcon />
            </IconButton>
            
            <Box sx={{ flexGrow: 1, display: 'flex', justifyContent: 'center' }}>
              {chapter.prev_chapter && (
                <IconButton color="inherit" onClick={handlePrevChapter}>
                  <ArrowBackIcon />
                </IconButton>
              )}
              
              <Typography variant="h6" sx={{ flexGrow: 0, textAlign: 'center', fontSize: { sm: '1.25rem' }, mx: 2 }}>
                {chapter.title}
              </Typography>
              
              {chapter.next_chapter && (
                <IconButton color="inherit" onClick={handleNextChapter}>
                  <ArrowForwardIcon />
                </IconButton>
              )}
            </Box>
            
            <IconButton color="inherit" onClick={() => setControlsVisible(true)}>
              <SettingsIcon />
            </IconButton>
          </Toolbar>
        </AppBar>
      )}

      {/* Mobile Top Controls */}
      {isMobile && (
        <Slide direction="down" in={controlsVisible} mountOnEnter unmountOnExit>
          <AppBar 
            position="fixed" 
            color="default" 
            elevation={4} 
            sx={{ 
              top: 0,
              zIndex: theme.zIndex.drawer + 1,
              backgroundColor: theme.palette.background.paper,
              borderBottom: `1px solid ${theme.palette.divider}`,
              backdropFilter: 'blur(8px)',
              boxShadow: 3
            }}
          >
            <Toolbar sx={{ justifyContent: 'space-between' }}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <IconButton edge="start" color="inherit" onClick={handleBackToChapters} sx={{ mr: 1 }}>
                  <ListIcon />
                </IconButton>
                <IconButton color="inherit" onClick={handleBackToSource}>
                  <HomeIcon />
                </IconButton>
              </Box>
              
              <Typography 
                variant="subtitle1" 
                noWrap 
                sx={{ 
                  fontWeight: 'medium',
                  maxWidth: 'calc(100% - 160px)',
                  textAlign: 'center'
                }}
              >
                {chapter.title}
              </Typography>
              
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <IconButton color="inherit" onClick={() => setControlsVisible(false)}>
                  <CloseIcon />
                </IconButton>
              </Box>
            </Toolbar>
          </AppBar>
        </Slide>
      )}

      <Container 
        maxWidth="md" 
        sx={{
          padding: { xs: 0, md: 4 },
        }}
      >
        <Box
          ref={contentRef}
          onClick={handleContentClick}
          sx={{
            minHeight: 'calc(100vh - 64px)',
            position: 'relative',
            // Display overlay indicators for edge tap zones on mobile
            '&::before, &::after': isMobile ? {
              content: '""',
              position: 'fixed',
              top: 0,
              bottom: 0,
              width: `${EDGE_TAP_WIDTH_PERCENTAGE}%`,
              backgroundColor: 'rgba(0, 0, 0, 0.05)',
              zIndex: 0,
              pointerEvents: 'none',
              opacity: controlsVisible ? 1 : 0,
              transition: 'opacity 0.3s ease'
            } : {},
            '&::before': isMobile ? {
              left: 0,
              borderRight: '1px dashed rgba(0, 0, 0, 0.2)'
            } : {},
            '&::after': isMobile ? {
              right: 0,
              borderLeft: '1px dashed rgba(0, 0, 0, 0.2)'
            } : {}
          }}
        >
          {/* Dimming Overlay */}
          {readerSettings.dimLevel > 0 && (
            <Box
              sx={{
                position: 'fixed',
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                backgroundColor: 'black',
                opacity: readerSettings.dimLevel / 100,
                zIndex: theme.zIndex.drawer - 1,
                pointerEvents: 'none', // Allows clicking through the overlay
              }}
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
                {chapter.title}
              </Typography>
              <Typography variant="subtitle1" sx={{ color: 'text.secondary', textAlign: 'center' }}>
                {chapter.novel_title}
              </Typography>
            </Box>
            
            <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
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
            </Box>
            
            {/* Chapter content Tab */}
            <Box role="tabpanel" hidden={activeTab !== 0} sx={{ mb: 4 }}>
              <Typography 
                sx={{ 
                  fontSize: `${readerSettings.fontSize}px`, 
                  lineHeight: readerSettings.lineSpacing,
                  textAlign: readerSettings.textAlign,
                  fontFamily: readerSettings.fontFamily || undefined,
                  userSelect: readerSettings.textSelectable ? 'text' : 'none',
                  WebkitUserSelect: readerSettings.textSelectable ? 'text' : 'none',
                  MozUserSelect: readerSettings.textSelectable ? 'text' : 'none',
                  msUserSelect: readerSettings.textSelectable ? 'text' : 'none',
                }}
                dangerouslySetInnerHTML={{ __html: chapter.body }}
              />
            </Box>
            
            {/* Comments Tab */}
            <Box role="tabpanel" hidden={activeTab !== 1} sx={{ mb: 4 }}>
              {novelSlug && sourceSlug && chapterNumber && activeTab === 1 && (
                <CommentSection 
                  chapterData={{
                    novelSlug,
                    sourceSlug,
                    chapterNumber: parseInt(chapterNumber)
                  }}
                  title="Chapter Comments"
                />
              )}
            </Box>
            
            <Divider sx={{ mt: 4, mb: 2 }} />
            
            {/* Navigation buttons */}
            <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
              {chapter.prev_chapter ? (
                <Button 
                  startIcon={<ArrowBackIcon />} 
                  onClick={handlePrevChapter}
                  variant="outlined"
                >
                  Previous Chapter
                </Button>
              ) : <div></div>}
              
              {chapter.next_chapter && (
                <Button 
                  endIcon={<ArrowForwardIcon />} 
                  onClick={handleNextChapter}
                  variant="contained"
                >
                  Next Chapter
                </Button>
              )}
            </Box>
          </Paper>
        </Box>
      </Container>

      {/* Settings Drawer */}
      <ReaderSettings
        open={isMobile ? controlsVisible : controlsVisible}
        onClose={() => setControlsVisible(false)}
        settings={readerSettings}
        onSettingChange={setReaderSettings}
        chapterInfo={{
          title: chapter.title,
          novelTitle: chapter.novel_title,
          prevChapter: chapter.prev_chapter,
          nextChapter: chapter.next_chapter
        }}
        onNavigate={handleSettingsNavigate}
      />
    </>
  );
};

export default ChapterReader;
