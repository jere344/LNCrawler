import React from 'react';
import { Chip } from '@mui/material';
import { useAdultContent } from '@context/AdultContentContext';

/**
 * Small "R18" chip shown over a blurred adult cover. Clicking it (or the
 * cover) reveals that one cover for the session. Renders nothing unless the
 * account is in 'blur' mode and the cover is still hidden.
 */
export const AdultBadge: React.FC<{ isAdult?: boolean; novelId?: string }> = ({ isAdult, novelId }) => {
    const { blurCovers, isRevealed, revealHandler } = useAdultContent();
    if (!blurCovers || !isAdult || isRevealed(novelId)) return null;
    return (
        <Chip
            label="R18"
            color="warning"
            size="small"
            onClick={revealHandler(novelId)}
            sx={{ position: 'absolute', top: 8, left: 8, zIndex: 2, fontWeight: 'bold', cursor: 'pointer' }}
        />
    );
};
