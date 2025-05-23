import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Container,
  Typography,
  Box,
  Paper,
  Button,
  ImageList,
  ImageListItem,
  CircularProgress,
  Pagination,
  Dialog,
  IconButton,
  useTheme,
  alpha,
  useMediaQuery,
  Switch,
  FormControlLabel,
} from '@mui/material';
import { novelService } from '../../services/api';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import CloseIcon from '@mui/icons-material/Close';
import NavigateBeforeIcon from '@mui/icons-material/NavigateBefore';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import BreadcrumbNav from '../common/BreadcrumbNav';
import LanguageIcon from '@mui/icons-material/Language';
import BookIcon from '@mui/icons-material/Book';
import ImageIcon from '@mui/icons-material/Image';

interface GalleryImage {
  chapter_id: number;
  chapter_title: string;
  image_url: string;
  image_name: string;
}

interface GalleryResponse {
  novel_id: string;
  novel_title: string;
  novel_slug: string;
  source_id: string;
  source_name: string;
  source_slug: string;
  count: number;
  total_pages: number;
  current_page: number;
  images: GalleryImage[];
}

type ImageWithDimensions = GalleryImage & { width?: number; height?: number };

const ImageGallery = () => {
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const [gallery, setGallery] = useState<GalleryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [selectedImage, setSelectedImage] = useState<ImageWithDimensions | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState<boolean>(false);

  const [showSmallImages, setShowSmallImages] = useState<boolean>(false);
  const [imagesWithDimensions, setImagesWithDimensions] = useState<ImageWithDimensions[]>([]);
  const [allDimensionsLoaded, setAllDimensionsLoaded] = useState<boolean>(false);

  useEffect(() => {
    const fetchGallery = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      setImagesWithDimensions([]); // Reset for new page/source
      setAllDimensionsLoaded(false);
      setError(null); 
      try {
        const data = await novelService.getSourceGallery(novelSlug, sourceSlug, page);
        setGallery(data);
        // Dimension loading will be triggered by the effect below watching `gallery`
      } catch (err) {
        console.error('Error fetching gallery:', err);
        setError('Failed to load images. Please try again later.');
        setGallery(null);
      } finally {
        setLoading(false);
      }
    };

    fetchGallery();
  }, [novelSlug, sourceSlug, page]);

  useEffect(() => {
    if (!gallery || gallery.images.length === 0) {
      setImagesWithDimensions([]);
      setAllDimensionsLoaded(true); // No images to load dimensions for
      return;
    }

    setAllDimensionsLoaded(false);
    const promises = gallery.images.map(image => {
      return new Promise<ImageWithDimensions>((resolve) => {
        const img = new Image();
        img.onload = () => resolve({ ...image, width: img.naturalWidth, height: img.naturalHeight });
        img.onerror = () => resolve({ ...image, width: 0, height: 0 }); // Resolve with 0,0 on error
        img.src = image.image_url;
      });
    });

    Promise.all(promises).then(results => {
      setImagesWithDimensions(results);
      setAllDimensionsLoaded(true);
    });
  }, [gallery]); // Trigger when gallery data (and thus its images) changes

  const handleBackClick = () => {
    navigate(`/novels/${novelSlug}/${sourceSlug}`);
  };

  const handlePageChange = (_event: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
  };

  const openLightbox = (imageToOpen: GalleryImage) => {
    const fullImageDetails = imagesWithDimensions.find(
      img => img.image_url === imageToOpen.image_url
    );
    setSelectedImage(fullImageDetails || { ...imageToOpen });
    setLightboxOpen(true);
  };

  const closeLightbox = () => {
    setLightboxOpen(false);
  };

  const navigateLightbox = (direction: 'prev' | 'next') => {
    if (!gallery || !selectedImage) return;
    
    const currentIndexInGallery = gallery.images.findIndex(
      img => img.image_url === selectedImage.image_url
    );
    
    let nextIndexInGallery = -1;
    if (direction === 'prev' && currentIndexInGallery > 0) {
      nextIndexInGallery = currentIndexInGallery - 1;
    } else if (direction === 'next' && currentIndexInGallery < gallery.images.length - 1) {
      nextIndexInGallery = currentIndexInGallery + 1;
    }

    if (nextIndexInGallery !== -1) {
      const nextImageFromGallery = gallery.images[nextIndexInGallery];
      const fullNextImageDetails = imagesWithDimensions.find(
        img => img.image_url === nextImageFromGallery.image_url
      );
      setSelectedImage(fullNextImageDetails || { ...nextImageFromGallery });
    }
  };

  const filteredImages = useMemo(() => {
    return imagesWithDimensions.filter(image => {
      if (showSmallImages) {
        return true;
      }
      // If dimensions are not loaded (undefined), or if image is small, filter it out
      if (typeof image.width === 'number' && typeof image.height === 'number') {
        return image.width >= 50 && image.height >= 50;
      }
      // If dimensions are not yet available (should not happen with Promise.all approach unless error)
      // or if we want to show images while dimensions are loading (not current strategy)
      return true; // Default to show if dimensions are somehow undefined after loading
    });
  }, [imagesWithDimensions, showSmallImages]);

  if (loading && !gallery) {
    return (
      <Container maxWidth="lg">
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
          <CircularProgress />
        </Box>
      </Container>
    );
  }

  if (error || (!gallery && !loading)) { // Adjusted error condition
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} onClick={handleBackClick} sx={{ mt: 2 }}>
          Back to Source
        </Button>
        <Paper 
          elevation={3} 
          sx={{ 
            p: 4, 
            textAlign: 'center', 
            mt: 3, 
            borderRadius: 3,
            background: `linear-gradient(135deg, ${alpha(theme.palette.error.dark, 0.05)} 0%, ${alpha(theme.palette.error.light, 0.1)} 100%)`,
          }}
        >
          <Typography color="error" variant="h5" gutterBottom>
            {error || 'No images found for this source'}
          </Typography>
          <Button 
            variant="contained" 
            color="primary" 
            onClick={handleBackClick}
            sx={{ mt: 2 }}
          >
            Return to Source
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      {gallery && (
        <BreadcrumbNav
          items={[
            {
              label: gallery.novel_title,
              link: `/novels/${novelSlug}`,
              icon: <BookIcon fontSize="inherit" />
            },
            {
              label: gallery.source_name,
              link: `/novels/${novelSlug}/${sourceSlug}`,
              icon: <LanguageIcon fontSize="inherit" />
            },
            {
              label: "Image Gallery",
              icon: <ImageIcon fontSize="inherit" />
            }
          ]}
        />
      )}
      
      <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
        <Button 
          startIcon={<ArrowBackIcon />} 
          onClick={handleBackClick}
          variant="outlined"
          sx={{ 
            borderRadius: '20px',
            px: 2,
          }}
        >
          Back to Source
        </Button>
      </Box>

      <Paper
        elevation={3}
        sx={{
          p: 3,
          mb: 4,
          borderRadius: 3,
          background: theme.palette.mode === 'dark'
            ? `linear-gradient(135deg, ${alpha(theme.palette.background.paper, 0.9)} 0%, ${alpha(theme.palette.background.paper, 1)} 100%)`
            : theme.palette.background.paper,
        }}
      >
        <Typography variant="h4" gutterBottom>
          Image Gallery
        </Typography>
        <Typography variant="subtitle1" color="text.secondary" gutterBottom>
          {gallery?.count} images from {gallery?.source_name}
        </Typography>

        <FormControlLabel
          control={
            <Switch
              checked={showSmallImages}
              onChange={(e) => setShowSmallImages(e.target.checked)}
            />
          }
          label={`Show small images (${imagesWithDimensions.length - filteredImages.length} filtered)`}
          sx={{ mt: 1, mb: 2, display: 'block' }}
        />
        
        <Box sx={{ mb: 3, mt: 1 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
            </Box>
          ) : !allDimensionsLoaded && gallery && gallery.images.length > 0 ? (
            <Box sx={{ textAlign: 'center', p: 4 }}>
              <CircularProgress size={24} sx={{ mr: 1, verticalAlign: 'middle' }} />
              <Typography variant="body2" component="span" sx={{ verticalAlign: 'middle' }}>
                Loading image dimensions...
              </Typography>
            </Box>
          ) : (
            <>
              {filteredImages.length > 0 ? (
                <ImageList variant="masonry" cols={isMobile ? 2 : 3} gap={8} sx={{ overflow: 'hidden' }}>
                  {filteredImages.map((image) => (
                    <ImageListItem 
                      key={image.image_url} 
                      onClick={() => openLightbox(image)}
                      sx={{
                        cursor: 'pointer',
                        borderRadius: 2,
                        overflow: 'hidden',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                        transition: 'transform 0.3s ease',
                        '&:hover': {
                          transform: 'scale(1.02)'
                        }
                      }}
                    >
                      <img
                        src={image.image_url}
                        alt={`Chapter ${image.chapter_id}: ${image.image_name}`}
                        loading="lazy"
                        style={{ borderRadius: 8 }}
                      />
                      <Box 
                        sx={{
                          position: 'absolute',
                          bottom: 0,
                          left: 0,
                          right: 0,
                          bgcolor: 'rgba(0,0,0,0.7)',
                          color: 'white',
                          p: 1,
                          fontSize: '0.8rem',
                        }}
                      >
                        <Typography variant="caption">
                          Chapter {image.chapter_id}
                        </Typography>
                      </Box>
                    </ImageListItem>
                  ))}
                </ImageList>
              ) : (
                gallery && gallery.images.length > 0 && allDimensionsLoaded && (
                  <Typography sx={{ textAlign: 'center', p: 4, color: 'text.secondary' }}>
                    No images to display with current filter settings.
                  </Typography>
                )
              )}
              {gallery && gallery.images.length === 0 && allDimensionsLoaded && (
                 <Typography sx={{ textAlign: 'center', p: 4, color: 'text.secondary' }}>
                  No images found in this gallery page.
                </Typography>
              )}
            </>
          )}
        </Box>
        
        {gallery && gallery.total_pages > 1 && (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 4 }}>
            <Pagination
              count={gallery.total_pages}
              page={page}
              onChange={handlePageChange}
              color="primary"
              size={isMobile ? "small" : "medium"}
              siblingCount={isMobile ? 0 : 1}
            />
          </Box>
        )}
      </Paper>
      
      {/* Lightbox Modal */}
      <Dialog
        open={lightboxOpen}
        onClose={closeLightbox}
        maxWidth="xl"
        fullWidth
        PaperProps={{
          sx: {
            bgcolor: 'rgba(0,0,0,0.9)',
            boxShadow: 'none',
            height: '100%',
            m: 0,
            borderRadius: 0,
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
          }
        }}
      >
        <Box sx={{ 
          position: 'absolute', 
          top: 0, 
          right: 0, 
          m: 1 
        }}>
          <IconButton onClick={closeLightbox} sx={{ color: 'white' }}>
            <CloseIcon />
          </IconButton>
        </Box>

        {selectedImage && (
          <Box sx={{ textAlign: 'center', p: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="subtitle1" sx={{ color: 'white', mb: 2 }}>
              Chapter {selectedImage.chapter_id}: {selectedImage.chapter_title}
            </Typography>

            <Box sx={{ 
              position: 'relative', 
              flexGrow: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              overflow: 'auto'
            }}>
              <img
                src={selectedImage.image_url}
                alt={selectedImage.image_name}
                style={{ 
                  maxWidth: '100%', 
                  maxHeight: '100%', 
                  objectFit: 'contain',
                }}
              />
              
              {/* Navigation arrows */}
              <IconButton
                sx={{
                  position: 'absolute',
                  left: 8,
                  color: 'white',
                  bgcolor: 'rgba(0,0,0,0.4)',
                  '&:hover': { bgcolor: 'rgba(0,0,0,0.6)' }
                }}
                onClick={() => navigateLightbox('prev')}
              >
                <NavigateBeforeIcon />
              </IconButton>
              
              <IconButton
                sx={{
                  position: 'absolute',
                  right: 8,
                  color: 'white',
                  bgcolor: 'rgba(0,0,0,0.4)',
                  '&:hover': { bgcolor: 'rgba(0,0,0,0.6)' }
                }}
                onClick={() => navigateLightbox('next')}
              >
                <NavigateNextIcon />
              </IconButton>
            </Box>

            <Typography variant="caption" sx={{ color: 'white', mt: 2 }}>
              {selectedImage.image_name}
            </Typography>
          </Box>
        )}
      </Dialog>
    </Container>
  );
};

export default ImageGallery;
