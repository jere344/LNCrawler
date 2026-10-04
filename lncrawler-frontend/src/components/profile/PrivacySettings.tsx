import React, { useState } from 'react';
import {
    Box,
    Typography,
    FormControl,
    Select,
    MenuItem,
    InputLabel,
    Alert,
    CircularProgress,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@context/AuthContext';
import { PrivacySection, PrivacyValue } from '@models/user_types';

const SECTIONS: PrivacySection[] = [
    'library',
    'library_notes',
    'library_ratings',
    'reading_lists',
    'reviews',
    'comments',
    'stats',
    'reading_history',
    'friends',
];

const VALUES: PrivacyValue[] = ['public', 'friends', 'private'];

const PrivacySettings: React.FC = () => {
    const { t } = useTranslation();
    const { user, updateProfile } = useAuth();
    const [saving, setSaving] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const settings = user?.privacy_settings || {};
    const current = (section: PrivacySection): PrivacyValue =>
        (settings[section] as PrivacyValue) || 'private';

    const handleChange = async (section: PrivacySection, value: PrivacyValue) => {
        setSaving(section);
        setError(null);
        try {
            await updateProfile({ privacy_settings: { ...settings, [section]: value } });
        } catch (err) {
            console.error('Error saving privacy settings:', err);
            setError(t('privacy.saveError'));
        } finally {
            setSaving(null);
        }
    };

    return (
        <Box>
            <Typography variant="h6" gutterBottom>
                {t('privacy.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t('privacy.description')}
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            {SECTIONS.map((section) => (
                <Box key={section} sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1.5 }}>
                    <Typography sx={{ flex: 1 }}>{t(`privacy.sections.${section}`)}</Typography>
                    <FormControl size="small" sx={{ minWidth: 160 }}>
                        <InputLabel>{t('privacy.visibility')}</InputLabel>
                        <Select
                            label={t('privacy.visibility')}
                            value={current(section)}
                            onChange={(e) => handleChange(section, e.target.value as PrivacyValue)}
                            disabled={saving === section}
                            endAdornment={saving === section ? <CircularProgress size={16} /> : undefined}
                        >
                            {VALUES.map((value) => (
                                <MenuItem key={value} value={value}>
                                    {t(`privacy.values.${value}`)}
                                </MenuItem>
                            ))}
                        </Select>
                    </FormControl>
                </Box>
            ))}
        </Box>
    );
};

export default PrivacySettings;
