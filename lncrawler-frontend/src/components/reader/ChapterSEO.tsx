import { useTranslation } from 'react-i18next';
import { ChapterContent } from '@models/novels_types';

interface ChapterSEOProps {
  chapter: ChapterContent | null;
}

const DEFAULT_OG_IMAGE = '/og-image.jpg';

const ChapterSEO = ({ chapter }: ChapterSEOProps) => {
  const { t } = useTranslation();
  const getChapterLabel = (title?: string | null, chapterId?: number | null): string => {
    const trimmed = title?.trim();
    if (trimmed) {
      return trimmed;
    }
    return chapterId != null ? t('units.chapter', { number: chapterId }) : "";
  };
  const pageUrl = window.location.href;
  const siteName = "LNCrawler";
  const chapterLabel = chapter ? getChapterLabel(chapter.title, chapter.chapter_id) : "";

  // i18n-missing: no catalog keys for chapter SEO meta strings
  const metaTitle = chapter 
    ? `Read ${chapterLabel} - ${chapter.novel_title} | ${siteName}` 
    : `Loading Chapter | ${siteName}`;
  
  // i18n-missing: no catalog keys for chapter SEO meta strings
  const metaDescription = chapter 
    ? `Read ${chapterLabel} of the light novel ${chapter.novel_title}. ${chapter.body ? chapter.body.substring(0, 150).replace(/<[^>]+>/g, '') + '...' : `Continue reading ${chapter.novel_title} on ${siteName}.`}`
    : `Loading chapter content. Read light novels online on ${siteName}.`;
  
  // i18n-missing: no catalog keys for chapter SEO meta strings
  const metaKeywords = chapter 
    ? `${chapter.novel_title}, ${chapter.source_name}, ${chapterLabel}, read light novel, online reader, web novel`
    : "light novel, web novel, chapter reader, online reading";
  
  const ogImage = chapter?.source_overview_image_url 
    ? chapter.source_overview_image_url 
    : `${window.location.origin}${DEFAULT_OG_IMAGE}`;

  return (
    <>
      <title>{metaTitle}</title>
      <meta name="description" content={metaDescription} />
      <meta name="keywords" content={metaKeywords} />
      <link rel="canonical" href={pageUrl} />

      <meta property="og:title" content={metaTitle} />
      <meta property="og:description" content={metaDescription} />
      <meta property="og:type" content="article" />
      <meta property="og:url" content={pageUrl} />
      <meta property="og:site_name" content={siteName} />
      <meta property="og:image" content={ogImage} />
      {chapter && <meta property="article:section" content={chapter.novel_title} />}

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={metaTitle} />
      <meta name="twitter:description" content={metaDescription} />
      <meta name="twitter:image" content={ogImage} />
    </>
  );
};

export default ChapterSEO;
