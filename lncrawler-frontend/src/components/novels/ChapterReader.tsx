import { useState, useEffect } from 'react';
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
  AppBar
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';
import FormatSizeIcon from '@mui/icons-material/FormatSize';
import HomeIcon from '@mui/icons-material/Home';
import ListIcon from '@mui/icons-material/List';

interface ChapterContent {
  id: string;
  chapter_id: number;
  title: string;
  novel_title: string;
  novel_id: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  body: string;
  prev_chapter?: { chapter_id: number } | null;
  next_chapter?: { chapter_id: number } | null;
}

const ChapterReader = () => {
  const { novelSlug, sourceSlug, chapterNumber } = useParams<{ 
    novelSlug: string; 
    sourceSlug: string; 
    chapterNumber: string 
  }>();
  const navigate = useNavigate();
  
  const [chapter, setChapter] = useState<ChapterContent | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [fontSize, setFontSize] = useState<number>(18);
  
  useEffect(() => {
    const fetchChapterContent = async () => {
      if (!novelSlug || !sourceSlug || !chapterNumber) return;
      
      setLoading(true);
      try {
        const response = await novelService.getChapterContent(
          novelSlug, 
          sourceSlug, 
          parseInt(chapterNumber)
        );
        setChapter(response);
      } catch (err) {
        console.error('Error fetching chapter content:', err);
        setError('Failed to load chapter content. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchChapterContent();
  }, [novelSlug, sourceSlug, chapterNumber]);

  const handleBackToChapters = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapterlist`);
  };

  const handleBackToSource = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };

  const handleBackToNovel = () => {
    navigate(`/novels/${novelSlug}`);
  };

  const handleNextChapter = () => {
    if (chapter?.next_chapter) {
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.next_chapter.chapter_id}`);
    }
  };

  const handlePrevChapter = () => {
    if (chapter?.prev_chapter) {
      navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.prev_chapter.chapter_id}`);
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
          <Box sx={{ mb: 3 }}>
            <Typography variant="h5" gutterBottom align="center">
              {chapter.title}
            </Typography>
            <Typography variant="subtitle1" color="text.secondary" align="center">
              {chapter.novel_title}
            </Typography>
          </Box>
          
          <Divider sx={{ mb: 4 }} />
          
          <Box sx={{ mb: 4 }}>
            <Typography 
              sx={{ 
                fontSize: `${fontSize}px`, 
                lineHeight: 1.6,
                textAlign: 'justify'
              }}
              dangerouslySetInnerHTML={{ __html: chapter.body }}
            />
          </Box>
          
          <Divider sx={{ mt: 4, mb: 2 }} />
          
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
