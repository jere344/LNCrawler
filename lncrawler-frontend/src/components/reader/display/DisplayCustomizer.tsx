import { Box, Button, Divider, IconButton, Typography } from '@mui/material';
import { DndContext, KeyboardSensor, PointerSensor, closestCenter, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, arrayMove, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { useTranslation } from 'react-i18next';
import AddIcon from '@mui/icons-material/Add';
import DragIndicatorIcon from '@mui/icons-material/DragIndicator';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutlined';
import { useReaderSettings } from '../hooks/useReaderSettings';
import { useViewportSize } from '../hooks/useViewportSize';
import { updateReaderSetting } from '../readerSettingsStore';
import { DISPLAY_MODULES, type DisplayModule } from '../readerSettingsSchema';
import { defaultSettings } from '../readerDefaults';
import { useSettingsContext } from '../settings/settingsContext';
import { fitsInSheet } from './displayLayout';
import { DISPLAY_MODULE_DEFS } from './displayModules';
import { TOUCH_TARGET } from '../touchTarget';
import SheetPreview from './SheetPreview';

interface SortableModuleRowProps {
  module: DisplayModule;
  canRemove: boolean;
  touch: boolean;
  onRemove: (module: DisplayModule) => void;
}

// One control in the sheet: a drag handle, its name, and a remove button
const SortableModuleRow = ({ module, canRemove, touch, onRemove }: SortableModuleRowProps) => {
  const touchTarget = touch ? TOUCH_TARGET : undefined;
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: module });
  const label = t(DISPLAY_MODULE_DEFS[module].labelKey);

  return (
    <Box
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition, opacity: isDragging ? 0.5 : 1 }}
      sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5 }}
    >
      <IconButton
        aria-label={t('readerDisplay.customizer.move', { label })}
        {...attributes}
        {...listeners}
        sx={{ cursor: 'grab', touchAction: 'none', ...touchTarget }}
      >
        <DragIndicatorIcon />
      </IconButton>
      <Typography sx={{ flex: 1, minWidth: 0 }}>{label}</Typography>
      <IconButton
        aria-label={t('readerDisplay.customizer.remove', { label })}
        disabled={!canRemove}
        onClick={() => onRemove(module)}
        sx={touchTarget}
      >
        <RemoveCircleOutlineIcon />
      </IconButton>
    </Box>
  );
};

// Edits the display sheet: a live preview, the controls in the sheet (reorder, remove), and the controls that can be added
const DisplayCustomizer = () => {
  const { t } = useTranslation();
  const { mode } = useSettingsContext();
  const modules = useReaderSettings().displaySheetModules;
  const { height: viewportHeight } = useViewportSize();
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  const available = DISPLAY_MODULES.filter((module) => !modules.includes(module));
  const canAdd = (module: DisplayModule) => fitsInSheet([...modules, module], viewportHeight, mode);
  const noRoom = available.every((module) => !canAdd(module));
  const touchLayout = mode === 'phone' || mode === 'tablet' || mode === 'phoneLandscape';
  const touchTarget = touchLayout ? TOUCH_TARGET : undefined;

  const handleDragEnd = ({ active, over }: DragEndEvent) => {
    if (!over || active.id === over.id) return;
    const from = modules.indexOf(active.id as DisplayModule);
    const to = modules.indexOf(over.id as DisplayModule);
    updateReaderSetting('displaySheetModules', arrayMove(modules, from, to));
  };

  const removeModule = (module: DisplayModule) => {
    updateReaderSetting('displaySheetModules', modules.filter((item) => item !== module));
  };

  const addModule = (module: DisplayModule) => {
    updateReaderSetting('displaySheetModules', [...modules, module]);
  };

  return (
    <Box data-setting-id="displaySheet">
      <SheetPreview mode={mode} />

      <Typography variant="subtitle2" component="h3" gutterBottom>{t('readerDisplay.customizer.inSheet')}</Typography>
      <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
        <SortableContext items={modules} strategy={verticalListSortingStrategy}>
          {modules.map((module) => (
            <SortableModuleRow key={module} module={module} canRemove={modules.length > 1} touch={touchLayout} onRemove={removeModule} />
          ))}
        </SortableContext>
      </DndContext>

      <Divider sx={{ my: 2 }} />

      <Typography variant="subtitle2" component="h3" gutterBottom>{t('readerDisplay.customizer.addControl')}</Typography>
      {noRoom && (
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>{t('readerDisplay.customizer.noRoom')}</Typography>
      )}
      {available.map((module) => {
        const label = t(DISPLAY_MODULE_DEFS[module].labelKey);
        return (
          <Box key={module} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.5 }}>
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography>{label}</Typography>
              <Typography variant="caption" color="text.secondary">{t(DISPLAY_MODULE_DEFS[module].descKey)}</Typography>
            </Box>
            <IconButton
              aria-label={t('readerDisplay.customizer.add', { label })}
              disabled={!canAdd(module)}
              onClick={() => addModule(module)}
              sx={touchTarget}
            >
              <AddIcon />
            </IconButton>
          </Box>
        );
      })}

      <Divider sx={{ my: 2 }} />

      <Button
        variant="outlined"
        fullWidth
        onClick={() => updateReaderSetting('displaySheetModules', [...defaultSettings.displaySheetModules])}
      >
        {t('readerDisplay.customizer.restore')}
      </Button>
    </Box>
  );
};

export default DisplayCustomizer;
