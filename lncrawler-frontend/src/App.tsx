import { Outlet } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider, Container, Box, CircularProgress, createTheme } from "@mui/material";
import { Suspense, useMemo } from "react";
import { useTranslation } from "react-i18next";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import { useLanguage } from "@context/LanguageContext";
import { getMuiLocale, muiDirection } from "./i18n/muiLocale";
import Header from '@components/Header';
import Footer from '@components/Footer';
import ErrorBoundary from '@components/common/ErrorBoundary';
import { NotificationProvider } from '@context/NotificationContext';
import { AudioPlayerProvider, useAudioPlayer } from '@context/AudioPlayerContext';
import MiniPlayer from '@components/audio/MiniPlayer';
import FullPlayer from '@components/audio/FullPlayer';
import { useScrollRestoration } from './router/useScrollRestoration';

const Wrapper = ({ children }: { children: React.ReactNode }) => {
    useScrollRestoration();

    return <>{children}</>;
};

// Keeps the page bottom clear of the mini player while it is shown.
const PlayerSpacer = () => {
    const { barHeight } = useAudioPlayer();

    return <Box sx={{ height: barHeight > 0 ? `calc(${barHeight}px + env(safe-area-inset-bottom))` : 0 }} />;
};

// App with theme context
function AppWithTheme() {
    const { theme } = useTheme();
    const { i18n } = useTranslation();
    const { uiLanguage } = useLanguage();

    // Resolve the active code ('' means "browser" -> whatever i18next detected).
    const activeLanguage = uiLanguage || i18n.resolvedLanguage || 'en';

    const localizedTheme = useMemo(
        () => createTheme(theme, getMuiLocale(activeLanguage), { direction: muiDirection(activeLanguage) }),
        [theme, activeLanguage]
    );

    return (
        <MuiThemeProvider theme={localizedTheme}>
            <ErrorBoundary>
                <NotificationProvider>
                <AudioPlayerProvider>
                <Wrapper>
                <Box
                    sx={{
                        display: 'flex',
                        flexDirection: 'column',
                        minHeight: '100vh',
                    }}
                >
                    <CssBaseline />
                    <Header />
                    <Container 
                        maxWidth="lg" 
                        sx={{ 
                            px: { xs: 0, sm: 3, md: 4 }, 
                            py: 2,
                            flex: '1 0 auto' 
                        }}
                    >
                        <Suspense
                            fallback={
                                <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
                                    <CircularProgress />
                                </Box>
                            }
                        >
                            <Outlet />
                        </Suspense>
                    </Container>
                    <Footer />
                    <PlayerSpacer />
                </Box>
                <MiniPlayer />
                <FullPlayer />
                </Wrapper>
                </AudioPlayerProvider>
                </NotificationProvider>
            </ErrorBoundary>
        </MuiThemeProvider>
    );
}

// Root App component
function App() {
    return (
        <ThemeProvider>
            <AppWithTheme />
        </ThemeProvider>
    );
}

export default App;
