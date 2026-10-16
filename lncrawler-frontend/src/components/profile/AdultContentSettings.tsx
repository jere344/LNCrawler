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
import { ShowR18 } from '@models/user_types';

const VALUES: ShowR18[] = ['no', 'yes', 'blur'];

const AdultContentSettings: React.FC = () => {
    const { t } = useTranslation();
    const { user, updateProfile } = useAuth();
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const current = user?.show_r18 || 'no';

    const handleChange = async (value: ShowR18) => {
        setSaving(true);
        setError(null);
        try {
            await updateProfile({ show_r18: value });
        } catch (err) {
            console.error('Error saving adult content setting:', err);
            setError(t('adultSettings.saveError'));
        } finally {
            setSaving(false);
        }
    };

    return (
        <Box>
            <Typography variant="h6" gutterBottom>
                {t('adultSettings.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t('adultSettings.description')}
            </Typography>
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography sx={{ flex: 1 }}>{t('adultSettings.label')}</Typography>
                <FormControl size="small" sx={{ minWidth: 160 }}>
                    <InputLabel>{t('adultSettings.label')}</InputLabel>
                    <Select
                        label={t('adultSettings.label')}
                        value={current}
                        onChange={(e) => handleChange(e.target.value as ShowR18)}
                        disabled={saving}
                        endAdornment={saving ? <CircularProgress size={16} /> : undefined}
                    >
                        {VALUES.map((value) => (
                            <MenuItem key={value} value={value}>
                                {t(`adultSettings.values.${value}`)}
                            </MenuItem>
                        ))}
                    </Select>
                </FormControl>
            </Box>
        </Box>
    );
};

export default AdultContentSettings;
