import {
    IconButton,
    Box,
    Typography,
    AppBar,
    Toolbar,
    useMediaQuery,
    Tab,
    Tabs,
    Menu,
    MenuItem,
    Link,
    ListItemIcon,
    ListItemText,
    Button,
    Avatar,
} from "@mui/material";
import PaletteIcon from "@mui/icons-material/Palette";
import SearchIcon from "@mui/icons-material/Search";
import MenuIcon from "@mui/icons-material/Menu";
import GitHubIcon from "@mui/icons-material/GitHub";
import CheckIcon from "@mui/icons-material/Check";
import LoginIcon from "@mui/icons-material/Login";
import LogoutIcon from "@mui/icons-material/Logout";
import PersonIcon from "@mui/icons-material/Person";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import HistoryIcon from "@mui/icons-material/History";
import ForumIcon from "@mui/icons-material/Forum"; // Import Forum icon for Chat
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted'; // Import icon for reading lists
import { useTheme as useMuiTheme } from "@mui/material/styles";
import { useTheme } from "@theme/ThemeContext";
import { useNavigate, useLocation, Link as RouterLink } from "react-router-dom";
import { useState, useEffect, useCallback } from "react";
import { useAuth } from "../context/AuthContext";

// Import logos
import logoLight from "@assets/logo-transparent.png";
import logoDark from "@assets/logo-transparent-dark.png";

// Custom hook to track scroll direction
const useScrollDirection = () => {
    const [scrollDirection, setScrollDirection] = useState("up");
    const [prevOffset, setPrevOffset] = useState(0);

    const toggleScrollDirection = useCallback(() => {
        const scrollY = window.scrollY;
        if (scrollY === 0) {
            setScrollDirection("up");
        } else if (scrollY > prevOffset) {
            setScrollDirection("down");
        } else if (scrollY < prevOffset) {
            setScrollDirection("up");
        }
        setPrevOffset(scrollY);
    }, [prevOffset]);

    useEffect(() => {
        window.addEventListener("scroll", toggleScrollDirection);
        return () => window.removeEventListener("scroll", toggleScrollDirection);
    }, [toggleScrollDirection]);

    return scrollDirection;
};

// Discord icon component (Material UI doesn't have a built-in Discord icon)
const DiscordIcon = () => (
    <svg width="24" height="24" viewBox="0 0 71 55" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
        <path d="M60.1045 4.8978C55.5792 2.8214 50.7265 1.2916 45.6527 0.41542C45.5603 0.39851 45.468 0.440769 45.4204 0.525289C44.7963 1.6353 44.105 3.0834 43.6209 4.2216C38.1637 3.4046 32.7345 3.4046 27.3892 4.2216C26.905 3.0581 26.1886 1.6353 25.5617 0.525289C25.5141 0.443589 25.4218 0.40133 25.3294 0.41542C20.2584 1.2888 15.4057 2.8186 10.8776 4.8978C10.8384 4.9147 10.8048 4.9429 10.7825 4.9795C1.57795 18.7309 -0.943561 32.1443 0.293408 45.3914C0.299005 45.4562 0.335386 45.5182 0.385761 45.5576C6.45866 50.0174 12.3413 52.7249 18.1147 54.5195C18.2071 54.5477 18.305 54.5139 18.3638 54.4378C19.7295 52.5728 20.9469 50.6063 21.9907 48.5383C22.0523 48.4172 21.9935 48.2735 21.8676 48.2256C19.9366 47.4931 18.0979 46.6 16.3292 45.5858C16.1893 45.5041 16.1781 45.304 16.3068 45.2082C16.679 44.9293 17.0513 44.6391 17.4067 44.3461C17.471 44.2926 17.5606 44.2813 17.6362 44.3151C29.2558 49.6202 41.8354 49.6202 53.3179 44.3151C53.3935 44.2785 53.4831 44.2898 53.5502 44.3433C53.9057 44.6363 54.2779 44.9293 54.6529 45.2082C54.7816 45.304 54.7732 45.5041 54.6333 45.5858C52.8646 46.6197 51.0259 47.4931 49.0921 48.2228C48.9662 48.2707 48.9102 48.4172 48.9718 48.5383C50.038 50.6034 51.2554 52.5699 52.5959 54.435C52.6519 54.5139 52.7526 54.5477 52.845 54.5195C58.6464 52.7249 64.529 50.0174 70.6019 45.5576C70.6551 45.5182 70.6887 45.459 70.6943 45.3942C72.1747 30.0791 68.2147 16.7757 60.1968 4.9823C60.1772 4.9429 60.1437 4.9147 60.1045 4.8978ZM23.7259 37.3253C20.2276 37.3253 17.3451 34.1136 17.3451 30.1693C17.3451 26.225 20.1717 23.0133 23.7259 23.0133C27.308 23.0133 30.1626 26.2532 30.1066 30.1693C30.1066 34.1136 27.28 37.3253 23.7259 37.3253ZM47.3178 37.3253C43.8196 37.3253 40.9371 34.1136 40.9371 30.1693C40.9371 26.225 43.7636 23.0133 47.3178 23.0133C50.9 23.0133 53.7545 26.2532 53.6986 30.1693C53.6986 34.1136 50.9 37.3253 47.3178 37.3253Z" />
    </svg>
);

// Enhanced Header component with navigation tabs
const Header = () => {
    const { isDarkMode, currentThemeId, setThemeById, availableThemes } = useTheme();
    const { isAuthenticated, user, logout } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const muiTheme = useMuiTheme();
    const isMobile = useMediaQuery(muiTheme.breakpoints.down("sm"));
    const isTablet = useMediaQuery(muiTheme.breakpoints.between("sm", "md"));
    const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
    const [themeMenuAnchor, setThemeMenuAnchor] = useState<null | HTMLElement>(null);
    const [accountMenuAnchor, setAccountMenuAnchor] = useState<null | HTMLElement>(null);
    const scrollDirection = useScrollDirection();

    // Determine the current path for active tab highlighting
    const getCurrentPath = () => {
        if (location.pathname.startsWith("/download")) return "/download";

        if (isAuthenticated) {
            // avoid a warning in the console during loading before useAuth kicks in
            if (location.pathname.startsWith("/library")) return "/library";
            if (location.pathname.startsWith("/history")) return "/history";
        }
        if (location.pathname.startsWith("/reading-lists")) return "/reading-lists";
        if (location.pathname.startsWith("/boards")) return "/boards";
        if (location.pathname.startsWith("/novels")) return "/";
        if (location.pathname === "/") return "/";
        return "/";
    };

    const handleMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
        setMenuAnchor(event.currentTarget);
    };

    const handleMenuClose = () => {
        setMenuAnchor(null);
    };

    const handleThemeMenuOpen = (event: React.MouseEvent<HTMLButtonElement>) => {
        setThemeMenuAnchor(event.currentTarget);
    };

    const handleThemeMenuClose = () => {
        setThemeMenuAnchor(null);
    };

    const handleThemeChange = (themeId: string) => {
        setThemeById(themeId);
        handleThemeMenuClose();
    };

    const handleAccountMenuOpen = (event: React.MouseEvent<HTMLButtonElement | HTMLDivElement>) => {
        setAccountMenuAnchor(event.currentTarget);
    };

    const handleAccountMenuClose = () => {
        setAccountMenuAnchor(null);
    };

    const handleLogout = async () => {
        try {
            await logout();
            handleAccountMenuClose();
            navigate("/");
        } catch (error) {
            console.error("Logout failed:", error);
        }
    };

    // Use the appropriate logo based on dark mode
    const logoSrc = isDarkMode ? logoDark : logoLight;

    // Get user's initials for avatar
    const getUserInitials = () => {
        if (!user || !user.username) return "?";
        return user.username.charAt(0).toUpperCase();
    };

    return (
        <AppBar
            position="sticky"
            color="default"
            elevation={1}
            sx={{
                transition: "transform 0.3s ease-in-out",
                ...((isMobile || isTablet) && {
                    transform: scrollDirection === "down" ? "translateY(-100%)" : "translateY(0)",
                }),
            }}
        >
            <Toolbar sx={{ justifyContent: "space-between", minHeight: isTablet ? 56 : 64, px: isTablet ? 1 : 2 }}>
                {/* Logo/Home section */}
                <Box sx={{ display: "flex", alignItems: "center" }}>
                    <Box
                        component={RouterLink}
                        to="/"
                        sx={{
                            display: "flex",
                            alignItems: "center",
                            textDecoration: "none",
                            color: "inherit",
                        }}
                    >
                        <Box
                            component="img"
                            src={logoSrc}
                            alt="LNCrawler Logo"
                            sx={{
                                height: 40,
                                mr: 1,
                            }}
                        />
                        { !isTablet && (
                            <Typography variant="h6" component="div" sx={{ fontWeight: "bold" }}>
                                LNCrawler
                            </Typography>
                        )}
                    </Box>
                </Box>

                {/* Navigation Links - Desktop and Tablet */}
                {!isMobile && (
                    <Tabs
                        value={getCurrentPath()}
                        indicatorColor="primary"
                        textColor="primary"
                        sx={{
                            flexGrow: 1,
                            ml: isTablet ? 1 : 2,
                            "& .MuiTab-root": {
                                      minWidth: "auto",
                                      px: isTablet ? 1 : 1.5,
                                  },
                        }}
                    >
                        <Tab label="Home" value="/" component={RouterLink} to="/" />
                        {isAuthenticated && <Tab label="Library" value="/library" component={RouterLink} to="/library" />}
                        {isAuthenticated && <Tab label="History" value="/history" component={RouterLink} to="/history" />}
                        <Tab label="Lists" value="/reading-lists" component={RouterLink} to="/reading-lists" />
                        <Tab label="Chat" value="/boards" component={RouterLink} to="/boards" />
                        <Tab label="Add Novel" value="/download" component={RouterLink} to="/download" />
                    </Tabs>
                )}

                {/* Actions section */}
                <Box sx={{ display: "flex", alignItems: "center" }}>
                    {/* Search Button */}
                    <IconButton
                        component={RouterLink}
                        to="/novels/search"
                        color="inherit"
                        aria-label="Search"
                        sx={{ padding: isTablet ? 0.5 : 1 }}
                    >
                        <SearchIcon sx={{ fontSize: isTablet ? "1.25rem" : "1.5rem" }} />
                    </IconButton>

                    {/* Discord Link - Hide on tablet */}
                    {!isTablet && (
                        <IconButton
                            component={Link}
                            href="https://discord.gg/a2b4Mfr4cU"
                            target="_blank"
                            rel="noopener noreferrer"
                            color="inherit"
                            aria-label="Discord"
                            sx={{ padding: isTablet ? 0.5 : 1 }}
                        >
                            <DiscordIcon />
                        </IconButton>
                    )}

                    {/* GitHub Link - Hide on tablet */}
                    {!isTablet && (
                        <IconButton
                            component={Link}
                            href="https://github.com/jere344/lightnovel-crawler-website"
                            target="_blank"
                            rel="noopener noreferrer"
                            color="inherit"
                            aria-label="GitHub"
                            sx={{ padding: isTablet ? 0.5 : 1 }}
                        >
                            <GitHubIcon sx={{ fontSize: isTablet ? "1.25rem" : "1.5rem" }} />
                        </IconButton>
                    )}

                    {/* Theme Menu */}
                    <IconButton
                        onClick={handleThemeMenuOpen}
                        color="inherit"
                        aria-label="Change theme"
                        aria-controls="theme-menu"
                        aria-haspopup="true"
                        sx={{ padding: isTablet ? 0.5 : 1 }}
                    >
                        <PaletteIcon sx={{ fontSize: isTablet ? "1.25rem" : "1.5rem" }} />
                    </IconButton>
                    <Menu
                        id="theme-menu"
                        anchorEl={themeMenuAnchor}
                        open={Boolean(themeMenuAnchor)}
                        onClose={handleThemeMenuClose}
                        anchorOrigin={{
                            vertical: "bottom",
                            horizontal: "right",
                        }}
                        transformOrigin={{
                            vertical: "top",
                            horizontal: "right",
                        }}
                    >
                        {availableThemes
                            .filter((theme) => !theme.hidden)
                            .map((theme) => (
                                <MenuItem key={theme.id} onClick={() => handleThemeChange(theme.id)} selected={currentThemeId === theme.id}>
                                    {currentThemeId === theme.id && (
                                        <ListItemIcon>
                                            <CheckIcon fontSize="small" />
                                        </ListItemIcon>
                                    )}
                                    <ListItemText inset={currentThemeId !== theme.id} primary={theme.name} />
                                </MenuItem>
                            ))}
                    </Menu>

                    {/* Authentication Menu */}
                    {isAuthenticated ? (
                        <>
                            <Box
                                onClick={handleAccountMenuOpen}
                                sx={{
                                    display: "flex",
                                    alignItems: "center",
                                    cursor: "pointer",
                                    ml: 1,
                                }}
                            >
                                <Avatar
                                    sx={{
                                        width: isTablet ? 28 : 32,
                                        height: isTablet ? 28 : 32,
                                        bgcolor: "primary.main",
                                        fontSize: isTablet ? "0.75rem" : "0.875rem",
                                    }}
                                    src={user?.profile_pic || undefined}
                                >
                                    {getUserInitials()}
                                </Avatar>
                                {!isMobile && !isTablet && (
                                    <Typography variant="body2" sx={{ ml: 1 }}>
                                        {user?.username || "User"}
                                    </Typography>
                                )}
                            </Box>
                            <Menu
                                id="account-menu"
                                anchorEl={accountMenuAnchor}
                                open={Boolean(accountMenuAnchor)}
                                onClose={handleAccountMenuClose}
                                anchorOrigin={{
                                    vertical: "bottom",
                                    horizontal: "right",
                                }}
                                transformOrigin={{
                                    vertical: "top",
                                    horizontal: "right",
                                }}
                            >
                                <MenuItem component={RouterLink} to="/profile" onClick={handleAccountMenuClose}>
                                    <ListItemIcon>
                                        <PersonIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary="Profile" />
                                </MenuItem>
                                <MenuItem onClick={handleLogout}>
                                    <ListItemIcon>
                                        <LogoutIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary="Logout" />
                                </MenuItem>
                            </Menu>
                        </>
                    ) : !isMobile ? (
                        <Box sx={{ ml: 1 }}>
                            <Button
                                variant={isTablet ? "text" : "outlined"}
                                size="small"
                                component={RouterLink}
                                to="/login"
                                startIcon={!isTablet && <LoginIcon />}
                                sx={{ mr: 1, px: isTablet ? 1 : 2 }}
                            >
                                Login
                            </Button>
                        </Box>
                    ) : (
                        <IconButton color="inherit" onClick={handleAccountMenuOpen} aria-label="Account">
                            <AccountCircleIcon />
                        </IconButton>
                    )}

                    {/* Mobile Menu Button */}
                    {isMobile && (
                        <>
                            <IconButton edge="end" color="inherit" aria-label="menu" onClick={handleMenuOpen}>
                                <MenuIcon />
                            </IconButton>
                            <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={handleMenuClose}>
                                <MenuItem component={RouterLink} to="/" onClick={handleMenuClose}>
                                    Home
                                </MenuItem>
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/library" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <LibraryBooksIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary="Library" />
                                    </MenuItem>
                                )}
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/history" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <HistoryIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary="Reading History" />
                                    </MenuItem>
                                )}
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/reading-lists" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <FormatListBulletedIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary="Reading Lists" />
                                    </MenuItem>
                                )}
                                <MenuItem component={RouterLink} to="/boards" onClick={handleMenuClose}>
                                    <ListItemIcon>
                                        <ForumIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary="Chat" />
                                </MenuItem>
                                <MenuItem component={RouterLink} to="/download" onClick={handleMenuClose}>
                                    Add Novel
                                </MenuItem>
                            </Menu>
                        </>
                    )}

                    {/* Tablet More Menu Button */}
                    {isTablet && (
                        <>
                            <IconButton edge="end" color="inherit" aria-label="menu" onClick={handleMenuOpen} sx={{ padding: 0.5 }}>
                                <MenuIcon sx={{ fontSize: "1.25rem" }} />
                            </IconButton>
                            <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={handleMenuClose}>
                                <MenuItem
                                    component={Link}
                                    href="https://discord.gg/a2b4Mfr4cU"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={handleMenuClose}
                                >
                                    <ListItemIcon>
                                        <DiscordIcon />
                                    </ListItemIcon>
                                    <ListItemText primary="Discord" />
                                </MenuItem>
                                <MenuItem
                                    component={Link}
                                    href="https://github.com/jere344/lightnovel-crawler-website"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={handleMenuClose}
                                >
                                    <ListItemIcon>
                                        <GitHubIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary="GitHub" />
                                </MenuItem>
                            </Menu>
                        </>
                    )}

                    {/* Mobile Account Menu */}
                    {isMobile && !isAuthenticated && (
                        <Menu anchorEl={accountMenuAnchor} open={Boolean(accountMenuAnchor)} onClose={handleAccountMenuClose}>
                            <MenuItem component={RouterLink} to="/login" onClick={handleAccountMenuClose}>
                                <ListItemIcon>
                                    <LoginIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText primary="Login" />
                            </MenuItem>
                            <MenuItem component={RouterLink} to="/register" onClick={handleAccountMenuClose}>
                                <ListItemIcon>
                                    <PersonIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText primary="Register" />
                            </MenuItem>
                        </Menu>
                    )}
                </Box>
            </Toolbar>
        </AppBar>
    );
};

export default Header;
