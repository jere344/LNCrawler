import { useState, useEffect } from 'react';
import { 
  Container, 
  Typography, 
  Grid, 
  Card, 
  CardContent, 
  CardMedia, 
  Box, 
  Paper, 
  Pagination, 
  CircularProgress,
  CardActionArea,
  Rating,
} from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { novelService } from '../../services/api';
import defaultCover from '@assets/default-cover.jpg';
import StarIcon from '@mui/icons-material/Star';
import { Novel, NovelListResponse } from '@models/novels_types';

const NovelList = () => {
  const [novels, setNovels] = useState<Novel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchNovels = async () => {
      setLoading(true);
      try {
        const response = await novelService.listNovels(page, 24);
        setNovels(response.results);
        setTotalPages(response.total_pages);
      } catch (err) {
        console.error('Error fetching novels:', err);
        setError('Failed to load novels. Please try again later.');
      } finally {
        setLoading(false);
      }
    };
    
    fetchNovels();
  }, [page]);

  const handlePageChange = (event: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleNovelClick = (novelSlug: string) => {
    navigate(`/novels/${novelSlug}`);
  };

  return (
    <Container maxWidth="lg">
      <Box sx={{ my: 4, textAlign: 'center' }}>
        <Typography variant="h4" component="h1" gutterBottom>
          Novel Library
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" paragraph>
          Browse our collection of light novels
        </Typography>
      </Box>

      {loading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
          <CircularProgress />
        </Box>
      ) : error ? (
        <Paper elevation={3} sx={{ p: 3, textAlign: 'center' }}>
          <Typography color="error">{error}</Typography>
        </Paper>
      ) : (
        <>
          <Grid container spacing={3}>
            {novels.map((novel) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={novel.id}>
                <Card
                  sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    transition: 'transform 0.2s',
                    '&:hover': {
                      transform: 'scale(1.03)'
                    }
                  }}
                >
                  <CardActionArea onClick={() => handleNovelClick(novel.slug)}>
                    <CardMedia
                      component="img"
                      height="250"
                      image={novel.cover_url ? (import.meta.env.VITE_API_BASE_URL + "/" + novel.cover_url) : defaultCover}
                      alt={novel.title}
                      sx={{ objectFit: 'cover' }}
                      onError={(e: any) => {
                        e.target.onerror = null;
                        e.target.src = defaultCover;
                      }}
                    />
                    <CardContent>
                      <Typography gutterBottom variant="h6" component="div" noWrap>
                        {novel.title}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
                        {novel.avg_rating ? (
                          <>
                            <Rating 
                              value={novel.avg_rating} 
                              precision={0.1} 
                              readOnly 
                              size="small"
                              emptyIcon={<StarIcon style={{ opacity: 0.55 }} fontSize="inherit" />}
                            />
                            <Typography variant="body2" color="text.secondary" sx={{ ml: 0.5 }}>
                              {novel.avg_rating.toFixed(1)}
                            </Typography>
                          </>
                        ) : (
                          <Typography variant="body2" color="text.secondary">
                            No ratings
                          </Typography>
                        )}
                      </Box>
                      <Typography variant="body2" color="text.secondary">
                        {novel.sources_count} {novel.sources_count === 1 ? 'source' : 'sources'} • {novel.total_chapters} chapters
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
          
          <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
            <Pagination 
              count={totalPages} 
              page={page} 
              onChange={handlePageChange} 
              color="primary" 
              size="large"
              showFirstButton
              showLastButton
            />
          </Box>
        </>
      )}
    </Container>
  );
};

export default NovelList;
