import { Routes, Route, useLocation } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider, Container, Box } from "@mui/material";
import { useLayoutEffect } from "react";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import Header from '@components/Header';
import Footer from '@components/Footer';
import DownloaderHome from '@components/downloader/DownloaderHome';
import SearchResults from '@components/downloader/SearchResults';
import DownloadForm from '@components/downloader/DownloadForm';
import DownloadStatus from '@components/downloader/DownloadStatus';
import NovelDetail from '@components/novels/NovelDetail';
import SourceDetail from '@components/novels/SourceDetail';
import ChapterList from '@components/novels/ChapterList';
import ChapterReader from '@components/novels/ChapterReader';
import SearchPage from '@components/search/SearchPage';
import HomePage from '@components/home/HomePage';
// Import new auth components
import LoginPage from '@components/auth/LoginPage';
import RegisterPage from '@components/auth/RegisterPage';
import ProfilePage from '@components/auth/ProfilePage';
// Import new library page
import LibraryPage from '@components/library/LibraryPage';
// Import reading history page
import ReadingHistoryPage from '@components/history/ReadingHistoryPage';

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

    return (
        <MuiThemeProvider theme={theme}>
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
                        <Routes>
                            {/* Authentication routes */}
                            <Route path="/login" element={<LoginPage />} />
                            <Route path="/register" element={<RegisterPage />} />
                            <Route path="/profile" element={<ProfilePage />} />
                            
                            {/* Library and History routes */}
                            <Route path="/library" element={<LibraryPage />} />
                            <Route path="/history" element={<ReadingHistoryPage />} />
                            
                            {/* Downloader routes */}
                            <Route path="/download" element={<DownloaderHome />} />
                            <Route path="/download/search/:jobId" element={<SearchResults />} />
                            <Route path="/download/:jobId/:sourceIndex/:novelIndex" element={<DownloadForm />} />
                            <Route path="/download/status/:jobId" element={<DownloadStatus />} />
                            
                            {/* Novel reading routes with new URL structure */}
                            <Route path="/novels/search" element={<SearchPage />} />
                            <Route path="/novels/:novelSlug" element={<NovelDetail />} />
                            <Route path="/novels/:novelSlug/:sourceSlug" element={<SourceDetail />} />
                            <Route path="/novels/:novelSlug/:sourceSlug/chapterlist" element={<ChapterList />} />
                            <Route path="/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber" element={<ChapterReader />} />
                            
                            {/* Home page */}
                            <Route path="/" element={<HomePage />} />
                            
                        </Routes>
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
