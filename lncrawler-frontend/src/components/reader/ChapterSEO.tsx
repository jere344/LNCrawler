import { useTranslation } from 'react-i18next';
import { ChapterContent } from '@models/novels_types';
import { getChapterLabel } from '@utils/Misc';
import SeoMeta, { DEFAULT_OG_IMAGE } from '@components/common/SeoMeta';

interface ChapterSEOProps {
  chapter: ChapterContent | null;
}

const ChapterSEO = ({ chapter }: ChapterSEOProps) => {
  const { t } = useTranslation();
  const pageUrl = window.location.href;
  const siteName = "LNCrawler";
  const chapterLabel = chapter ? getChapterLabel(t, chapter.title, chapter.chapter_id) : "";

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
    <SeoMeta
      title={metaTitle}
      description={metaDescription}
      keywords={metaKeywords}
      image={ogImage}
      type="article"
      canonical={pageUrl}
    >
      {chapter && <meta property="article:section" content={chapter.novel_title} />}
    </SeoMeta>
  );
};

export default ChapterSEO;
