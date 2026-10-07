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
import SettingsIcon from "@mui/icons-material/Settings";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import HistoryIcon from "@mui/icons-material/History";
import ForumIcon from "@mui/icons-material/Forum"; // Import Forum icon for Chat
import FormatListBulletedIcon from '@mui/icons-material/FormatListBulleted'; // Import icon for reading lists
import { useTheme as useMuiTheme } from "@mui/material/styles";
import { useTheme } from "@theme/ThemeContext";
import { useNavigate, useLocation, Link as RouterLink } from "react-router-dom";
import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import LanguageSwitcher from "./common/LanguageSwitcher";

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

// Enhanced Header component with navigation tabs
const Header = () => {
    const { isDarkMode, currentThemeId, setThemeById, availableThemes } = useTheme();
    const { t } = useTranslation();
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
        if (location.pathname.startsWith("/chat")) return "/chat";
        if (location.pathname.startsWith("/novels/search")) return "/novels/search";
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
                            alt={t('header.logoAlt')}
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
                        <Tab label={t('header.home')} value="/" component={RouterLink} to="/" />
                        {isAuthenticated && <Tab label={t('header.library')} value="/library" component={RouterLink} to="/library" />}
                        {isAuthenticated && <Tab label={t('header.history')} value="/history" component={RouterLink} to="/history" />}
                        <Tab label={t('header.lists')} value="/reading-lists" component={RouterLink} to="/reading-lists" />
                        <Tab label={t('header.chat')} value="/chat" component={RouterLink} to="/chat" />
                        <Tab label={t('header.search')} value="/novels/search" component={RouterLink} to="/novels/search" />
                    </Tabs>
                )}

                {/* Actions section */}
                <Box sx={{ display: "flex", alignItems: "center" }}>
                    {/* Add Novel - Desktop only, on tablet it lives in the burger menu */}
                    {!isMobile && !isTablet && (
                        <Button
                            variant="outlined"
                            size="small"
                            component={RouterLink}
                            to="/download"
                            sx={{ mr: 1, px: isTablet ? 1 : 2, whiteSpace: "nowrap" }}
                        >
                            {t('header.addNovel')}
                        </Button>
                    )}

                    {/* GitHub Link - Hide on tablet */}
                    {!isTablet && (
                        <IconButton
                            component={Link}
                            href="https://github.com/jere344/LNCrawler"
                            target="_blank"
                            rel="noopener noreferrer"
                            color="inherit"
                            aria-label={t('header.github')}
                            sx={{ padding: isTablet ? 0.5 : 1 }}
                        >
                            <GitHubIcon sx={{ fontSize: isTablet ? "1.25rem" : "1.5rem" }} />
                        </IconButton>
                    )}

                    {/* Interface Language */}
                    <LanguageSwitcher />

                    {/* Theme Menu */}
                    <IconButton
                        onClick={handleThemeMenuOpen}
                        color="inherit"
                        aria-label={t('header.changeTheme')}
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
                                    <ListItemText inset={currentThemeId !== theme.id} primary={t('themes.' + theme.id)} />
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
                                        {user?.username || t('header.userFallback')}
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
                                <MenuItem component={RouterLink} to={user ? `/u/${encodeURIComponent(user.username)}` : "/"} onClick={handleAccountMenuClose}>
                                    <ListItemIcon>
                                        <PersonIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.profile')} />
                                </MenuItem>
                                <MenuItem component={RouterLink} to="/settings" onClick={handleAccountMenuClose}>
                                    <ListItemIcon>
                                        <SettingsIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.settings')} />
                                </MenuItem>
                                <MenuItem onClick={handleLogout}>
                                    <ListItemIcon>
                                        <LogoutIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.logout')} />
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
                                {t('header.login')}
                            </Button>
                        </Box>
                    ) : (
                        <IconButton color="inherit" onClick={handleAccountMenuOpen} aria-label={t('header.account')}>
                            <AccountCircleIcon />
                        </IconButton>
                    )}

                    {/* Mobile Menu Button */}
                    {isMobile && (
                        <>
                            <IconButton edge="end" color="inherit" aria-label={t('header.menu')} onClick={handleMenuOpen}>
                                <MenuIcon />
                            </IconButton>
                            <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={handleMenuClose}>
                                <MenuItem component={RouterLink} to="/" onClick={handleMenuClose}>
                                    {t('header.home')}
                                </MenuItem>
                                <MenuItem component={RouterLink} to="/download" onClick={handleMenuClose}>
                                    {t('header.addNovel')}
                                </MenuItem>
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/library" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <LibraryBooksIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary={t('header.library')} />
                                    </MenuItem>
                                )}
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/history" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <HistoryIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary={t('header.readingHistory')} />
                                    </MenuItem>
                                )}
                                {isAuthenticated && (
                                    <MenuItem component={RouterLink} to="/reading-lists" onClick={handleMenuClose}>
                                        <ListItemIcon>
                                            <FormatListBulletedIcon fontSize="small" />
                                        </ListItemIcon>
                                        <ListItemText primary={t('header.readingLists')} />
                                    </MenuItem>
                                )}
                                <MenuItem component={RouterLink} to="/chat" onClick={handleMenuClose}>
                                    <ListItemIcon>
                                        <ForumIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.chat')} />
                                </MenuItem>
                                <MenuItem component={RouterLink} to="/novels/search" onClick={handleMenuClose}>
                                    <ListItemIcon>
                                        <SearchIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.search')} />
                                </MenuItem>
                            </Menu>
                        </>
                    )}

                    {/* Tablet More Menu Button */}
                    {isTablet && (
                        <>
                            <IconButton edge="end" color="inherit" aria-label={t('header.menu')} onClick={handleMenuOpen} sx={{ padding: 0.5 }}>
                                <MenuIcon sx={{ fontSize: "1.25rem" }} />
                            </IconButton>
                            <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={handleMenuClose}>
                                <MenuItem component={RouterLink} to="/download" onClick={handleMenuClose}>
                                    {t('header.addNovel')}
                                </MenuItem>
                                <MenuItem
                                    component={Link}
                                    href="https://github.com/jere344/LNCrawler"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={handleMenuClose}
                                >
                                    <ListItemIcon>
                                        <GitHubIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.github')} />
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
                                <ListItemText primary={t('header.login')} />
                            </MenuItem>
                            <MenuItem component={RouterLink} to="/register" onClick={handleAccountMenuClose}>
                                <ListItemIcon>
                                    <PersonIcon fontSize="small" />
                                </ListItemIcon>
                                <ListItemText primary={t('header.register')} />
                            </MenuItem>
                        </Menu>
                    )}
                </Box>
            </Toolbar>
        </AppBar>
    );
};

export default Header;
