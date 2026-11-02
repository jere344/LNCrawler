import { useEffect, useRef, useState } from 'react';
import { Box, Button, IconButton, Stack } from '@mui/material';
import { alpha, useTheme } from '@mui/material/styles';
import { useTranslation } from 'react-i18next';
import CloseIcon from '@mui/icons-material/Close';
import { useAuth } from '@context/AuthContext';
import type { ReaderLayoutMode } from '../hooks/useReaderLayout';
import { usePrefersReducedMotion } from '../hooks/usePrefersReducedMotion';
import ReaderPanelFrame from '../panels/ReaderPanelFrame';
import { SETTINGS_PAGES, SETTINGS_PAGE_ORDER, type SettingsPageId } from './settingsPages';
import SettingsHome from './SettingsHome';
import SettingsSearch from './SettingsSearch';
import type { SettingsIndexEntry } from './settingsIndex';
import { SettingsContext } from './settingsContext';

// The controls a jump moves focus to, in the first row that has one
const FOCUSABLE = 'button, input, select, [role="combobox"], [role="radio"], [role="switch"]';

interface AllSettingsPanelProps {
  mode: ReaderLayoutMode;
  // Page to open first; without one, the panel opens on the home (text on desktop)
  initialPage?: SettingsPageId;
  novelLanguage: string;
  hasNarration: boolean;
  onBeforePreview?: () => void;
  // Back past the first page: closes the panel, or returns to the display sheet
  onBack: () => void;
  // Desktop close button
  onClose: () => void;
}

// Every setting, in one panel. Phones and tablets push pages over the home; desktop shows a nav beside the page.
const AllSettingsPanel = ({
  mode,
  initialPage,
  novelLanguage,
  hasNarration,
  onBeforePreview,
  onBack,
  onClose,
}: AllSettingsPanelProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const isDesktop = mode === 'desktop';
  // Phones and tablets: the page pushed over the home, or null for the home itself
  const [pushedPage, setPushedPage] = useState<SettingsPageId | null>(initialPage ?? null);
  // Desktop: the page open in the nav's right column
  const [deskPage, setDeskPage] = useState<SettingsPageId>(initialPage ?? 'text');
  const [query, setQuery] = useState('');
  // The setting a search result asked for; the nonce makes each choice a new jump, even to the same row
  const [jump, setJump] = useState<{ id: string; zone?: SettingsIndexEntry['zone']; nonce: number } | null>(null);
  const searching = query.trim() !== '';

  const page = isDesktop ? deskPage : pushedPage;
  const title = page ? t(SETTINGS_PAGES[page].titleKey) : t('readerSettingsPages.title');

  // A page opened directly has no home behind it, so back leaves the panel
  const goBack = () => {
    if (!isDesktop && pushedPage !== null && !initialPage) setPushedPage(null);
    else onBack();
  };

  // Opens the page the setting lives on. Backup is at the foot of the phone home, so it goes there.
  const chooseResult = ({ id, page: resultPage, zone }: SettingsIndexEntry) => {
    setQuery('');
    if (isDesktop) setDeskPage(resultPage);
    else setPushedPage(resultPage === 'backup' ? null : resultPage);
    setJump({ id, zone, nonce: (jump?.nonce ?? 0) + 1 });
  };

  const PageComponent = page ? SETTINGS_PAGES[page].Component : null;

  // A new page starts at the top. The body is the scrolling box that holds this wrapper.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bodyRef.current?.parentElement?.scrollTo({ top: 0 });
  }, [page]);

  // A search result: bring its row into view, flash it and focus its first control, once per jump
  const handledNonce = useRef(0);
  const reducedMotion = usePrefersReducedMotion();
  useEffect(() => {
    if (!jump || jump.nonce === handledNonce.current) return;
    handledNonce.current = jump.nonce;
    // The zone only applies when the page opens, so later visits start on the default zone
    setJump((current) => current && { ...current, zone: undefined });
    const row = bodyRef.current?.querySelector<HTMLElement>(`[data-setting-id="${jump.id}"]`);
    if (!row) return;
    row.scrollIntoView({ block: 'center' });
    if (!reducedMotion) {
      row.animate(
        [{ backgroundColor: alpha(theme.palette.primary.main, 0.25) }, { backgroundColor: 'transparent' }],
        { duration: 1200 },
      );
    }
    row.querySelector<HTMLElement>(FOCUSABLE)?.focus({ preventScroll: true });
  }, [jump, theme, reducedMotion]);

  return (
    <SettingsContext.Provider value={{ mode, novelLanguage, hasNarration, onBeforePreview, isAuthenticated }}>
      <ReaderPanelFrame
        title={title}
        mode={mode}
        onBack={goBack}
        showBack={!isDesktop}
        headerExtra={isDesktop ? (
          <IconButton onClick={onClose} aria-label={t('readerDisplay.close')}>
            <CloseIcon />
          </IconButton>
        ) : undefined}
      >
        <Box ref={bodyRef} sx={{ minHeight: '100%' }}>
          {(isDesktop || pushedPage === null) && (
            <SettingsSearch query={query} onQueryChange={setQuery} onChoose={chooseResult} onClose={onClose} />
          )}
          {searching ? null : isDesktop ? (
            <Box sx={{ display: 'flex', gap: 3, minHeight: '100%' }}>
              <Stack component="nav" aria-label={t('readerSettingsPages.title')} spacing={0.5} sx={{ width: 200, flexShrink: 0 }}>
                {SETTINGS_PAGE_ORDER.map((id) => {
                  const { Icon, titleKey } = SETTINGS_PAGES[id];
                  const current = id === deskPage;
                  return (
                    <Button
                      key={id}
                      startIcon={<Icon />}
                      aria-current={current ? 'page' : undefined}
                      onClick={() => setDeskPage(id)}
                      sx={{ justifyContent: 'flex-start', textAlign: 'start', fontWeight: current ? 700 : 400 }}
                    >
                      {t(titleKey)}
                    </Button>
                  );
                })}
              </Stack>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                {PageComponent && <PageComponent key={jump?.nonce ?? 0} initialZone={jump?.zone} />}
              </Box>
            </Box>
          ) : PageComponent ? (
            <PageComponent key={jump?.nonce ?? 0} initialZone={jump?.zone} />
          ) : (
            <SettingsHome onOpen={setPushedPage} />
          )}
        </Box>
      </ReaderPanelFrame>
    </SettingsContext.Provider>
  );
};

export default AllSettingsPanel;
