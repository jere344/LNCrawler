import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Container,
  Typography,
  Box,
  Paper,
  Button,
  Tooltip,
  useTheme,
  alpha,
  Skeleton,
  Grid as Grid,
  Alert,
} from '@mui/material';
import { useAuth } from '@context/AuthContext';
import { useEpubDownload } from '@utils/useEpubDownload';
import AddToListDialog from '../readinglist/AddToListDialog';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import LanguageIcon from '@mui/icons-material/Language';
import CommentIcon from '@mui/icons-material/Comment';
import defaultCover from '@assets/default-cover.jpg';
import CommentSection from '../comments/CommentSection';
import NovelSynopsis from './common/NovelSynopsis';
import NovelUpdateButton from './common/NovelUpdateButton';
import { useAdultContent } from '@context/AdultContentContext';
import BreadcrumbNav from '../common/BreadcrumbNav';
import BookIcon from '@mui/icons-material/Book';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { editionLabel } from '@utils/Misc.tsx';
import BookmarkIcon from '@mui/icons-material/Bookmark';
import SectionContainer from '@components/common/SectionContainer.tsx';
import SeoMeta, { DEFAULT_OG_IMAGE } from '../common/SeoMeta';
import NovelSources from './NovelSources';
import NovelRecommendation from '../common/NovelRecommendation';
import Reviews from './Reviews';
import TrendingUpIcon from '@mui/icons-material/TrendingUp';
import InfoIcon from '@mui/icons-material/Info';
import ShareIcon from '@mui/icons-material/Share';
import NovelTags from './common/NovelTags';
import DetailRow from './sourceDetail/DetailRow';
import ReadingListsPanel from './sourceDetail/ReadingListsPanel';
import SourceDetailSkeleton from './sourceDetail/SourceDetailSkeleton';
import SourceAudiobookBanner from '@components/audiobooks/SourceAudiobookBanner';
import SourceCover from './sourceDetail/SourceCover';
import SourceTitleBar from './sourceDetail/SourceTitleBar';
import SourceHeroDetails from './sourceDetail/SourceHeroDetails';
import SourceHeroStats from './sourceDetail/SourceHeroStats';
import SourceReadActions from './sourceDetail/SourceReadActions';
import SourceToolActions from './sourceDetail/SourceToolActions';
import { useSourceDetail } from './sourceDetail/useSourceDetail';
import { isFullSource } from './sourceDetail/sourceView';

const SourceDetail = () => {
  const { t, i18n } = useTranslation();
  const { novelSlug, sourceSlug } = useParams<{ novelSlug: string; sourceSlug: string }>();
  const theme = useTheme();
  const [downloadAnchor, setDownloadAnchor] = useState<null | HTMLElement>(null);
  const { startDownload, preparingKey } = useEpubDownload(novelSlug!, sourceSlug!);
  const { isAuthenticated } = useAuth();
  const { isBlurred, revealHandler } = useAdultContent();
  const { source, setSource, novel, loading, error, novelRating, isBookmarked, isDmca, bookmarking, handleToggleBookmark, handleShare } = useSourceDetail(novelSlug, sourceSlug);
  // The full source (detail fetch, or a card's state); a library card's preview has none of its
  // authors, tags, counters or chapter stats, so the sections that need them wait for the fetch.
  const full = isFullSource(source) ? source : null;
  const authors = full?.authors ?? [];
  const tags = full?.tags ?? [];
  const coverBlurred = isBlurred(source?.is_adult, source?.novel_id);
  const [addToListOpen, setAddToListOpen] = useState(false);
  const [readingListPage, setReadingListPage] = useState(1);



  const pageUrl = window.location.href;
  const siteName = "LNCrawler";

  const metaTitle = full
    ? t('sourceDetail.metaTitle', { title: full.title, source: full.source_name })
    : t('sourceDetail.metaLoadingTitle');
  const metaSynopsis = full?.synopsis
    ? full.synopsis.substring(0, 120).replace(/<[^>]+>/g, '') + '...'
    : `Discover this light novel on ${siteName}.`; // i18n-missing: no catalog key for the synopsis fallback
  const metaDescription = full
    ? t('sourceDetail.metaDescription', { title: full.title, source: full.source_name, synopsis: metaSynopsis })
    : t('sourceDetail.metaLoadingDescription');
  // i18n-missing: no catalog key for the source-detail generic meta keywords
  const metaKeywordsList = full
    ? [full.title, full.source_name, ...full.tags, ...full.authors, "read light novel", "web novel"]
    : ["light novel", "web novel", "source details"];
  const metaKeywords = [...new Set(metaKeywordsList.filter(Boolean))].join(', '); // Unique keywords
  const ogImage = full?.overview_url || full?.cover_url || source?.cover_min_url || DEFAULT_OG_IMAGE;

  if (!source && !error) {
    return <SourceDetailSkeleton />;
  }

  if (!source) {
    return (
      <Container>
        <Button startIcon={<ArrowBackIcon />} component={Link} to="/" variant="outlined" sx={{ mt: 2 }}>
          {t('sourceDetail.backToHome')}
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
            {error || t('sourceDetail.notFound')}
          </Typography>
          <Button 
            variant="contained" 
            color="primary" 
            component={Link}
            to="/"
            sx={{ mt: 2 }}
          >
            {t('sourceDetail.returnToHome')}
          </Button>
        </Paper>
      </Container>
    );
  }

  return (
      <Container maxWidth="lg">
        <SeoMeta
          title={metaTitle}
          description={metaDescription}
          keywords={metaKeywords}
          image={ogImage}
          type="book"
          canonical={pageUrl}
        >
          {authors.length > 0 && <meta property="book:author" content={authors.join(', ')} />}
          {tags.length > 0 && tags.map(tag => <meta property="book:tag" content={tag} key={tag} />)}
        </SeoMeta>

        {full && (
          <BreadcrumbNav
            items={[
              {
                label: full.novel_title,
                icon: <BookIcon fontSize="inherit" />
              },
              {
                label: full.source_name,
                icon: <LanguageIcon fontSize="inherit" />
              }
            ]}
          />
        )}
        
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mt: 2, mb: 4 }}>
          <Button 
            startIcon={<ArrowBackIcon />}
            component={Link}
            to="/"
            variant="outlined"
            sx={{ 
              borderRadius: '20px',
              px: 2,
            }}
          >
            {t('sourceDetail.backToHome')}
          </Button>
          <Tooltip title={t('common.share')}>
            <Button
              startIcon={<ShareIcon />}
              onClick={handleShare}
              variant="outlined"
              sx={{ borderRadius: '20px', px: 2 }}
            >
              {t('common.share')}
            </Button>
          </Tooltip>
        </Box>

        {isDmca && (
          <Alert severity="error" sx={{ mb: 3, borderRadius: 2 }}>
            {t('sourceDetail.dmcaNotice')}
          </Alert>
        )}

        <Paper 
          elevation={0}
          sx={{ 
            p: 0,
            overflow: 'hidden',
            borderRadius: 3,
            mb: 4,
            position: 'relative',
            background: `linear-gradient(135deg, ${alpha(theme.palette.primary.dark, 0.3)} 0%, ${alpha(theme.palette.primary.main, 0.1)} 100%)`,
          }}
        >
          {/* Hero background with blur effect */}
          <Box 
            sx={{ 
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              opacity: 0.35,
              backgroundImage: `url(${full?.cover_url || source.cover_min_url || defaultCover})`,
              backgroundSize: 'cover',
              backgroundPosition: 'center',
              filter: 'blur(20px)',
              zIndex: 0,
            }}
          />
          
          <Box sx={{ position: 'relative', zIndex: 1, p: { xs: 2, md: 4 } }}>
            <Grid container spacing={3}>
              <Grid size={{ xs: 12, md: 6, lg: 5 }}>
                <SourceCover
                  source={source}
                  coverBlurred={coverBlurred}
                  onCoverClick={coverBlurred ? revealHandler(source.novel_id) : undefined}
                />
              </Grid>
              
              <Grid size={{ xs: 12, md: 6, lg: 7 }}>
                <SourceTitleBar
                  source={source}
                  novel={novel}
                  novelSlug={novelSlug}
                  isAuthenticated={isAuthenticated}
                  isBookmarked={isBookmarked}
                  bookmarking={bookmarking}
                  onToggleBookmark={handleToggleBookmark}
                  onAddToList={() => setAddToListOpen(true)}
                  setSource={setSource}
                />
                <SourceHeroDetails source={full} novelSlug={novelSlug} novelRating={novelRating} />
                <SourceHeroStats source={full} language={i18n.language} />
                {/* Tags */}
                {tags.length > 0 && (
                  <Box sx={{ mb: 3 }}>
                    <NovelTags tags={tags} chipSize="small" />
                  </Box>
                )}

                <SourceReadActions source={full} novelSlug={novelSlug} sourceSlug={sourceSlug} isDmca={isDmca} />
                <SourceToolActions
                  source={source}
                  novelSlug={novelSlug}
                  sourceSlug={sourceSlug}
                  isDmca={isDmca}
                  downloadAnchor={downloadAnchor}
                  setDownloadAnchor={setDownloadAnchor}
                  preparingKey={preparingKey}
                  startDownload={startDownload}
                />
                {full?.audiobook && <SourceAudiobookBanner audiobook={full.audiobook} isAdult={full.audiobook.is_adult} />}
              </Grid>
            </Grid>
          </Box>
        </Paper>
        
        {/* Update Button Section */}
        {full && full.source_url && full.source_url.startsWith('http') && (
          <Paper 
            sx={{ 
              p: { xs: 2, md: 3 }, 
              mb: 4,
              borderRadius: 3,
            }}
          >
            <NovelUpdateButton 
              sourceUrl={full.source_url} 
              novelTitle={source.title} 
              sourceName={full.source_name}
              disabled={isDmca || full.has_crawler === false}
            />
          </Paper>
        )}

        {full?.synopsis ? (
          <SectionContainer title={t('sourceDetail.synopsis')} icon={<BookmarkIcon />}>
            <NovelSynopsis synopsis={full.synopsis} />
          </SectionContainer>
        ) : loading ? (
          <SectionContainer title={t('sourceDetail.synopsis')} icon={<BookmarkIcon />}>
            {[...Array(6)].map((_, i) => (
              <Skeleton key={i} variant="text" width="100%" height={20} sx={{ mb: 1 }} animation="wave" />
            ))}
          </SectionContainer>
        ) : null}

        {full && ((full.status && full.status !== 'Unknown') || full.edition || full.original_publisher || full.english_publisher || full.editors?.length > 0 || full.translators?.length > 0) && (
          <SectionContainer title={t('sourceDetail.details')} icon={<InfoIcon />}>
            <Grid container spacing={2}>
              {full.status && full.status !== 'Unknown' && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.status')} value={full.status} />
                </Grid>
              )}
              {full.edition && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.editionLabel')} value={editionLabel(full.edition, t)} />
                </Grid>
              )}
              {full.original_publisher && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.originalPublisher')} value={full.original_publisher} />
                </Grid>
              )}
              {full.english_publisher && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.englishPublisher')} value={full.english_publisher} />
                </Grid>
              )}
              {full.editors?.length > 0 && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.editors')} value={full.editors.join(', ')} />
                </Grid>
              )}
              {full.translators?.length > 0 && (
                <Grid size={{ xs: 12, sm: 6 }}>
                  <DetailRow label={t('sourceDetail.translators')} value={full.translators.join(', ')} />
                </Grid>
              )}
            </Grid>
          </SectionContainer>
        )}

        {novel && novel.sources.length > 1 && (
          <SectionContainer title={t('sourceDetail.otherSources')} icon={<LanguageIcon />}>
            <NovelSources
              novel={{ ...novel, slug: novelSlug ?? novel.slug }}
              currentSourceSlug={sourceSlug}
            />
          </SectionContainer>
        )}

        {novel?.similar_novels && novel.similar_novels.length > 0 && (
          <SectionContainer title={t('sourceDetail.similarNovels')} icon={<TrendingUpIcon />}>
            <NovelRecommendation similarNovels={novel.similar_novels} />
          </SectionContainer>
        )}

        {novel?.reading_lists && novel.reading_lists.length > 0 && (
          <ReadingListsPanel
            readingLists={novel.reading_lists}
            page={readingListPage}
            onPageChange={setReadingListPage}
          />
        )}
        {novelSlug && (
          <SectionContainer title={t('sourceDetail.reviews')} icon={<MenuBookIcon />}>
            <Reviews novelSlug={novelSlug} />
          </SectionContainer>
        )}

        {novelSlug && (
          <SectionContainer title={t('sourceDetail.comments')} icon={<CommentIcon />}>
            <CommentSection 
              novelSlug={novelSlug}
              title={t('sourceDetail.novelComments')} 
            />
          </SectionContainer>
        )}

        <AddToListDialog
          open={addToListOpen}
          onClose={() => setAddToListOpen(false)}
          novelId={source.novel_id}
          novelTitle={novel?.title || source?.title}
          displayTitle={source?.title || novel?.title || ''}
        />
    </Container>
  );
};

export default SourceDetail;
