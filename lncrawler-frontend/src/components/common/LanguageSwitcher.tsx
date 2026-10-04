import { useState } from 'react';
import {
    IconButton,
    Menu,
    MenuItem,
    ListItemIcon,
    ListItemText,
    Avatar,
    Box,
    Tooltip,
} from '@mui/material';
import LanguageIcon from '@mui/icons-material/Language';
import CheckIcon from '@mui/icons-material/Check';
import { useTranslation } from 'react-i18next';
import { useLanguage } from '@context/LanguageContext';
import { availableLanguages, languageFlagUrl, languageCodeToName } from '@utils/Misc';
import i18n from '../../i18n';

// Compact interface-language picker for the header. Works logged out: the
// chosen language is stored locally by LanguageContext and applied to i18next.
const LanguageSwitcher = () => {
    const { t } = useTranslation();
    const { uiLanguage, setUiLanguage } = useLanguage();
    const [anchor, setAnchor] = useState<null | HTMLElement>(null);

    const activeLanguage = uiLanguage || i18n.resolvedLanguage || 'en';
    const flag = languageFlagUrl(activeLanguage);

    const handleClose = () => setAnchor(null);

    const handleSelect = (code: string) => {
        setUiLanguage(code);
        handleClose();
    };

    return (
        <>
            <Tooltip title={t('header.language')}>
                <IconButton
                    onClick={(e) => setAnchor(e.currentTarget)}
                    color="inherit"
                    aria-label={t('header.language')}
                >
                    <Avatar
                        src={flag}
                        sx={{ width: 24, height: 16, borderRadius: 0.5 }}
                    >
                        <LanguageIcon fontSize="small" />
                    </Avatar>
                </IconButton>
            </Tooltip>
            <Menu
                anchorEl={anchor}
                open={Boolean(anchor)}
                onClose={handleClose}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
                transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            >
                <MenuItem value="" selected={!uiLanguage} onClick={() => handleSelect('')}>
                    {!uiLanguage && (
                        <ListItemIcon>
                            <CheckIcon fontSize="small" />
                        </ListItemIcon>
                    )}
                    <ListItemText inset={!!uiLanguage} primary={t('profileLanguage.automatic')} />
                </MenuItem>
                {availableLanguages.map((code) => (
                    <MenuItem key={code} selected={activeLanguage === code} onClick={() => handleSelect(code)}>
                        {activeLanguage === code && (
                            <ListItemIcon>
                                <CheckIcon fontSize="small" />
                            </ListItemIcon>
                        )}
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pl: activeLanguage === code ? 0 : 3 }}>
                            <Avatar
                                src={languageFlagUrl(code)}
                                sx={{ width: 22, height: 15, borderRadius: 0.5 }}
                            />
                            {languageCodeToName(t, code)}
                        </Box>
                    </MenuItem>
                ))}
            </Menu>
        </>
    );
};

export default LanguageSwitcher;
