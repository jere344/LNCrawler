import { Routes, Route, useLocation, Navigate } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider, Container, Box, CircularProgress, createTheme } from "@mui/material";
import { lazy, Suspense, useLayoutEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import { useLanguage } from "@context/LanguageContext";
import { getMuiLocale, muiDirection } from "./i18n/muiLocale";
import Header from '@components/Header';
import Footer from '@components/Footer';

// Route-level code splitting: each page (and everything it alone imports, e.g.
// the reader or mdxeditor) is fetched on navigation instead of on first paint.
const DownloaderHome = lazy(() => import('@components/downloader/DownloaderHome'));
const SearchResults = lazy(() => import('@components/downloader/SearchResults'));
const DownloadForm = lazy(() => import('@components/downloader/DownloadForm'));
const DownloadStatus = lazy(() => import('@components/downloader/DownloadStatus'));
const NovelRedirect = lazy(() => import('@components/novels/NovelRedirect'));
const SourceDetail = lazy(() => import('@components/novels/SourceDetail'));
const ChapterList = lazy(() => import('@components/novels/ChapterList'));
const ChapterReader = lazy(() => import('@components/reader/ChapterReader'));
const SearchPage = lazy(() => import('@components/search/SearchPage'));
const HomePage = lazy(() => import('@components/home/HomePage'));
const LoginPage = lazy(() => import('@components/auth/LoginPage'));
const RegisterPage = lazy(() => import('@components/auth/RegisterPage'));
const ProfilePage = lazy(() => import('@components/auth/ProfilePage'));
const ResetPasswordPage = lazy(() => import('@components/auth/ResetPasswordPage'));
const LibraryPage = lazy(() => import('@components/library/LibraryPage'));
const ReadingHistoryPage = lazy(() => import('@components/history/ReadingHistoryPage'));
const ImageGallery = lazy(() => import('@components/novels/ImageGallery'));
const BoardList = lazy(() => import('@components/boards/BoardList'));
const BoardDetail = lazy(() => import('@components/boards/BoardDetail'));
const ReadingListsPage = lazy(() => import('@components/readinglist/ReadingListsPage'));
const ReadingListDetail = lazy(() => import('@components/readinglist/ReadingListDetail'));

const Wrapper = ({ children }: { children: React.ReactNode }) => {
    const location = useLocation();

    useLayoutEffect(() => {
        // Only scroll to top if there's no hash in the URL
        if (!window.location.hash) {
            window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
        }
    }, [location.pathname, location.search]);

    return <>{children}</>;
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
                        <Routes>
                            {/* Authentication routes */}
                            <Route path="/login" element={<LoginPage />} />
                            <Route path="/register" element={<RegisterPage />} />
                            <Route path="/profile" element={<ProfilePage />} />
                            <Route path="/reset-password" element={<ResetPasswordPage />} />
                            
                            {/* Library and History routes */}
                            <Route path="/library" element={<LibraryPage />} />
                            <Route path="/history" element={<ReadingHistoryPage />} />
                            
                            {/* Reading Lists routes */}
                            <Route path="/reading-lists" element={<ReadingListsPage />} />
                            <Route path="/reading-lists/:listId" element={<ReadingListDetail />} />

                            {/* Board routes */}
                            <Route path="/boards" element={<BoardList />} />
                            <Route path="/boards/:boardSlug" element={<BoardDetail />} />
                            
                            {/* Downloader routes */}
                            <Route path="/download" element={<DownloaderHome />} />
                            <Route path="/download/search/:jobId" element={<SearchResults />} />
                            <Route path="/download/:jobId/:novelIndex/:sourceIndex" element={<DownloadForm />} />
                            <Route path="/download/status/:jobId" element={<DownloadStatus />} />
                            
                            {/* Novel reading routes with new URL structure */}
                            <Route path="/novels/search" element={<SearchPage />} />
                            <Route path="/novels/:novelSlug" element={<NovelRedirect />} />
                            <Route path="/novels/:novelSlug/:sourceSlug" element={<SourceDetail />} />
                            <Route path="/novels/:novelSlug/:sourceSlug/chapterlist" element={<ChapterList />} />
                            <Route path="/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber" element={<ChapterReader />} />
                            <Route path="/novels/:novelSlug/:sourceSlug/gallery" element={<ImageGallery />} />
                            
                            {/* Home page */}
                            <Route path="/" element={<HomePage />} />

                            {/* Fallback route - redirect to home */}
                            <Route path="*" element={<Navigate to="/" replace />} />

                            
                        </Routes>
                        </Suspense>
                    </Container>
                    <Footer />
                </Box>
            </Wrapper>
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
