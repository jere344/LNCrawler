import { Box } from '@mui/material';
import type { DisplayModule } from '../readerSettingsSchema';
import { DISPLAY_MODULE_DEFS } from './displayModules';
import { MODULE_LAYOUT, pairRows } from './displayLayout';

interface DisplayModuleGridProps {
  modules: DisplayModule[];
}

// Two columns: half modules sit side by side, full modules span the line
const DisplayModuleGrid = ({ modules }: DisplayModuleGridProps) => (
  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }}>
    {pairRows(modules).map((row) =>
      row.map((module) => {
        const { Component } = DISPLAY_MODULE_DEFS[module];
        return (
          <Box
            key={module}
            sx={{
              gridColumn: row.length === 1 ? '1 / -1' : undefined,
              minHeight: MODULE_LAYOUT[module].height,
              minWidth: 0,
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'center',
            }}
          >
            <Component />
          </Box>
        );
      })
    )}
  </Box>
);

export default DisplayModuleGrid;
