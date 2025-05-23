import React from 'react';
import { Button, Typography, Box, Tooltip, SxProps, Theme } from '@mui/material';

interface ActionButtonProps {
  /**
   * The title text displayed on the button
   */
  title: string;
  
  /**
   * Optional subtitle text displayed below the title
   */
  subtitle?: string;
  
  /**
   * The icon to display at the start of the button
   */
  startIcon: React.ReactNode;
  
  /**
   * The icon to display in the background (will be rotated)
   * If not provided, startIcon will be used
   */
  backgroundIcon?: React.ReactNode;
  
  /**
   * Button color variant
   */
  color?: "inherit" | "primary" | "secondary" | "success" | "error" | "info" | "warning";
  
  /**
   * Function to call when the button is clicked
   */
  onClick?: () => void;
  
  /**
   * Whether the button is disabled
   */
  disabled?: boolean;
  
  /**
   * Tooltip text to display on hover
   */
  tooltip?: string;
  
  /**
   * Tooltip placement
   */
  tooltipPlacement?: "top" | "bottom" | "left" | "right";
  
  /**
   * Optional additional styling
   */
  sx?: SxProps<Theme>;
  
  /**
   * Full width button
   */
  fullWidth?: boolean;
}

/**
 * A styled action button with a title, subtitle, and icon.
 * The icon is displayed both as a start icon and as a larger rotated background icon.
 */
const ActionButton: React.FC<ActionButtonProps> = ({
  title,
  subtitle,
  startIcon,
  backgroundIcon,
  color = "primary",
  onClick,
  disabled = false,
  tooltip,
  tooltipPlacement = "top",
  sx = {},
  fullWidth = true,
}) => {
  const button = (
    <Button
      variant="contained"
      color={color}
      size="large"
      fullWidth={fullWidth}
      startIcon={startIcon}
      onClick={onClick}
      disabled={disabled}
      sx={{
        borderRadius: '12px',
        p: 1.5,
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
        display: 'flex',
        justifyContent: 'flex-start',
        alignItems: 'center',
        textAlign: 'left',
        position: 'relative',
        overflow: 'hidden',
        ...sx
      }}
    >
      <Box sx={{ zIndex: 1 }}>
        <Typography variant="button" sx={{ display: 'block', fontWeight: 700 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" sx={{ opacity: 0.8 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {React.cloneElement((backgroundIcon || startIcon) as React.ReactElement, { 
        sx: { 
          position: 'absolute', 
          right: '5px', 
          fontSize: '3rem', 
          opacity: 0.2,
          transform: 'rotate(15deg)'
        }
      })}
    </Button>
  );

  if (tooltip) {
    return (
      <Tooltip title={tooltip} arrow placement={tooltipPlacement}>
        {button}
      </Tooltip>
    );
  }

  return button;
};

export default ActionButton;
