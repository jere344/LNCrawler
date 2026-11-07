import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import SimulatedPreview from '../SimulatedPreview';
import { SettingStepper, SettingSwitch, PageFootReset } from '../SettingRows';
import { AlignModule, FontModule } from '../../display/moduleControls';
import { STEPPER_SPECS } from '../../display/stepperSpecs';

// Font, size, alignment and spacing of the chapter text, with a preview on top
const TextPage = () => {
  const { t } = useTranslation();

  return (
    <Box>
      <SimulatedPreview />

      <Box sx={{ pt: 2 }} data-setting-id="fontFamily">
        <Typography sx={{ fontWeight: 600, pb: 1 }}>{t('fontSettings.font')}</Typography>
        <FontModule />
      </Box>

      <SettingStepper
        title={t('readerDisplay.modules.size.label')}
        settingKey="fontSize"
        settingId="fontSize"
        {...STEPPER_SPECS.fontSize}
      />

      <Box sx={{ pt: 2 }} data-setting-id="textAlign">
        <Typography sx={{ fontWeight: 600, pb: 1 }}>{t('readerDisplay.modules.align.label')}</Typography>
        <AlignModule />
      </Box>

      <SettingStepper
        title={t('readerDisplay.modules.line.label')}
        settingKey="lineSpacing"
        settingId="lineSpacing"
        {...STEPPER_SPECS.lineSpacing}
      />
      <SettingStepper
        title={t('readerSettingsPages.betweenParagraphs')}
        settingKey="paragraphSpacing"
        settingId="paragraphSpacing"
        {...STEPPER_SPECS.paragraphSpacing}
      />
      <SettingStepper
        title={t('readerSettingsPages.sideMargins')}
        settingKey="margin"
        settingId="margin"
        {...STEPPER_SPECS.margin}
      />
      <SettingStepper
        title={t('readerSettingsPages.betweenWords')}
        settingKey="wordSpacing"
        settingId="wordSpacing"
        {...STEPPER_SPECS.wordSpacing}
      />
      <SettingStepper
        title={t('readerSettingsPages.betweenLetters')}
        settingKey="letterSpacing"
        settingId="letterSpacing"
        {...STEPPER_SPECS.letterSpacing}
      />
      <SettingSwitch settingKey="paragraphIndent" settingId="paragraphIndent" title={t('readerSettingsPages.indentFirstLine')} />

      <PageFootReset
        keys={['fontSize', 'fontFamily', 'textAlign', 'lineSpacing', 'paragraphSpacing', 'margin', 'wordSpacing', 'letterSpacing', 'paragraphIndent']}
      />
    </Box>
  );
};

export default TextPage;
