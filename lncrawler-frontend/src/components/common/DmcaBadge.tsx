import React from 'react';
import { Chip } from '@mui/material';
import { useTranslation } from 'react-i18next';

interface DmcaBadgeProps {
    top?: number;
    bottom?: number;
    left?: number;
    zIndex?: number;
}

/**
 * "DMCA" chip shown on a novel removed after a takedown request. Callers pick
 * the cover corner it sits in.
 */
export const DmcaBadge: React.FC<DmcaBadgeProps> = ({ top, bottom, left = 8, zIndex = 2 }) => {
    const { t } = useTranslation();
    return (
        <Chip
            label={t('common.dmca')}
            color="error"
            size="small"
            sx={{ position: 'absolute', top, bottom, left, zIndex, fontWeight: 'bold' }}
        />
    );
};
