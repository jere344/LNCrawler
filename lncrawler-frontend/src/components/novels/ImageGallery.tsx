import { useState, useEffect, useMemo } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
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
import { getChapterLabel } from '@utils/Misc';
import SeoMeta, { DEFAULT_OG_IMAGE } from '../common/SeoMeta';

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
  const { t } = useTranslation();
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));

  const [gallery, setGallery] = useState<GalleryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState<number>(1);
  const [selectedImage, setSelectedImage] = useState<ImageWithDimensions | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState<boolean>(false);

  const [showSmallImages, setShowSmallImages] = useState<boolean>(false);
  const [dimensions, setDimensions] = useState<Record<string, { width: number; height: number }>>({});

  useEffect(() => {
    const fetchGallery = async () => {
      if (!novelSlug || !sourceSlug) return;
      
      setLoading(true);
      setDimensions({}); // Reset for new page/source
      setError(null); 
      try {
        const data = await novelService.getSourceGallery(novelSlug, sourceSlug, page);
        setGallery(data);
      } catch (err) {
        console.error('Error fetching gallery:', err);
        setError(t('gallery.loadFailed'));
        setGallery(null);
      } finally {
        setLoading(false);
      }
    };

    fetchGallery();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- t intentionally omitted; explicit inputs listed
  }, [novelSlug, sourceSlug, page]);

  const handlePageChange = (_event: React.ChangeEvent<unknown>, value: number) => {
    setPage(value);
  };

  // Dimensions are recorded from the grid <img> as the browser lazy-loads each image,
  // so the small-image filter no longer requires an eager full-page prefetch.
  const handleImageLoad = (url: string, event: React.SyntheticEvent<HTMLImageElement>) => {
    const { naturalWidth: width, naturalHeight: height } = event.currentTarget;
    setDimensions(prev =>
      prev[url]?.width === width && prev[url]?.height === height ? prev : { ...prev, [url]: { width, height } }
    );
  };

  const handleImageError = (url: string) => {
    setDimensions(prev => (prev[url] ? prev : { ...prev, [url]: { width: 0, height: 0 } }));
  };

  const openLightbox = (imageToOpen: GalleryImage) => {
    setSelectedImage(imageToOpen);
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
      setSelectedImage(gallery.images[nextIndexInGallery]);
    }
  };

  const filteredImages = useMemo(() => {
    if (!gallery) return [];
    if (showSmallImages) return gallery.images;
    return gallery.images.filter(image => {
      const d = dimensions[image.image_url];
      return !d || (d.width >= 50 && d.height >= 50);
    });
  }, [gallery, showSmallImages, dimensions]);

  const hiddenSmallCount = useMemo(() => {
    if (!gallery) return 0;
    return gallery.images.filter(image => {
      const d = dimensions[image.image_url];
      return !!d && (d.width < 50 || d.height < 50);
    }).length;
  }, [gallery, dimensions]);

  const pageUrl = window.location.href;

  const metaTitle = gallery 
    ? t('gallery.metaTitle', { novel: gallery.novel_title, source: gallery.source_name })
    : t('gallery.metaLoadingTitle');
  const metaDescription = gallery
    ? t('gallery.metaDescription', { novel: gallery.novel_title, source: gallery.source_name, count: gallery.count })
    : t('gallery.metaLoadingDescription');
  // i18n-missing: no catalog key for the gallery fallback keywords
  const metaKeywords = gallery
    ? t('gallery.keywords', { novel: gallery.novel_title, source: gallery.source_name })
    : "image gallery, light novel, illustrations, art";
  const ogImage = (gallery && gallery.images.length > 1) ? gallery.images[1].image_url : gallery?.images[0]?.image_url || DEFAULT_OG_IMAGE;


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
        <Button startIcon={<ArrowBackIcon />} component={Link} to={`/novels/${novelSlug}/${sourceSlug}`} sx={{ mt: 2 }}>
          {t('gallery.backToSource')}
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
            {error || t('gallery.notFound')}
          </Typography>
          <Button 
            variant="contained" 
            color="primary" 
            component={Link} 
            to={`/novels/${novelSlug}/${sourceSlug}`} // navigation using Link
            sx={{ mt: 2 }}
          >
            {t('gallery.returnToSource')}
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg">
      <SeoMeta
        title={metaTitle}
        description={metaDescription.substring(0, 160)}
        keywords={metaKeywords}
        image={ogImage}
        type="image.gallery"
        canonical={pageUrl}
      />

      {gallery && (
        <BreadcrumbNav
          items={[
            {
              label: gallery.novel_title,
              icon: <BookIcon fontSize="inherit" />
            },
            {
              label: gallery.source_name,
              link: `/novels/${novelSlug}/${sourceSlug}`,
              icon: <LanguageIcon fontSize="inherit" />
            },
            {
              label: t('gallery.heading'),
              icon: <ImageIcon fontSize="inherit" />
            }
          ]}
        />
      )}

      <Box sx={{ display: 'flex', alignItems: 'center', mt: 2, mb: 4 }}>
        <Button 
          startIcon={<ArrowBackIcon />} 
          component={Link} 
          to={`/novels/${novelSlug}/${sourceSlug}`} // navigation using Link
          variant="outlined"
          sx={{ 
            borderRadius: '20px',
            px: 2,
          }}
        >
          {t('gallery.backToSource')}
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
          {t('gallery.heading')}
        </Typography>
        <Typography variant="subtitle1" gutterBottom sx={{
          color: "text.secondary"
        }}>
          {t('gallery.countFrom', { count: gallery?.count ?? 0, novel: gallery?.novel_title })}
        </Typography>

        <FormControlLabel
          control={
            <Switch
              checked={showSmallImages}
              onChange={(e) => setShowSmallImages(e.target.checked)}
            />
          }
          label={t('gallery.showSmall', { count: hiddenSmallCount })}
          sx={{ mt: 1, mb: 2, display: 'block' }}
        />
        
        <Box sx={{ mb: 3, mt: 1 }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress />
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
                        alt={t('gallery.imageAlt', { chapter: getChapterLabel(t, image.chapter_title, image.chapter_id), name: image.image_name })}
                        loading="lazy"
                        decoding="async"
                        onLoad={(e) => handleImageLoad(image.image_url, e)}
                        onError={() => handleImageError(image.image_url)}
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
                          {getChapterLabel(t, image.chapter_title, image.chapter_id)}
                        </Typography>
                      </Box>
                    </ImageListItem>
                  ))}
                </ImageList>
              ) : (
                gallery && gallery.images.length > 0 && (
                  <Typography sx={{ textAlign: 'center', p: 4, color: 'text.secondary' }}>
                    {t('gallery.noImagesFiltered')}
                  </Typography>
                )
              )}
              {gallery && gallery.images.length === 0 && (
                 <Typography sx={{ textAlign: 'center', p: 4, color: 'text.secondary' }}>
                  {t('gallery.noImagesPage')}
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
        slotProps={{
          paper: {
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
              {getChapterLabel(t, selectedImage.chapter_title, selectedImage.chapter_id)}
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
