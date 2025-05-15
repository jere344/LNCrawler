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
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import FormatSizeIcon from '@mui/icons-material/FormatSize';
import HomeIcon from '@mui/icons-material/Home';
import ListIcon from '@mui/icons-material/List';
import CommentIcon from '@mui/icons-material/Comment';
import CommentSection from '../comments/CommentSection';
import { ChapterContent as IChapterContent } from '@models/novels_types';

// Interface for our chapter cache
interface ChapterCache {
  [key: string]: IChapterContent;
}

const ChapterReader = () => {
  const { novelSlug, sourceSlug, chapterNumber } = useParams<{ 
    novelSlug: string; 
    sourceSlug: string; 
    chapterNumber: string 
  }>();
  const navigate = useNavigate();
  
  const [chapter, setChapter] = useState<IChapterContent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [fontSize, setFontSize] = useState<number>(18);
  const [activeTab, setActiveTab] = useState(0);
  const [commentsLoaded, setCommentsLoaded] = useState(false);
  
  // Create a ref to store our chapter cache that persists through renders
  const chapterCacheRef = useRef<ChapterCache>({});

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

  const handleTabChange = (_event: React.SyntheticEvent, newValue: number) => {
    setActiveTab(newValue);
    
    // Load comments only when switching to the comments tab for the first time
    if (newValue === 1 && !commentsLoaded) {
      setCommentsLoaded(true);
    }
  };

  const handleBackToChapters = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleBackToSource = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };
  
  const handleNextChapter = () => {
    if (chapter?.next_chapter) {
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.next_chapter}`);
    }
  };

  const handlePrevChapter = () => {
    if (chapter?.prev_chapter) {
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.prev_chapter}`);
    }
  };

  const increaseFontSize = () => {
    setFontSize(prevSize => Math.min(prevSize + 2, 28));
  };

  const decreaseFontSize = () => {
    setFontSize(prevSize => Math.max(prevSize - 2, 12));
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
            
            <Typography variant="h6" sx={{ flexGrow: 0, textAlign: 'center', fontSize: { xs: '0.9rem', sm: '1.25rem' }, mx: 2 }}>
              {chapter.title}
            </Typography>
            
            {chapter.next_chapter && (
              <IconButton color="inherit" onClick={handleNextChapter}>
                <ArrowForwardIcon />
              </IconButton>
            )}
          </Box>
          
          <Box>
            <IconButton onClick={decreaseFontSize} color="inherit">
              <FormatSizeIcon fontSize="small" />
            </IconButton>
            <IconButton onClick={increaseFontSize} color="inherit">
              <FormatSizeIcon fontSize="large" />
            </IconButton>
          </Box>
        </Toolbar>
      </AppBar>

      <Container maxWidth="md">
        <Paper elevation={3} sx={{ p: { xs: 2, md: 4 }, mt: 2, mb: 8 }}>
          {/* Chapter title and content */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom align="center">
              {chapter.title}
            </Typography>
            <Typography variant="subtitle1" color="text.secondary" align="center">
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
                fontSize: `${fontSize}px`, 
                lineHeight: 1.6,
                textAlign: 'justify'
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
      </Container>
    </>
  );
};

export default ChapterReader;
