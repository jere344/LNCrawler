import type { ComponentType } from 'react';
import type { DisplayModule } from '../readerSettingsSchema';
import {
  AlignModule,
  DimModule,
  FontModule,
  IndentModule,
  LineModule,
  MarginModule,
  ParagraphModule,
  SizeModule,
  ThemeModule,
  WarmModule,
} from './moduleControls';

interface DisplayModuleDef {
  labelKey: string;
  descKey: string;
  Component: ComponentType;
}

// Each module in the display sheet: its name, what it does, and the control it renders
export const DISPLAY_MODULE_DEFS: Record<DisplayModule, DisplayModuleDef> = {
  size: { labelKey: 'readerDisplay.modules.size.label', descKey: 'readerDisplay.modules.size.desc', Component: SizeModule },
  line: { labelKey: 'readerDisplay.modules.line.label', descKey: 'readerDisplay.modules.line.desc', Component: LineModule },
  para: { labelKey: 'readerDisplay.modules.para.label', descKey: 'readerDisplay.modules.para.desc', Component: ParagraphModule },
  margin: { labelKey: 'readerDisplay.modules.margin.label', descKey: 'readerDisplay.modules.margin.desc', Component: MarginModule },
  indent: { labelKey: 'readerDisplay.modules.indent.label', descKey: 'readerDisplay.modules.indent.desc', Component: IndentModule },
  align: { labelKey: 'readerDisplay.modules.align.label', descKey: 'readerDisplay.modules.align.desc', Component: AlignModule },
  theme: { labelKey: 'readerDisplay.modules.theme.label', descKey: 'readerDisplay.modules.theme.desc', Component: ThemeModule },
  font: { labelKey: 'readerDisplay.modules.font.label', descKey: 'readerDisplay.modules.font.desc', Component: FontModule },
  dim: { labelKey: 'readerDisplay.modules.dim.label', descKey: 'readerDisplay.modules.dim.desc', Component: DimModule },
  warm: { labelKey: 'readerDisplay.modules.warm.label', descKey: 'readerDisplay.modules.warm.desc', Component: WarmModule },
};
