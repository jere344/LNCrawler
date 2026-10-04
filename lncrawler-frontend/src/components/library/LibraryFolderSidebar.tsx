import React, { useState } from 'react';
import {
  Box,
  List,
  ListItemButton,
  ListItemText,
  ListItemIcon,
  IconButton,
  Menu,
  MenuItem,
  Tooltip,
  Typography,
} from '@mui/material';
import FolderIcon from '@mui/icons-material/Folder';
import FolderOpenIcon from '@mui/icons-material/FolderOpen';
import CreateNewFolderIcon from '@mui/icons-material/CreateNewFolder';
import MoreVertIcon from '@mui/icons-material/MoreVert';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import FolderOffIcon from '@mui/icons-material/FolderOff';
import { LibraryFolder } from '@models/novels_types';
import { useTranslation } from 'react-i18next';

interface LibraryFolderSidebarProps {
  folders: LibraryFolder[];
  totalCount: number;
  selected: string;
  onSelect: (folder: string) => void;
  editable?: boolean;
  onCreate?: () => void;
  onRename?: (folder: LibraryFolder) => void;
  onDelete?: (folder: LibraryFolder) => void;
}

const LibraryFolderSidebar: React.FC<LibraryFolderSidebarProps> = ({
  folders,
  totalCount,
  selected,
  onSelect,
  editable = false,
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

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', px: 1, mb: 1 }}>
        <Typography variant="subtitle2" color="text.secondary">
          {t('library.folders')}
        </Typography>
        {editable && onCreate && (
          <Tooltip title={t('library.newFolder')}>
            <IconButton size="small" onClick={onCreate}>
              <CreateNewFolderIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      <List dense disablePadding>
        <ListItemButton selected={selected === 'all'} onClick={() => onSelect('all')}>
          <ListItemIcon sx={{ minWidth: 32 }}>
            <LibraryBooksIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t('library.allItems')} />
          <Typography variant="caption" color="text.secondary">{totalCount}</Typography>
        </ListItemButton>

        <ListItemButton selected={selected === 'unfiled'} onClick={() => onSelect('unfiled')}>
          <ListItemIcon sx={{ minWidth: 32 }}>
            <FolderOffIcon fontSize="small" />
          </ListItemIcon>
          <ListItemText primary={t('library.unfiled')} />
        </ListItemButton>

        {folders.map((folder) => (
          <ListItemButton
            key={folder.id}
            selected={selected === folder.id}
            onClick={() => onSelect(folder.id)}
          >
            <ListItemIcon sx={{ minWidth: 32 }}>
              {selected === folder.id ? <FolderOpenIcon fontSize="small" /> : <FolderIcon fontSize="small" />}
            </ListItemIcon>
            <ListItemText primary={folder.name} />
            <Typography variant="caption" color="text.secondary" sx={{ mr: editable ? 0.5 : 0 }}>
              {folder.count}
            </Typography>
            {editable && (onRename || onDelete) && (
              <IconButton
                size="small"
                onClick={(event) => {
                  event.stopPropagation();
                  setMenuAnchor(event.currentTarget);
                  setMenuFolder(folder);
                }}
              >
                <MoreVertIcon fontSize="small" />
              </IconButton>
            )}
          </ListItemButton>
        ))}
      </List>

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

export default LibraryFolderSidebar;
