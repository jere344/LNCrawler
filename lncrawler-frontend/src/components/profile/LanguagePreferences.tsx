import React from 'react';
import {
    Box,
    Typography,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Autocomplete,
    TextField,
    FormControlLabel,
    Switch,
    Chip,
    Avatar,
    Divider,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '@context/LanguageContext';
import { availableLanguages, languageFlagUrl, languageCodeToName } from '@utils/Misc';

const LanguagePreferences: React.FC = () => {
    const { t } = useTranslation();
    const {
        uiLanguage,
        contentLanguages,
        languageFilterEnabled,
        setUiLanguage,
        setContentLanguages,
        setLanguageFilterEnabled,
    } = useLanguage();

    return (
        <Box sx={{ mt: 4 }}>
            <Typography variant="h6" gutterBottom>
                {t('profileLanguage.heading')}
            </Typography>

            <FormControl fullWidth margin="normal">
                <InputLabel id="ui-language-label">{t('profileLanguage.interfaceLanguage')}</InputLabel>
                <Select
                    labelId="ui-language-label"
                    label={t('profileLanguage.interfaceLanguage')}
                    value={uiLanguage}
                    onChange={(e) => setUiLanguage(e.target.value)}
                    renderValue={(code) => (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            {code && (
                                <Avatar src={languageFlagUrl(code)} sx={{ width: 22, height: 15, borderRadius: 0.5 }} />
                            )}
                            {code ? languageCodeToName(t, code) : t('profileLanguage.automatic')}
                        </Box>
                    )}
                >
                    <MenuItem value="">
                        <em>{t('profileLanguage.automatic')}</em>
                    </MenuItem>
                    {availableLanguages.map((code) => (
                        <MenuItem key={code} value={code}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Avatar src={languageFlagUrl(code)} sx={{ width: 22, height: 15, borderRadius: 0.5 }} />
                                {languageCodeToName(t, code)}
                            </Box>
                        </MenuItem>
                    ))}
                </Select>
            </FormControl>

            <FormControlLabel
                sx={{ mt: 2, display: 'flex' }}
                control={
                    <Switch
                        checked={languageFilterEnabled}
                        onChange={(e) => setLanguageFilterEnabled(e.target.checked)}
                    />
                }
                label={t('profileLanguage.showOnlyMine')}
            />

            <Box sx={{ mt: 2 }}>
                <Autocomplete<string, true, false, false>
                    multiple
                    disableCloseOnSelect
                    options={availableLanguages}
                    value={contentLanguages}
                    onChange={(_e, value) => setContentLanguages(value)}
                    getOptionLabel={(code) => languageCodeToName(t, code)}
                    isOptionEqualToValue={(option, value) => option === value}
                    renderOption={(props, code) => (
                        <li {...props} key={code}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                <Avatar src={languageFlagUrl(code)} sx={{ width: 22, height: 15, borderRadius: 0.5 }} />
                                {languageCodeToName(t, code)}
                            </Box>
                        </li>
                    )}
                    renderValue={(value, getItemProps) =>
                        value.map((code, index) => (
                            <Chip
                                label={languageCodeToName(t, code)}
                                avatar={<Avatar src={languageFlagUrl(code)} />}
                                {...getItemProps({ index })}
                                key={code}
                            />
                        ))
                    }
                    renderInput={(params) => (
                        <TextField
                            {...params}
                            variant="outlined"
                            label={t('profileLanguage.contentLanguages')}
                            placeholder={t('profileLanguage.contentPlaceholder')}
                            helperText={t('profileLanguage.contentHelper')}
                        />
                    )}
                />
            </Box>

            <Divider sx={{ my: 3 }} />
        </Box>
    );
};

export default LanguagePreferences;
