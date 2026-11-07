import type { ComponentType } from 'react';
import type { DisplayModule } from '../readerSettingsSchema';
import { STEPPER_SPECS } from './stepperSpecs';
import { AlignModule, DimModule, FontModule, IndentModule, ThemeModule, WarmModule } from './moduleControls';
import { SIZE_BUTTONS, stepperModule } from './stepperModule';

interface DisplayModuleDef {
  labelKey: string;
  descKey: string;
  Component: ComponentType;
}

// A stepped number setting as a display module: its name, what it does, and the stepper that sets it
const steppedModule = (
  labelKey: string,
  descKey: string,
  specKey: keyof typeof STEPPER_SPECS,
  buttons?: Parameters<typeof stepperModule>[2],
): DisplayModuleDef => ({ labelKey, descKey, Component: stepperModule(specKey, labelKey, buttons) });

// Each module in the display sheet: its name, what it does, and the control it renders
export const DISPLAY_MODULE_DEFS: Record<DisplayModule, DisplayModuleDef> = {
  size: steppedModule('readerDisplay.modules.size.label', 'readerDisplay.modules.size.desc', 'fontSize', SIZE_BUTTONS),
  line: steppedModule('readerDisplay.modules.line.label', 'readerDisplay.modules.line.desc', 'lineSpacing'),
  para: steppedModule('readerDisplay.modules.para.label', 'readerDisplay.modules.para.desc', 'paragraphSpacing'),
  margin: steppedModule('readerDisplay.modules.margin.label', 'readerDisplay.modules.margin.desc', 'margin'),
  indent: { labelKey: 'readerDisplay.modules.indent.label', descKey: 'readerDisplay.modules.indent.desc', Component: IndentModule },
  align: { labelKey: 'readerDisplay.modules.align.label', descKey: 'readerDisplay.modules.align.desc', Component: AlignModule },
  theme: { labelKey: 'readerDisplay.modules.theme.label', descKey: 'readerDisplay.modules.theme.desc', Component: ThemeModule },
  font: { labelKey: 'readerDisplay.modules.font.label', descKey: 'readerDisplay.modules.font.desc', Component: FontModule },
  dim: { labelKey: 'readerDisplay.modules.dim.label', descKey: 'readerDisplay.modules.dim.desc', Component: DimModule },
  warm: { labelKey: 'readerDisplay.modules.warm.label', descKey: 'readerDisplay.modules.warm.desc', Component: WarmModule },
};
