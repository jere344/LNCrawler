import React from 'react';
import { Breadcrumbs, Link, Typography, Box } from '@mui/material';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import HomeIcon from '@mui/icons-material/Home';
import { Link as RouterLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

export interface BreadcrumbItem {
  label: string;
  link?: string;
  // Runs on click before the link navigates; the link keeps its href, so middle-click still opens it
  onClick?: (event: React.MouseEvent<HTMLAnchorElement>) => void;
  icon?: React.ReactNode;
}

// One line whatever the labels, so a long title cannot change the row's height and shift the page
const ELLIPSIS_SX = { overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', minWidth: 0 } as const;
// The last item takes the room the others leave
const MIDDLE_MAX_WIDTH = { xs: '8rem', sm: '14rem' };

interface BreadcrumbNavProps {
  items: BreadcrumbItem[];
}

const BreadcrumbNav: React.FC<BreadcrumbNavProps> = ({ items }) => {
  const { t } = useTranslation();
  return (
    <Box sx={{ mb: 3, mt: 1 }}>
      <Breadcrumbs 
        separator={<NavigateNextIcon fontSize="small" />} 
        aria-label={t('common.breadcrumb')}
        sx={{
          '& .MuiBreadcrumbs-ol': { flexWrap: 'nowrap' },
          '& .MuiBreadcrumbs-li': { minWidth: 0 },
          '& .MuiBreadcrumbs-separator': { flexShrink: 0 },
        }}
      >
        <Link 
          component={RouterLink}
          to="/"
          color="inherit" 
          underline="hover"
          sx={{ display: 'flex', alignItems: 'center', whiteSpace: 'nowrap' }}
        >
          <HomeIcon sx={{ mr: 0.5 }} fontSize="inherit" />
          {t('common.home')}
        </Link>
        
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          
          if (isLast || !item.link) {
            return (
              <Typography
                component="span"
                key={item.label}
                sx={{ 
                  display: 'flex', 
                  alignItems: 'center',
                  color: 'text.primary',
                  minWidth: 0,
                  maxWidth: isLast ? undefined : MIDDLE_MAX_WIDTH,
                }}
              >
                {item.icon && <Box sx={{ mr: 0.5, display: 'flex', alignItems: 'center', flexShrink: 0 }}>{item.icon}</Box>}
                <Box component="span" title={item.label} sx={ELLIPSIS_SX}>{item.label}</Box>
              </Typography>
            );
          }
          
          return (
            <Link
              key={item.label}
              component={RouterLink}
              to={item.link}
              onClick={item.onClick}
              color="inherit"
              underline="hover"
              sx={{ display: 'flex', alignItems: 'center', minWidth: 0, maxWidth: MIDDLE_MAX_WIDTH }}
            >
              {item.icon && <Box sx={{ mr: 0.5, display: 'flex', alignItems: 'center', flexShrink: 0 }}>{item.icon}</Box>}
              <Box component="span" title={item.label} sx={ELLIPSIS_SX}>{item.label}</Box>
            </Link>
          );
        })}
      </Breadcrumbs>
    </Box>
  );
};

export default BreadcrumbNav;
