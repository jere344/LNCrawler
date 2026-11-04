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
  // The pages pushed over the home, bottom first; the last one is on screen (the desktop nav's page is the last)
  pages: SettingsPageId[];
  // The search field has a query, which is a layer of its own
  searching: boolean;
  novelLanguage: string;
  hasNarration: boolean;
  // The chapter being read, for the listening status
  chapterNumber?: number;
  onBeforePreview?: () => void;
  // One level up: the back arrow, Escape, and clearing the search
  onBack: () => void;
  onPushPage: (page: SettingsPageId) => void;
  // Shows a page in place of the current entry (desktop nav, search result); null is the home
  onSetDeskPage: (page: SettingsPageId | null) => void;
  onStartSearch: () => void;
  // Desktop close button
  onClose: () => void;
}

// Every setting, in one panel. Phones and tablets push pages over the home; desktop shows a nav beside the page.
const AllSettingsPanel = ({
  mode,
  pages,
  searching,
  novelLanguage,
  hasNarration,
  chapterNumber,
  onBeforePreview,
  onBack,
  onPushPage,
  onSetDeskPage,
  onStartSearch,
  onClose,
}: AllSettingsPanelProps) => {
  const { t } = useTranslation();
  const theme = useTheme();
  const { isAuthenticated } = useAuth();
  const isDesktop = mode === 'desktop';
  // The page on screen: the last one pushed. Phones and tablets show the home without one; desktop starts on text.
  const lastPage: SettingsPageId | undefined = pages[pages.length - 1];
  const page = lastPage ?? (isDesktop ? 'text' : null);
  // The desktop nav highlights the page at the root of the stack, so a subpage keeps its parent highlighted
  const navPage = pages[0] ?? 'text';
  // Desktop shows a subpage over its parent: Back returns to the parent, and there is no close button
  const nested = isDesktop && pages.length > 1;
  const [query, setQuery] = useState('');
  // The setting a search result asked for, and the page it is on; the nonce makes each choice a new jump, even to the same row
  const [jump, setJump] = useState<{ id: string; zone?: SettingsIndexEntry['zone']; page: SettingsPageId | null; nonce: number } | null>(null);
  const hasQuery = query.trim() !== '';
  const title = page ? t(SETTINGS_PAGES[page].titleKey) : t('readerSettingsPages.title');

  // The first query pushes the search layer; clearing the field pops it (Back does too)
  const changeQuery = (next: string) => {
    const nextHasQuery = next.trim() !== '';
    setQuery(next);
    if (nextHasQuery && !searching) onStartSearch();
    else if (!nextHasQuery && searching) onBack();
  };
  // Back past the search layer clears the field
  useEffect(() => {
    if (!searching) setQuery('');
  }, [searching]);

  // Opens the page the setting lives on. Backup is at the foot of the phone home, so it goes there.
  const chooseResult = ({ id, page: resultPage, zone }: SettingsIndexEntry) => {
    setQuery('');
    const shown = !isDesktop && resultPage === 'backup' ? null : resultPage;
    onSetDeskPage(shown);
    setJump({ id, zone, page: shown, nonce: (jump?.nonce ?? 0) + 1 });
  };

  const PageComponent = page ? SETTINGS_PAGES[page].Component : null;

  // A new page starts at the top. The body is the scrolling box that holds this wrapper.
  const bodyRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bodyRef.current?.parentElement?.scrollTo({ top: 0 });
  }, [page]);

  // A search result: bring its row into view, flash it and focus its first control, once per jump.
  // On desktop the page is shown after the search entry is dropped, so the jump waits for that page.
  const handledNonce = useRef(0);
  const reducedMotion = usePrefersReducedMotion();
  useEffect(() => {
    if (!jump || jump.nonce === handledNonce.current || jump.page !== page) return;
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
  }, [jump, page, theme, reducedMotion]);

  return (
    <SettingsContext.Provider
      value={{ mode, novelLanguage, hasNarration, chapterNumber, onOpenPage: onPushPage, onBeforePreview, isAuthenticated }}
    >
      <ReaderPanelFrame
        title={title}
        mode={mode}
        onBack={onBack}
        showBack={!isDesktop || nested}
        headerExtra={isDesktop && !nested ? (
          <IconButton onClick={onClose} aria-label={t('readerDisplay.close')}>
            <CloseIcon />
          </IconButton>
        ) : undefined}
      >
        <Box ref={bodyRef} sx={{ minHeight: '100%' }}>
          {(isDesktop || page === null) && (
            <SettingsSearch query={query} onQueryChange={changeQuery} onChoose={chooseResult} onClose={onBack} />
          )}
          {hasQuery ? null : isDesktop ? (
            <Box sx={{ display: 'flex', gap: 3, minHeight: '100%' }}>
              <Stack component="nav" aria-label={t('readerSettingsPages.title')} spacing={0.5} sx={{ width: 200, flexShrink: 0 }}>
                {SETTINGS_PAGE_ORDER.map((id) => {
                  const { Icon, titleKey } = SETTINGS_PAGES[id];
                  const current = id === navPage;
                  return (
                    <Button
                      key={id}
                      startIcon={<Icon />}
                      aria-current={current ? 'page' : undefined}
                      onClick={() => onSetDeskPage(id)}
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
            <SettingsHome onOpen={onPushPage} />
          )}
        </Box>
      </ReaderPanelFrame>
    </SettingsContext.Provider>
  );
};

export default AllSettingsPanel;
