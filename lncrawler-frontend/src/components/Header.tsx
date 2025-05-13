import { IconButton, Box, Typography, AppBar, Toolbar, useMediaQuery, Button, Tab, Tabs, Menu, MenuItem } from "@mui/material";
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import SearchIcon from '@mui/icons-material/Search';
import MenuIcon from '@mui/icons-material/Menu';
import HomeIcon from '@mui/icons-material/Home';
import { useTheme as useMuiTheme } from '@mui/material/styles';
import { useTheme } from "@theme/ThemeContext";
import { useNavigate, useLocation } from "react-router-dom";
import { useState } from "react";

// Enhanced Header component with navigation tabs
const Header = () => {
    const { isDarkMode, toggleTheme } = useTheme();
    const navigate = useNavigate();
    const location = useLocation();
    const muiTheme = useMuiTheme();
    const isMobile = useMediaQuery(muiTheme.breakpoints.down('sm'));
    const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
    
    // Determine the current path for active tab highlighting
    const getCurrentPath = () => {
        if (location.pathname.startsWith('/download')) return '/download';
        if (location.pathname.startsWith('/novels')) return '/novels';
        return location.pathname;
    };
    
    const handleNavigate = (path: string) => {
        navigate(path);
        setMenuAnchor(null);
    };
    
    const handleMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
        setMenuAnchor(event.currentTarget);
    };
    
    const handleMenuClose = () => {
        setMenuAnchor(null);
    };

    return (
        <AppBar position="sticky" color="default" elevation={1}>
            <Toolbar sx={{ justifyContent: 'space-between' }}>
                {/* Logo/Home section */}
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <IconButton color="inherit" onClick={() => navigate('/')} sx={{ mr: 1 }}>
                        <HomeIcon />
                    </IconButton>
                    <Typography 
                        variant="h6" 
                        component="div" 
                        sx={{ 
                            fontWeight: 'bold',
                            cursor: 'pointer'
                        }}
                        onClick={() => navigate('/')}
                    >
                        Novel Reader
                    </Typography>
                </Box>
                
                {/* Navigation Links - Desktop */}
                {!isMobile && (
                    <Tabs 
                        value={getCurrentPath()} 
                        indicatorColor="primary"
                        textColor="primary"
                        sx={{ flexGrow: 1, ml: 4 }}
                    >
                        <Tab label="Home" value="/" onClick={() => navigate('/')} />
                        <Tab label="Download" value="/download" onClick={() => navigate('/download')} />
                    </Tabs>
                )}
                
                {/* Actions section */}
                <Box sx={{ display: 'flex', alignItems: 'center' }}>
                    <IconButton onClick={() => navigate('/novels/search')} color="inherit">
                        <SearchIcon />
                    </IconButton>
                    <IconButton onClick={toggleTheme} color="inherit">
                        {isDarkMode ? <Brightness7Icon /> : <Brightness4Icon />}
                    </IconButton>
                    
                    {/* Mobile Menu Button */}
                    {isMobile && (
                        <>
                            <IconButton 
                                edge="end" 
                                color="inherit" 
                                aria-label="menu"
                                onClick={handleMenuOpen}
                            >
                                <MenuIcon />
                            </IconButton>
                            <Menu
                                anchorEl={menuAnchor}
                                open={Boolean(menuAnchor)}
                                onClose={handleMenuClose}
                            >
                                <MenuItem onClick={() => handleNavigate('/')}>Home</MenuItem>
                                <MenuItem onClick={() => handleNavigate('/download')}>Download</MenuItem>
                            </Menu>
                        </>
                    )}
                </Box>
            </Toolbar>
        </AppBar>
    );
};

export default Header;
