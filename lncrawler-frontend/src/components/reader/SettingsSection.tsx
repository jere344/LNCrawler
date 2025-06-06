import { Accordion, AccordionSummary, AccordionDetails, Box, Typography, useTheme } from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { ReactNode } from 'react';

interface SettingsSectionProps {
  title: string;
  icon: ReactNode;
  children: ReactNode;
  defaultExpanded?: boolean;
}

const SettingsSection = ({ title, icon, children, defaultExpanded = false }: SettingsSectionProps) => {
  const theme = useTheme();
  return (
    <Accordion defaultExpanded={defaultExpanded} 
        sx={{ 
            backgroundColor: theme.palette.background.paper,
        }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {icon}
          <Typography variant="subtitle1" fontWeight="medium">{title}</Typography>
        </Box>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        {children}
      </AccordionDetails>
    </Accordion>
  );
};

export default SettingsSection;
