import React from 'react';
import { Breadcrumbs, Link, Typography, Box } from '@mui/material';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import HomeIcon from '@mui/icons-material/Home';
import { Link as RouterLink } from 'react-router-dom';

export interface BreadcrumbItem {
  label: string;
  link?: string;
  icon?: React.ReactNode;
}

interface BreadcrumbNavProps {
  items: BreadcrumbItem[];
}

const BreadcrumbNav: React.FC<BreadcrumbNavProps> = ({ items }) => {
  return (
    <Box sx={{ mb: 3, mt: 1 }}>
      <Breadcrumbs 
        separator={<NavigateNextIcon fontSize="small" />} 
        aria-label="breadcrumb"
      >
        <Link 
          component={RouterLink}
          to="/"
          color="inherit" 
          underline="hover"
          sx={{ display: 'flex', alignItems: 'center' }}
        >
          <HomeIcon sx={{ mr: 0.5 }} fontSize="inherit" />
          Home
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
                  color: 'text.primary'
                }}
              >
                {item.icon && <Box sx={{ mr: 0.5, display: 'flex', alignItems: 'center' }}>{item.icon}</Box>}
                {item.label}
              </Typography>
            );
          }
          
          return (
            <Link
              key={item.label}
              component={RouterLink}
              to={item.link}
              color="inherit"
              underline="hover"
              sx={{ display: 'flex', alignItems: 'center' }}
            >
              {item.icon && <Box sx={{ mr: 0.5, display: 'flex', alignItems: 'center' }}>{item.icon}</Box>}
              {item.label}
            </Link>
          );
        })}
      </Breadcrumbs>
    </Box>
  );
};

export default BreadcrumbNav;
