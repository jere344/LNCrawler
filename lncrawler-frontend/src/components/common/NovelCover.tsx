import React from 'react';
import { CardMedia } from '@mui/material';
import type { SxProps, Theme } from '@mui/material';
import { useAdultContent } from '@context/AdultContentContext';
import { AdultBadge } from '@components/common/AdultBadge';
import { DmcaBadge } from '@components/common/DmcaBadge';
import { AudiobookBadge } from '@components/audiobooks/AudiobookBadge';

interface NovelCoverProps {
  src?: string | null;
  alt: string;
  novelId?: string;
  isAdult?: boolean;
  isDmca?: boolean;
  dmcaBadgeProps?: React.ComponentProps<typeof DmcaBadge>;
  hasAudiobook?: boolean;
  // Shown in place of the image when there is no cover.
  fallback?: React.ReactNode;
  // Size and position of the image, set by the card.
  sx?: SxProps<Theme>;
  // Overlays of the card, drawn after the badges.
  children?: React.ReactNode;
}

/**
 * Cover image of a novel with its adult blur and reveal, plus the adult, DMCA and
 * audiobook badges. The card keeps the wrapper that positions it.
 */
export const NovelCover: React.FC<NovelCoverProps> = ({
  src,
  alt,
  novelId,
  isAdult,
  isDmca = false,
  dmcaBadgeProps = { bottom: 8 },
  hasAudiobook = false,
  fallback,
  sx,
  children,
}) => {
  const { isBlurred, revealHandler } = useAdultContent();
  const blurred = isBlurred(isAdult, novelId);

  return (
    <>
      {src ? (
        <CardMedia
          component="img"
          image={src}
          alt={alt}
          onClick={blurred ? revealHandler(novelId) : undefined}
          sx={[
            {
              objectFit: 'cover',
              opacity: isDmca ? 0.55 : 1,
              cursor: blurred ? 'pointer' : undefined,
              filter: [
                isDmca ? 'grayscale(100%)' : null,
                blurred ? 'blur(16px)' : null,
              ].filter(Boolean).join(' ') || 'none',
            },
            ...(Array.isArray(sx) ? sx : [sx]),
          ]}
        />
      ) : fallback}
      <AdultBadge isAdult={isAdult} novelId={novelId} />
      {isDmca && <DmcaBadge {...dmcaBadgeProps} />}
      {hasAudiobook && <AudiobookBadge />}
      {children}
    </>
  );
};
