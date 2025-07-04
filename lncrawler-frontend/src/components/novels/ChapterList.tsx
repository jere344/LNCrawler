import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
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
  InputAdornment,
  Pagination,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Stack,
  SelectChangeEvent,
  Grid2 as Grid,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import SearchIcon from '@mui/icons-material/Search';
import { Chapter, ChapterListResponse as IChapterListResponse } from '@models/novels_types';
import BreadcrumbNav from '../common/BreadcrumbNav';
import BookIcon from '@mui/icons-material/Book';
import LanguageIcon from '@mui/icons-material/Language';
import ListAltIcon from '@mui/icons-material/ListAlt';
import { getChapterNameWithNumber } from '@utils/Misc';

const DEFAULT_OG_IMAGE = '/og-image.jpg';

interface IExtendedChapterListResponse extends IChapterListResponse {
  count: number;
  total_pages: number;
  current_page: number;
}

const ChapterList = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  
  const [chapterData, setChapterData] = useState<IExtendedChapterListResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(100);
  
  // Organize chapters by volume
  const [volumeChapters, setVolumeChapters] = useState<{ [key: number]: Chapter[] }>({});
  const [volumes, setVolumes] = useState<number[]>([]);
  
  useEffect(() => {
    const fetchChapters = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      try {
        const response = await novelService.getNovelChapters(novelSlug, sourceSlug, page, pageSize);
        setChapterData(response as IExtendedChapterListResponse);
        
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
  }, [novelSlug, sourceSlug, page, pageSize]);

  const handlePageChange = (_event: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
  };

  const handlePageSizeChange = (event: SelectChangeEvent<number>) => {
    setPageSize(Number(event.target.value));
    setPage(1);
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

  const pageUrl = window.location.href;
  const siteName = "LNCrawler";

  const metaTitle = chapterData 
    ? `Chapter List - ${chapterData.novel_title} (${chapterData.source_name}) | ${siteName}` 
    : `Loading Chapters | ${siteName}`;
  const metaDescription = chapterData 
    ? `Browse all ${chapterData.count} chapters for ${chapterData.novel_title} from source ${chapterData.source_name} on ${siteName}. Find the chapter you want to read.`
    : `Loading chapter list. Discover light novels on ${siteName}.`;
  const metaKeywords = chapterData 
    ? `${chapterData.novel_title}, ${chapterData.source_name}, chapter list, all chapters, light novel chapters, web novel`
    : "chapter list, light novel, web novel";
  const ogImage = chapterData?.source_overview_image_url || DEFAULT_OG_IMAGE;
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
        <Button startIcon={<ArrowBackIcon />} component={Link} to={`/`} sx={{ mt: 2 }}>
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
      <title>{metaTitle}</title>
      <meta name="description" content={metaDescription.substring(0, 160)} />
      <meta name="keywords" content={metaKeywords} />
      <link rel="canonical" href={pageUrl} />

      <meta property="og:title" content={metaTitle} />
      <meta property="og:description" content={metaDescription.substring(0, 160)} />
      <meta property="og:type" content="website" />
      <meta property="og:url" content={pageUrl} />
      <meta property="og:site_name" content={siteName} />
      <meta property="og:image" content={ogImage} />

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={metaTitle} />
      <meta name="twitter:description" content={metaDescription.substring(0, 160)} />
      <meta name="twitter:image" content={DEFAULT_OG_IMAGE} />

      {!loading && chapterData && (
        <BreadcrumbNav
          items={[
            {
              label: chapterData.novel_title,
              link: `/novels/${novelSlug}`,
              icon: <BookIcon fontSize="inherit" />
            },
            {
              label: chapterData.source_name,
              link: `/novels/${novelSlug}/${sourceSlug}`,
              icon: <LanguageIcon fontSize="inherit" />
            },
            {
              label: "Chapters",
              icon: <ListAltIcon fontSize="inherit" />
            }
          ]}
        />
      )}
      
      <Button component={Link} to={`/novels/${novelSlug}/${sourceSlug}`} startIcon={<ArrowBackIcon />} sx={{ mt: 2 }}>
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

        <Box sx={{ mt: 3, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid>
              <Typography variant="subtitle1">
                {chapterData.count} Total Chapters
              </Typography>
            </Grid>
            <Grid size="grow">
              <Stack direction="row" spacing={2} alignItems="center" justifyContent="flex-end">
                <Typography variant="body2">
                  Page {chapterData.current_page} of {chapterData.total_pages}
                </Typography>
                <FormControl variant="outlined" size="small" sx={{ minWidth: 120 }}>
                  <InputLabel id="page-size-label">Per Page</InputLabel>
                  <Select
                    labelId="page-size-label"
                    value={pageSize}
                    onChange={handlePageSizeChange}
                    label="Per Page"
                  >
                    <MenuItem value={50}>50</MenuItem>
                    <MenuItem value={100}>100</MenuItem>
                    <MenuItem value={200}>200</MenuItem>
                    <MenuItem value={500}>500</MenuItem>
                  </Select>
                </FormControl>
              </Stack>
            </Grid>
          </Grid>
        </Box>

        {chapterData.total_pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mb: 3 }}>
            <Pagination 
              count={chapterData.total_pages} 
              page={chapterData.current_page}
              onChange={handlePageChange} 
              color="primary" 
              showFirstButton 
              showLastButton
            />
          </Box>
        )}
        
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
                        component={Link}
                        to={`/novels/${novelSlug}/${sourceSlug}/chapter/${chapter.chapter_id}`}
                        disabled={!chapter.has_content}
                        sx={{
                          opacity: chapter.has_content ? 1 : 0.5,
                          '&.Mui-disabled': {
                            opacity: 0.5,
                          }
                        }}
                      >
                        <ListItemText 
                          primary={getChapterNameWithNumber(chapter.title, chapter.chapter_id)}
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
        
        {chapterData.total_pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 3 }}>
            <Pagination 
              count={chapterData.total_pages} 
              page={chapterData.current_page}
              onChange={handlePageChange} 
              color="primary" 
              showFirstButton 
              showLastButton
            />
          </Box>
        )}
      </Paper>
    </Container>
  );
};

export default ChapterList;
