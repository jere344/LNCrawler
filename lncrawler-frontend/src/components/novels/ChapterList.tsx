import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Box,
  Button,
  CircularProgress,
  Divider,
  TextField,
  InputAdornment
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SearchIcon from '@mui/icons-material/Search';

interface Chapter {
  id: string;
  chapter_id: number;
  title: string;
  url: string;
  volume: number;
  volume_title: string | null;
  has_content: boolean;
}

interface ChapterListResponse {
  novel_id: string;
  novel_title: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  chapters: Chapter[];
}

const ChapterList = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const navigate = useNavigate();
  
  const [chapterData, setChapterData] = useState<ChapterListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');
  
  // Organize chapters by volume
  const [volumeChapters, setVolumeChapters] = useState<{ [key: number]: Chapter[] }>({});
  const [volumes, setVolumes] = useState<number[]>([]);
  
  useEffect(() => {
    const fetchChapters = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      try {
        const response = await novelService.getNovelChapters(novelSlug, sourceSlug);
        setChapterData(response);
        
        // Organize chapters by volume
        const chaptersByVolume: { [key: number]: Chapter[] } = {};
        const volumeList: Set<number> = new Set();
        
        response.chapters.forEach((chapter: Chapter) => {
          const volume = chapter.volume || 0;
          volumeList.add(volume);
          
          if (!chaptersByVolume[volume]) {
            chaptersByVolume[volume] = [];
          }
          chaptersByVolume[volume].push(chapter);
        });
        
        setVolumeChapters(chaptersByVolume);
        setVolumes(Array.from(volumeList).sort((a, b) => a - b));
        
      } catch (err) {
        console.error('Error fetching chapters:', err);
        setError('Failed to load chapters. Please try again later.');
      } finally {
        setLoading(false);
      }
    };

    fetchChapters();
  }, [novelSlug, sourceSlug]);

  const handleBackClick = () => {
    if (chapterData) {
      navigate(`/novels/${novelSlug}/${sourceSlug}`);
    } else {
      navigate('/novels');
    }
  };

  const handleChapterClick = (chapterNumber: number) => {
    navigate(`/novels/${novelSlug}/${sourceSlug}/chapter/${chapterNumber}`);
  };

  const filteredVolumes = Object.entries(volumeChapters).reduce((acc: { [key: number]: Chapter[] }, [volume, chapters]) => {
    const filteredChapters = chapters.filter(chapter => 
      chapter.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      chapter.chapter_id.toString().includes(searchTerm)
    );
    
    if (filteredChapters.length > 0) {
      acc[Number(volume)] = filteredChapters;
    }
    
    return acc;
  }, {});

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 8 }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error || !chapterData) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/novels')} sx={{ mt: 2 }}>
          Back to Novels
        </Button>
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center', mt: 3 }}>
          <Typography color="error">{error || 'Chapters not found'}</Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="md">
      <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
        Back to Source
      </Button>

      <Paper elevation={3} sx={{ p: 3, mt: 2 }}>
        <Typography variant="h4" gutterBottom>
          {chapterData.novel_title}
        </Typography>
        
        <Typography variant="subtitle1" color="text.secondary" gutterBottom>
          Source: {chapterData.source_name}
        </Typography>
        
        <Box sx={{ mt: 3, mb: 2 }}>
          <TextField
            fullWidth
            placeholder="Search chapters..."
            variant="outlined"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <SearchIcon />
                </InputAdornment>
              ),
            }}
          />
        </Box>
        
        <Typography variant="subtitle1" gutterBottom sx={{ mt: 3 }}>
          {chapterData.chapters.length} Chapters
        </Typography>
        
        {volumes.length > 0 ? (
          volumes.map(volume => {
            if (!filteredVolumes[volume] || filteredVolumes[volume].length === 0) return null;
            
            const volumeTitle = filteredVolumes[volume][0].volume_title || `Volume ${volume === 0 ? 'Unknown' : volume}`;
            
            return (
              <Box key={volume} sx={{ mb: 4 }}>
                <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>
                  {volumeTitle}
                </Typography>
                <Divider sx={{ mb: 2 }} />
                
                <List disablePadding>
                  {filteredVolumes[volume].map((chapter) => (
                    <ListItem disablePadding key={chapter.id} divider>
                      <ListItemButton 
                        onClick={() => handleChapterClick(chapter.chapter_id)}
                        disabled={!chapter.has_content}
                        sx={{
                          opacity: chapter.has_content ? 1 : 0.5,
                          '&.Mui-disabled': {
                            opacity: 0.5,
                          }
                        }}
                      >
                        <ListItemText 
                          primary={chapter.title} 
                          secondary={!chapter.has_content ? 'Content unavailable' : null}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              </Box>
            );
          })
        ) : (
          <Typography variant="body1" sx={{ textAlign: 'center', py: 4 }}>
            No chapters available.
          </Typography>
        )}
      </Paper>
    </Container>
  );
};

export default ChapterList;
