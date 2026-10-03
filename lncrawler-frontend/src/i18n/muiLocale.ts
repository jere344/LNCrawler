import { enUS, frFR, esES, deDE, itIT, jaJP, koKR, zhCN, ptBR, ruRU, arSA, hiIN, thTH, viVN, idID, trTR, plPL, nlNL, svSE, daDK } from '@mui/material/locale';
import type { Localization } from '@mui/material/locale';

// Map our flat language codes to the MUI locale packs.
const MUI_LOCALES: Record<string, Localization> = {
    en: enUS,
    fr: frFR,
    es: esES,
    de: deDE,
    it: itIT,
    ja: jaJP,
    ko: koKR,
    zh: zhCN,
    pt: ptBR,
    ru: ruRU,
    ar: arSA,
    hi: hiIN,
    th: thTH,
    vi: viVN,
    id: idID,
    tr: trTR,
    pl: plPL,
    nl: nlNL,
    sv: svSE,
    da: daDK,
};

export const getMuiLocale = (code: string): Localization => MUI_LOCALES[code] ?? enUS;

export const muiDirection = (code: string): 'rtl' | 'ltr' => (code === 'ar' ? 'rtl' : 'ltr');
