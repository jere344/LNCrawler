import type { ReactNode } from 'react';

export const DEFAULT_OG_IMAGE = '/og-image.jpg';
const SITE_NAME = 'LNCrawler';

interface SeoMetaProps {
  title: string;
  description: string;
  keywords?: string;
  image?: string;
  type?: string;
  canonical?: string;
  children?: ReactNode;
}

const SeoMeta = ({
  title,
  description,
  keywords,
  image = DEFAULT_OG_IMAGE,
  type = 'website',
  canonical,
  children,
}: SeoMetaProps) => {
  const url = canonical ?? window.location.href;
  return (
    <>
      <title>{title}</title>
      <meta name="description" content={description} />
      {keywords && <meta name="keywords" content={keywords} />}
      <link rel="canonical" href={url} />

      <meta property="og:title" content={title} />
      <meta property="og:description" content={description} />
      <meta property="og:type" content={type} />
      <meta property="og:url" content={url} />
      <meta property="og:site_name" content={SITE_NAME} />
      <meta property="og:image" content={image} />
      {children}

      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={title} />
      <meta name="twitter:description" content={description} />
      <meta name="twitter:image" content={image} />
    </>
  );
};

export default SeoMeta;
