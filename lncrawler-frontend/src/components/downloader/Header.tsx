import { IconButton, Box, Typography } from "@mui/material";
import Brightness4Icon from '@mui/icons-material/Brightness4';
import Brightness7Icon from '@mui/icons-material/Brightness7';
import { useTheme } from "@theme/ThemeContext";

// Simple Header component with theme toggle
const Header = () => {
    const { isDarkMode, toggleTheme } = useTheme();
    
    return (
        <Box sx={{ 
            display: 'flex', 
            justifyContent: 'space-between',
            alignItems: 'center', 
            p: 2, 
            bgcolor: 'background.paper',
            borderBottom: 1, 
            borderColor: 'divider' 
        }}>
            <Typography variant="h6" component="div">
                Novel Reader
            </Typography>
            <IconButton onClick={toggleTheme} color="inherit">
                {isDarkMode ? <Brightness7Icon /> : <Brightness4Icon />}
            </IconButton>
        </Box>
    );
};

export default Header;
