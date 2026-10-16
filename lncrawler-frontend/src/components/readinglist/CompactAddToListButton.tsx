import React, { useState } from 'react';
import { Box, IconButton } from '@mui/material';
import type { SxProps } from '@mui/material';
import PlaylistAddIcon from '@mui/icons-material/PlaylistAdd';
import { useAuth } from '@context/AuthContext';
import { useNavigate } from 'react-router-dom';
import AddToListDialog from './AddToListDialog';

interface CompactAddToListButtonProps {
  novelId: string;
  novelTitle: string;
  customSx?: SxProps;
}

const CompactAddToListButton: React.FC<CompactAddToListButtonProps> = ({
  novelId,
  novelTitle,
  customSx = {}
}) => {
  const [open, setOpen] = useState(false);
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();

  const handleOpen = (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();

    if (!isAuthenticated) {
      navigate('/login?redirect=' + encodeURIComponent(window.location.pathname));
      return;
    }

    setOpen(true);
  };

  if (!isAuthenticated) return null;

  return (
    <>
      <Box sx={customSx}>
        <IconButton
          size="small"
          onClick={handleOpen}
          sx={{
            bgcolor: 'rgba(0, 0, 0, 0.6)',
            color: 'white',
            '&:hover': {
              bgcolor: 'rgba(0, 0, 0, 0.8)',
            },
            width: 36,
            height: 36,
          }}
        >
          <PlaylistAddIcon />
        </IconButton>
      </Box>

      <AddToListDialog
        open={open}
        onClose={() => setOpen(false)}
        novelId={novelId}
        novelTitle={novelTitle}
      />
    </>
  );
};

export default CompactAddToListButton;
