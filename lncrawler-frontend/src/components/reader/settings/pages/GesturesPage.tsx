import { useState } from 'react';
import { Alert, Box, Button, FormControlLabel, Radio, RadioGroup, Switch, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import ScreenZoneMap, { type ScreenZone } from '../ScreenZoneMap';
import { SettingGroupHeading, SettingRow, SettingSelect, SettingStepper } from '../SettingRows';
import { useReaderSettings } from '../../hooks/useReaderSettings';
import { updateReaderSetting } from '../../readerSettingsStore';
import type { CenterAction, EdgeTapBehavior } from '../../readerSettingsSchema';
import { dimBandMax, dimBandWidth } from '../../readerGeometry';
import { useViewportSize } from '../../hooks/useViewportSize';
import { useSettingsContext } from '../settingsContext';

const ZONE_LABEL_KEYS: Record<ScreenZone, string> = {
  left: 'readerSettingsPages.zoneLeft',
  middle: 'readerSettingsPages.zoneMiddle',
  right: 'readerSettingsPages.zoneRight',
};

const CENTER_ACTION_LABEL_KEYS: Record<CenterAction, string> = {
  none: 'gestureSettings.doNothing',
  controls: 'gestureSettings.showControls',
  fullscreen: 'gestureSettings.fullscreen',
};

const CENTER_ACTIONS: CenterAction[] = ['controls', 'fullscreen', 'none'];

const EDGE_TAP_LABEL_KEYS: Record<EdgeTapBehavior, string> = {
  none: 'behaviorSettings.doNothing',
  scrollUp: 'behaviorSettings.scrollUp',
  scrollDown: 'behaviorSettings.scrollDown',
  chapter: 'behaviorSettings.changeChapter',
};

interface ChoiceOption {
  value: string;
  label: string;
  hint?: string;
}

interface ChoiceGroupProps {
  label: string;
  value: string;
  options: ChoiceOption[];
  onChange: (value: string) => void;
  // The data-setting-id of the group, for the settings search
  settingId?: string;
}

// A list of options, one chosen at a time, each with an optional hint under its name
const ChoiceGroup = ({ label, value, options, onChange, settingId }: ChoiceGroupProps) => (
  <RadioGroup
    aria-label={label}
    data-setting-id={settingId}
    value={value}
    onChange={(event) => onChange(event.target.value)}
  >
    {options.map((option) => (
      <FormControlLabel
        key={option.value}
        value={option.value}
        control={<Radio />}
        sx={{ alignItems: 'flex-start', mx: 0, py: 0.5 }}
        label={
          <Box>
            <Typography sx={{ fontWeight: 600 }}>{option.label}</Typography>
            {option.hint && <Typography variant="body2" color="text.secondary">{option.hint}</Typography>}
          </Box>
        }
      />
    ))}
  </RadioGroup>
);

interface GesturesPageProps {
  // The zone to open on, for the settings search
  initialZone?: ScreenZone;
}

// Swipes, then the screen zones and what each does
const GesturesPage = ({ initialZone = 'middle' }: GesturesPageProps) => {
  const { t } = useTranslation();
  const settings = useReaderSettings();
  const { mode } = useSettingsContext();
  const [zone, setZone] = useState<ScreenZone>(initialZone);

  const dimEdge = settings.dimGestureSide === 'off' ? null : settings.dimGestureSide;
  // The band width is held to the screen, but the saved width is kept
  const { width: viewportWidth } = useViewportSize();
  const bandMax = dimBandMax(viewportWidth);
  const bandWidth = dimBandWidth(settings.dimGestureWidth, viewportWidth);
  const bandPx = Math.round((viewportWidth * bandWidth) / 100);

  const edgeValue = (behavior: EdgeTapBehavior) => t(EDGE_TAP_LABEL_KEYS[behavior]);
  const middleValue = t('readerSettingsPages.centerValue', {
    single: t(CENTER_ACTION_LABEL_KEYS[settings.centerSingleTap]),
    double: t(CENTER_ACTION_LABEL_KEYS[settings.centerDoubleTap]),
    long: t(CENTER_ACTION_LABEL_KEYS[settings.centerLongPress]),
  });

  const items = {
    left: { label: t(ZONE_LABEL_KEYS.left), value: edgeValue(settings.leftEdgeTapBehavior) },
    middle: { label: t(ZONE_LABEL_KEYS.middle), value: middleValue },
    right: { label: t(ZONE_LABEL_KEYS.right), value: edgeValue(settings.rightEdgeTapBehavior) },
  };

  const centerOptions = CENTER_ACTIONS.map((action) => ({
    value: action,
    label: t(CENTER_ACTION_LABEL_KEYS[action]),
  }));
  const edgeOptions = (Object.keys(EDGE_TAP_LABEL_KEYS) as EdgeTapBehavior[]).map((behavior) => ({
    value: behavior,
    label: t(EDGE_TAP_LABEL_KEYS[behavior]),
  }));
  const swipeOptions = [
    { value: 'none', label: t('gestureSettings.doNothing') },
    { value: 'prevChapter', label: t('gestureSettings.previousChapter') },
    { value: 'nextChapter', label: t('gestureSettings.nextChapter') },
    { value: 'chapterList', label: t('gestureSettings.chapterList') },
    { value: 'comments', label: t('gestureSettings.comments') },
  ];

  const renderMiddle = () => (
    <>
      <SettingSelect settingKey="centerSingleTap" settingId="centerSingleTap" title={t('readerSettingsPages.trigger.singleTap')} options={centerOptions} />
      <SettingSelect settingKey="centerDoubleTap" settingId="centerDoubleTap" title={t('readerSettingsPages.trigger.doubleTap')} options={centerOptions} />
      <SettingSelect settingKey="centerLongPress" settingId="centerLongPress" title={t('readerSettingsPages.trigger.longPress')} options={centerOptions} />
      {settings.centerLongPress !== 'none' && settings.textSelectable && (
        <Alert severity="warning" sx={{ mt: 1.5 }}>
          <Typography variant="body2">{t('readerSettingsPages.longPressWarning')}</Typography>
          <Button size="small" onClick={() => updateReaderSetting('textSelectable', false)} sx={{ mt: 0.5 }}>
            {t('readerSettingsPages.turnOffSelection')}
          </Button>
        </Alert>
      )}
    </>
  );

  // Left or right edge: what a tap does, and the slide-to-dim band on this edge
  const renderEdge = (edge: 'left' | 'right') => {
    const tapKey = edge === 'left' ? 'leftEdgeTapBehavior' : 'rightEdgeTapBehavior';
    const here = dimEdge === edge;
    // The other edge, when the slide-to-dim is on there
    const elsewhere = dimEdge !== null && !here ? dimEdge : null;
    const edgeName = t(ZONE_LABEL_KEYS[edge]);

    return (
      <>
        <SettingGroupHeading>{t('readerSettingsPages.tapThisEdge')}</SettingGroupHeading>
        <ChoiceGroup
          label={t('readerSettingsPages.tapThisEdge')}
          settingId="edgeTap"
          value={settings[tapKey]}
          options={edgeOptions}
          onChange={(value) => updateReaderSetting(tapKey, value as EdgeTapBehavior)}
        />

        <SettingGroupHeading>{t('readerSettingsPages.slideThisEdge')}</SettingGroupHeading>
        <SettingRow
          settingId="dimGestureSide"
          title={t('readerSettingsPages.slideToDim')}
          sub={elsewhere
            ? t('readerSettingsPages.slideToDimOther', { edge: t(ZONE_LABEL_KEYS[elsewhere]) })
            : t('readerSettingsPages.slideToDimSub')}
          control={
            <Switch
              checked={here}
              onChange={(event) => updateReaderSetting('dimGestureSide', event.target.checked ? edge : 'off')}
              slotProps={{ input: { 'aria-label': t('readerSettingsPages.slideToDimAria', { edge: edgeName }) } }}
            />
          }
        />
        {here && (
          <SettingStepper
            title={t('readerSettingsPages.bandWidth')}
            sub={t('readerSettingsPages.bandWidthAbout', { px: bandPx })}
            settingKey="dimGestureWidth"
            value={bandWidth}
            step={5}
            min={5}
            max={bandMax}
            format={(value) => `${value}%`}
            label={t('readerSettingsPages.bandWidth')}
          />
        )}
      </>
    );
  };

  return (
    <Box>
      <SettingGroupHeading>{t('readerSettingsPages.swipes')}</SettingGroupHeading>
      <SettingSelect settingKey="swipeLeftGesture" settingId="swipeLeftGesture" title={t('gestureSettings.swipeLeft')} options={swipeOptions} />
      <SettingSelect settingKey="swipeRightGesture" settingId="swipeRightGesture" title={t('gestureSettings.swipeRight')} options={swipeOptions} />

      {/* Last: the map's height varies with the panel below it */}
      <SettingGroupHeading>{t('readerSettingsPages.screenZones')}</SettingGroupHeading>
      <Typography variant="body2" color="text.secondary" sx={{ pb: 1 }}>
        {t('readerSettingsPages.chooseZone')}
      </Typography>
      <ScreenZoneMap zone={zone} onZoneChange={setZone} items={items} dimEdge={dimEdge} />
      {zone === 'middle' ? renderMiddle() : renderEdge(zone)}

      {mode === 'desktop' && (
        <Typography variant="body2" color="text.secondary" sx={{ pt: 2 }}>
          {t('readerSettingsPages.touchNote')}
        </Typography>
      )}
    </Box>
  );
};

export default GesturesPage;
