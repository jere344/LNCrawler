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
import HomeIcon from '@mui/icons-material/Home';
import AddIcon from '@mui/icons-material/Add';
import HeadphonesIcon from '@mui/icons-material/Headphones';
import { useTheme as useMuiTheme } from "@mui/material/styles";
import { useTheme } from "@theme/ThemeContext";
import { useNavigate, useLocation, useMatches, Link as RouterLink } from "react-router-dom";
import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../context/AuthContext";
import LanguageSwitcher from "./common/LanguageSwitcher";
import { useReaderSetting } from "./reader/hooks/useReaderSettings";
import { useFullscreen } from "./reader/hooks/useFullscreen";

// Import logos
import logoLight from "@assets/logo-transparent.png";
import logoDark from "@assets/logo-transparent-dark.png";

// Width from which the tabs show their label next to the icon
const DESKTOP_MIN_WIDTH = 1400;

// Narrowest widths at which the tablet tabs can show their label next to the icon
const TABLET_LABELS_MIN_WIDTH = 1060;
const TABLET_LABELS_AUTH_MIN_WIDTH = 1280;

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
    // Burger layout below md; icon-only tabs up to DESKTOP_MIN_WIDTH (full labels would overlap the actions before that)
    const isMobile = useMediaQuery(muiTheme.breakpoints.down("md"));
    const isTablet = useMediaQuery(`(min-width:${muiTheme.breakpoints.values.md}px) and (max-width:${DESKTOP_MIN_WIDTH - 0.05}px)`);
    // Tablet tabs get their label back as soon as the toolbar has room (logged-in users have two more tabs)
    const tabLabelsFit = useMediaQuery(`(min-width:${isAuthenticated ? TABLET_LABELS_AUTH_MIN_WIDTH : TABLET_LABELS_MIN_WIDTH}px)`);
    const isSmallMobile = useMediaQuery(muiTheme.breakpoints.down("sm"));
    const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
    const [themeMenuAnchor, setThemeMenuAnchor] = useState<null | HTMLElement>(null);
    const [accountMenuAnchor, setAccountMenuAnchor] = useState<null | HTMLElement>(null);
    const scrollDirection = useScrollDirection();
    const matches = useMatches();
    const onReaderRoute = matches.some((match) => (match.handle as { readerRoute?: boolean } | undefined)?.readerRoute);
    const readerHeaderBehavior = useReaderSetting("readerHeaderBehavior");
    const { active: fullscreenActive } = useFullscreen();

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
        if (location.pathname.startsWith("/audiobooks")) return "/audiobooks";
        if (location.pathname.startsWith("/novels/search")) return "/novels/search";
        if (location.pathname.startsWith("/novels")) return "/";
        if (location.pathname === "/") return "/";
        return "/";
    };

    const navItems = [
        { to: "/", label: t('header.home'), icon: <HomeIcon /> },
        { to: "/audiobooks", label: t('audiobooks.title'), icon: <HeadphonesIcon /> },
        ...(isAuthenticated
            ? [
                  { to: "/library", label: t('header.library'), icon: <LibraryBooksIcon /> },
                  { to: "/history", label: t('header.history'), icon: <HistoryIcon /> },
              ]
            : []),
        { to: "/reading-lists", label: t('header.lists'), icon: <FormatListBulletedIcon /> },
        { to: "/chat", label: t('header.chat'), icon: <ForumIcon /> },
        { to: "/novels/search", label: t('header.search'), icon: <SearchIcon /> },
    ];

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

    // The reader scrolls the site header away with the page: always on desktop, and on touch
    // only with the 'pageTop' setting. Elsewhere, on mobile/tablet the bar is fixed and hidden
    // with a transform, so it never changes the document flow. A spacer of the same height keeps content in place.
    const touchLayout = isMobile;
    const staticHeader = onReaderRoute && (!touchLayout || readerHeaderBehavior === "pageTop");
    const hideOnScroll = touchLayout && !staticHeader;
    const toolbarHeight = isMobile && !isSmallMobile ? 56 : 64;

    // Fullscreen on the reader: the site header is left out entirely, so no gap is kept above the reader
    if (onReaderRoute && fullscreenActive) return null;

    return (
        <>
        <AppBar
            data-app-header
            position={staticHeader ? "static" : hideOnScroll ? "fixed" : "sticky"}
            color="default"
            elevation={1}
            sx={{
                transition: "transform 0.3s ease-in-out",
                ...(hideOnScroll && {
                    transform: scrollDirection === "down" ? "translateY(-100%)" : "translateY(0)",
                }),
            }}
        >
            <Toolbar sx={{ justifyContent: "space-between", minHeight: toolbarHeight, px: isTablet ? 1 : 2 }}>
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
                        {/* Title hidden on the narrowest screens so the toolbar fits in 320 px */}
                        { (
                            <Typography variant="h6" component="div" sx={{ fontWeight: "bold", "@media (max-width:359px)": { display: "none" } }}>
                                LNCrawler
                            </Typography>
                        )}
                    </Box>
                </Box>

                {/* Navigation Links - Desktop (icon + label) and Tablet (icon only) */}
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
                                px: isTablet ? 1.5 : 1.5,
                            },
                        }}
                    >
                        {navItems.map((item) => (
                            <Tab
                                key={item.to}
                                value={item.to}
                                component={RouterLink}
                                to={item.to}
                                icon={item.icon}
                                iconPosition="start"
                                label={isTablet && !tabLabelsFit ? undefined : item.label}
                                aria-label={item.label}
                                title={isTablet && !tabLabelsFit ? item.label : undefined}
                            />
                        ))}
                    </Tabs>
                )}

                {/* Actions section */}
                <Box sx={{ display: "flex", alignItems: "center" }}>
                    {/* Add Novel - Desktop with label, tablet icon only, mobile in the burger menu */}
                    {!isMobile && !isTablet && (
                        <Button
                            variant="outlined"
                            size="small"
                            component={RouterLink}
                            to="/download"
                            startIcon={<AddIcon />}
                            sx={{ mr: 1, px: 2, whiteSpace: "nowrap" }}
                        >
                            {t('header.addNovel')}
                        </Button>
                    )}
                    {isTablet && (
                        <IconButton
                            component={RouterLink}
                            to="/download"
                            color="inherit"
                            aria-label={t('header.addNovel')}
                            title={t('header.addNovel')}
                            sx={{ padding: 0.5 }}
                        >
                            <AddIcon sx={{ fontSize: "1.5rem" }} />
                        </IconButton>
                    )}

                    {/* GitHub Link - Hide on mobile (the footer has the link) */}
                    {!isMobile && (
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
                                    <ListItemIcon>
                                        <HomeIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.home')} />
                                </MenuItem>
                                <MenuItem component={RouterLink} to="/download" onClick={handleMenuClose}>
                                    <ListItemIcon>
                                        <AddIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('header.addNovel')} />
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
                                <MenuItem component={RouterLink} to="/audiobooks" onClick={handleMenuClose}>
                                    <ListItemIcon>
                                        <HeadphonesIcon fontSize="small" />
                                    </ListItemIcon>
                                    <ListItemText primary={t('audiobooks.title')} />
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
        {hideOnScroll && <Box sx={{ height: toolbarHeight }} />}
        </>
    );
};

export default Header;
