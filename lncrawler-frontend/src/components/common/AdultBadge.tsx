import React from 'react';
import { Chip } from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAdultContent } from '@context/AdultContentContext';

/**
 * Small "R18" chip shown over a blurred adult cover. Clicking it (or the
 * cover) reveals that one cover for the session. Renders nothing unless the
 * cover is still hidden.
 */
export const AdultBadge: React.FC<{ isAdult?: boolean; novelId?: string }> = ({ isAdult, novelId }) => {
    const { t } = useTranslation();
    const { isBlurred, revealHandler } = useAdultContent();
    if (!isBlurred(isAdult, novelId)) return null;
    return (
        <Chip
            label={t('common.r18')}
            color="warning"
            size="small"
            onClick={revealHandler(novelId)}
            sx={{ position: 'absolute', top: 8, left: 8, zIndex: 2, fontWeight: 'bold', cursor: 'pointer' }}
        />
    );
};
