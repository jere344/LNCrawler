import React from 'react';
import { Chip } from '@mui/material';
import { useAdultContent } from '@context/AdultContentContext';

/**
 * Small "R18" chip shown over a blurred adult cover. Clicking it (or the
 * cover) reveals that one cover for the session. Renders nothing unless the
 * cover is still hidden. `forceAdult` extends the blur to 'no' mode for the
 * viewer's own content.
 */
export const AdultBadge: React.FC<{ isAdult?: boolean; novelId?: string; forceAdult?: boolean }> = ({ isAdult, novelId, forceAdult }) => {
    const { isBlurred, revealHandler } = useAdultContent();
    if (!isBlurred(isAdult, novelId, forceAdult)) return null;
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
