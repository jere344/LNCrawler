import React, { useState } from 'react';
import { Box, Chip, IconButton, Menu, MenuItem, Tooltip } from '@mui/material';
import { useDroppable } from '@dnd-kit/core';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import { LibraryFolder } from '@models/novels_types';
import { useTranslation } from 'react-i18next';

interface LibraryFolderBarProps {
  folders: LibraryFolder[];
  totalCount: number;
  selected: string;
  onSelect: (folder: string) => void;
  editable?: boolean;
  dragActive?: boolean;
  onCreate?: () => void;
  onRename?: (folder: LibraryFolder) => void;
  onDelete?: (folder: LibraryFolder) => void;
}

const countSx = {
  ml: 0.25,
  px: 0.75,
  borderRadius: 5,
  bgcolor: 'action.selected',
  fontSize: '0.72rem',
  lineHeight: 1.6,
} as const;

interface BarChipProps {
  dropId: string;
  droppable?: boolean;
  active?: boolean;
  icon: React.ReactNode;
  label: React.ReactNode;
  count?: number;
  selected: boolean;
  onClick: () => void;
}

const BarChip: React.FC<BarChipProps> = ({
  dropId,
  droppable = false,
  active = false,
  icon,
  label,
  count,
  selected,
  onClick,
}) => {
  const { setNodeRef, isOver } = useDroppable({ id: dropId, disabled: !droppable });
  const highlight = isOver && active;

  return (
    <Chip
      ref={setNodeRef}
      icon={icon as React.ReactElement}
      onClick={onClick}
      variant={selected ? 'filled' : 'outlined'}
      color={selected ? 'primary' : 'default'}
      label={
        <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center' }}>
          {label}
          {count !== undefined && <Box component="span" sx={countSx}>{count}</Box>}
        </Box>
      }
      sx={{
        flexShrink: 0,
        transition: 'all 0.15s ease',
        ...(droppable && active && {
          outline: '2px dashed',
          outlineColor: 'primary.main',
          outlineOffset: 1,
        }),
        ...(highlight && {
          outlineStyle: 'solid',
          bgcolor: 'primary.main',
          color: 'primary.contrastText',
          transform: 'scale(1.05)',
        }),
      }}
    />
  );
};

const LibraryFolderBar: React.FC<LibraryFolderBarProps> = ({
  folders,
  totalCount,
  selected,
  onSelect,
  editable = false,
  dragActive = false,
  onCreate,
  onRename,
  onDelete,
}) => {
  const { t } = useTranslation();
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [menuFolder, setMenuFolder] = useState<LibraryFolder | null>(null);

  const closeMenu = () => {
    setMenuAnchor(null);
    setMenuFolder(null);
  };

  const unfiledCount = Math.max(0, totalCount - folders.reduce((sum, f) => sum + f.count, 0));

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 1,
        overflowX: 'auto',
        py: 1,
        px: 0.25,
        scrollbarWidth: 'thin',
      }}
    >
      <BarChip
        dropId="folder:all"
        icon={<LibraryBooksIcon fontSize="small" />}
        label={t('library.allItems')}
        count={totalCount}
        selected={selected === 'all'}
        onClick={() => onSelect('all')}
      />

      <BarChip
        dropId="folder:unfiled"
        droppable
        active={dragActive}
        icon={<FolderOffIcon fontSize="small" />}
        label={t('library.unfiled')}
        count={unfiledCount}
        selected={selected === 'unfiled'}
        onClick={() => onSelect('unfiled')}
      />

      {folders.map((folder) => (
        <BarChip
          key={folder.id}
          dropId={`folder:${folder.id}`}
          droppable
          active={dragActive}
          icon={
            selected === folder.id ? (
              <FolderOpenIcon fontSize="small" />
            ) : (
              <FolderIcon fontSize="small" />
            )
          }
          label={
            <Box component="span" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.25 }}>
              {folder.name}
              {editable && (onRename || onDelete) && (
                <Tooltip title={t('library.folders')}>
                  <IconButton
                    size="small"
                    component="span"
                    sx={{ ml: 0.25, p: 0.25, opacity: 0.6 }}
                    onClick={(event) => {
                      event.stopPropagation();
                      setMenuAnchor(event.currentTarget);
                      setMenuFolder(folder);
                    }}
                  >
                    <MoreVertIcon sx={{ fontSize: 16 }} />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          }
          count={folder.count}
          selected={selected === folder.id}
          onClick={() => onSelect(folder.id)}
        />
      ))}

      {editable && onCreate && (
        <Chip
          icon={<CreateNewFolderIcon fontSize="small" />}
          label={t('library.newFolder')}
          variant="outlined"
          onClick={onCreate}
          sx={{ flexShrink: 0, borderStyle: 'dashed' }}
        />
      )}

      <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={closeMenu}>
        <MenuItem
          onClick={() => {
            if (menuFolder) onRename?.(menuFolder);
            closeMenu();
          }}
        >
          {t('common.edit')}
        </MenuItem>
        <MenuItem
          onClick={() => {
            if (menuFolder) onDelete?.(menuFolder);
            closeMenu();
          }}
        >
          {t('common.delete')}
        </MenuItem>
      </Menu>
    </Box>
  );
};

export default LibraryFolderBar;
