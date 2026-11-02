import type { ReaderSettings } from '../readerSettingsSchema';
import type { ScreenZone } from './ScreenZoneMap';
import type { SettingsPageId } from './settingsPages';

export interface SettingsIndexEntry {
  // The data-setting-id of the row on its page, and the suffix of its keywords key
  id: string;
  labelKey: string;
  keywordsKey: string;
  page: SettingsPageId;
  // Screen zone to show on the gestures page
  zone?: ScreenZone;
  // The settings this entry covers, checked against defaultSettings by the coverage test
  settingKeys: (keyof ReaderSettings)[];
}

const entry = (
  id: string,
  labelKey: string,
  page: SettingsPageId,
  settingKeys: (keyof ReaderSettings)[],
  zone?: ScreenZone,
): SettingsIndexEntry => ({ id, labelKey, keywordsKey: `readerSettingsSearch.${id}`, page, zone, settingKeys });

// Every setting the search can jump to. Listening rows have no row of their own: they open the page only.
export const SETTINGS_INDEX: SettingsIndexEntry[] = [
  entry('fontFamily', 'fontSettings.font', 'text', ['fontFamily']),
  entry('fontSize', 'readerDisplay.modules.size.label', 'text', ['fontSize']),
  entry('textAlign', 'readerDisplay.modules.align.label', 'text', ['textAlign']),
  entry('lineSpacing', 'readerDisplay.modules.line.label', 'text', ['lineSpacing']),
  entry('paragraphSpacing', 'readerSettingsPages.betweenParagraphs', 'text', ['paragraphSpacing']),
  entry('margin', 'readerSettingsPages.sideMargins', 'text', ['margin']),
  entry('wordSpacing', 'readerSettingsPages.betweenWords', 'text', ['wordSpacing']),
  entry('letterSpacing', 'readerSettingsPages.betweenLetters', 'text', ['letterSpacing']),
  entry('paragraphIndent', 'readerSettingsPages.indentFirstLine', 'text', ['paragraphIndent']),

  entry('colorTheme', 'readerSettingsPages.colorTheme', 'colors', []),
  entry('backgroundColor', 'colorSettings.background', 'colors', ['backgroundColor']),
  entry('fontColor', 'readerSettingsPages.textLabel', 'colors', ['fontColor']),
  entry('readability', 'readerSettingsPages.readability', 'colors', []),
  entry('dimLevel', 'readerSettingsPages.screenDim', 'colors', ['dimLevel']),
  entry('nightSchedule', 'readerSettingsPages.onSchedule', 'colors', [
    'nightModeScheduleEnabled',
    'nightModeStartTime',
    'nightModeEndTime',
  ]),
  entry('nightModeStrength', 'readerSettingsPages.strength', 'colors', ['nightModeStrength']),
  entry('nightMode', 'readerSettingsPages.nightFilter', 'colors', ['nightMode']),

  entry('displaySheet', 'readerSettingsPages.pages.custom', 'custom', ['displaySheetModules']),

  entry('keyboardNavigation', 'keyboardSettings.enable', 'keys', ['keyboardNavigation']),
  entry('keyArrowLeft', 'keyboardSettings.arrowLeft', 'keys', ['keyArrowLeft']),
  entry('keyArrowRight', 'keyboardSettings.arrowRight', 'keys', ['keyArrowRight']),
  entry('keyArrowUp', 'keyboardSettings.arrowUp', 'keys', ['keyArrowUp']),
  entry('keyArrowDown', 'keyboardSettings.arrowDown', 'keys', ['keyArrowDown']),
  entry('keyPageUp', 'keyboardSettings.pageUp', 'keys', ['keyPageUp']),
  entry('keyPageDown', 'keyboardSettings.pageDown', 'keys', ['keyPageDown']),
  entry('keySpace', 'keyboardSettings.space', 'keys', ['keySpace']),
  entry('keyC', 'readerSettingsPages.keyC', 'keys', ['keyC']),
  entry('keyD', 'readerSettingsPages.keyD', 'keys', ['keyD']),

  entry('controlsTrigger', 'readerSettingsPages.showControlsWith', 'touch', ['controlsTrigger'], 'middle'),
  entry('swipeLeftGesture', 'gestureSettings.swipeLeft', 'touch', ['swipeLeftGesture']),
  entry('swipeRightGesture', 'gestureSettings.swipeRight', 'touch', ['swipeRightGesture']),
  entry('edgeTap', 'readerSettingsPages.tapThisEdge', 'touch', ['leftEdgeTapBehavior', 'rightEdgeTapBehavior'], 'right'),
  entry('dimGestureSide', 'readerSettingsPages.slideToDim', 'touch', ['dimGestureSide', 'dimGestureWidth'], 'right'),

  entry('readerHeaderBehavior', 'readerSettingsPages.siteHeader', 'reading', ['readerHeaderBehavior']),
  entry('markReadBehavior', 'behaviorSettings.markAsReadBehavior', 'reading', ['markReadBehavior']),
  entry('textSelectable', 'behaviorSettings.allowSelection', 'reading', ['textSelectable']),
  entry('savePosition', 'behaviorSettings.rememberPosition', 'reading', ['savePosition']),
  entry('hideScrollbar', 'layoutSettings.hideScrollbar', 'reading', ['hideScrollbar']),

  entry('ttsEngine', 'ttsSettings.engine', 'listen', ['ttsEngine', 'ttsBrowserVoices', 'ttsNeuralVoices']),
  entry('ttsLanguage', 'ttsSettings.language', 'listen', ['ttsLanguage']),
  entry('ttsQuality', 'ttsSettings.quality', 'listen', ['ttsKokoroDevice', 'ttsSupertonicDevice', 'ttsSupertonicSteps']),
  entry('ttsThrottle', 'ttsSettings.throttle', 'listen', ['ttsThrottle']),
  entry('ttsAutoScroll', 'ttsSettings.autoScroll', 'listen', ['ttsAutoScroll']),
  entry('ttsAutoNextChapter', 'ttsSettings.autoNextChapter', 'listen', ['ttsAutoNextChapter']),
  entry('ttsReadTitle', 'ttsSettings.readTitle', 'listen', ['ttsReadTitle']),
  entry('ttsSkipNotes', 'ttsSettings.skipNotes', 'listen', ['ttsSkipNotes']),
  entry('ttsTapToSeek', 'ttsSettings.tapToSeek', 'listen', ['ttsTapToSeek']),
  entry('ttsRate', 'ttsSettings.speed', 'listen', ['ttsRate']),
  entry('ttsPitch', 'ttsSettings.pitch', 'listen', ['ttsPitch']),
  entry('ttsVolume', 'ttsSettings.volume', 'listen', ['ttsVolume']),
  entry('ttsParagraphPause', 'ttsSettings.paragraphPause', 'listen', ['ttsParagraphPause']),
  entry('ttsHighlight', 'ttsSettings.highlight', 'listen', ['ttsHighlight']),
  entry('ttsKeepScreenOn', 'ttsSettings.keepScreenOn', 'listen', ['ttsKeepScreenOn']),

  entry('importSettings', 'readerSettings.import', 'backup', []),
  entry('exportSettings', 'readerSettings.export', 'backup', []),
  entry('resetDefaults', 'readerSettings.resetDefaults', 'backup', []),
];
