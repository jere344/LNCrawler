import { Box, Typography } from '@mui/material';
import { useTranslation } from 'react-i18next';
import SimulatedPreview from '../SimulatedPreview';
import { SettingStepper, SettingSwitch, PageFootReset } from '../SettingRows';
import { AlignModule, FontModule } from '../../display/moduleControls';
import { STEPPER_SPECS } from '../../display/stepperSpecs';

// Font, size, alignment and spacing of the chapter text, with a preview on top
const TextPage = () => {
  const { t } = useTranslation();

  const sizeTitle = t('readerDisplay.modules.size.label');
  const lineTitle = t('readerDisplay.modules.line.label');
  const paragraphTitle = t('readerSettingsPages.betweenParagraphs');
  const marginTitle = t('readerSettingsPages.sideMargins');
  const wordTitle = t('readerSettingsPages.betweenWords');
  const letterTitle = t('readerSettingsPages.betweenLetters');

  return (
    <Box>
      <SimulatedPreview />

      <Box sx={{ pt: 2 }} data-setting-id="fontFamily">
        <Typography sx={{ fontWeight: 600, pb: 1 }}>{t('fontSettings.font')}</Typography>
        <FontModule />
      </Box>

      <SettingStepper
        title={sizeTitle}
        settingKey="fontSize"
        settingId="fontSize"
        {...STEPPER_SPECS.fontSize}
        label={sizeTitle}
      />

      <Box sx={{ pt: 2 }} data-setting-id="textAlign">
        <Typography sx={{ fontWeight: 600, pb: 1 }}>{t('readerDisplay.modules.align.label')}</Typography>
        <AlignModule />
      </Box>

      <SettingStepper
        title={lineTitle}
        settingKey="lineSpacing"
        settingId="lineSpacing"
        {...STEPPER_SPECS.lineSpacing}
        label={lineTitle}
      />
      <SettingStepper
        title={paragraphTitle}
        settingKey="paragraphSpacing"
        settingId="paragraphSpacing"
        {...STEPPER_SPECS.paragraphSpacing}
        label={paragraphTitle}
      />
      <SettingStepper
        title={marginTitle}
        settingKey="margin"
        settingId="margin"
        {...STEPPER_SPECS.margin}
        label={marginTitle}
      />
      <SettingStepper
        title={wordTitle}
        settingKey="wordSpacing"
        settingId="wordSpacing"
        {...STEPPER_SPECS.wordSpacing}
        label={wordTitle}
      />
      <SettingStepper
        title={letterTitle}
        settingKey="letterSpacing"
        settingId="letterSpacing"
        {...STEPPER_SPECS.letterSpacing}
        label={letterTitle}
      />
      <SettingSwitch settingKey="paragraphIndent" settingId="paragraphIndent" title={t('readerSettingsPages.indentFirstLine')} />

      <PageFootReset
        keys={['fontSize', 'fontFamily', 'textAlign', 'lineSpacing', 'paragraphSpacing', 'margin', 'wordSpacing', 'letterSpacing', 'paragraphIndent']}
      />
    </Box>
  );
};

export default TextPage;
