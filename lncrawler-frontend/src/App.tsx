import { Routes, Route, useLocation, Navigate } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider } from "@mui/material";
import { useLayoutEffect } from "react";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import Header from '@components/downloader/Header';
import DownloaderHome from '@components/downloader/DownloaderHome';
import SearchResults from '@components/downloader/SearchResults';
import DownloadForm from '@components/downloader/DownloadForm';
import DownloadStatus from '@components/downloader/DownloadStatus';
import NovelList from '@components/novels/NovelList';
import NovelDetail from '@components/novels/NovelDetail';
import SourceDetail from '@components/novels/SourceDetail';
import ChapterList from '@components/novels/ChapterList';
import ChapterReader from '@components/novels/ChapterReader';
import SearchPage from '@components/search/SearchPage';

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
                <CssBaseline />
                <Header />
                <Routes>
                    {/* Downloader routes */}
                    <Route path="/download" element={<DownloaderHome />} />
                    <Route path="/download/search/:jobId" element={<SearchResults />} />
                    <Route path="/download/:jobId/:sourceIndex/:novelIndex" element={<DownloadForm />} />
                    <Route path="/download/status/:jobId" element={<DownloadStatus />} />
                    
                    {/* Novel reading routes with new URL structure */}
                    <Route path="/novels" element={<NovelList />} />
                    <Route path="/novels/search" element={<SearchPage />} />
                    <Route path="/novels/:novelSlug" element={<NovelDetail />} />
                    <Route path="/novels/:novelSlug/:sourceSlug" element={<SourceDetail />} />
                    <Route path="/novels/:novelSlug/:sourceSlug/chapterlist" element={<ChapterList />} />
                    <Route path="/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber" element={<ChapterReader />} />
                    
                    {/* Home page - redirect to novels */}
                    <Route path="/" element={<Navigate to="/novels" replace />} />
                    
                </Routes>
                {/* <Footer /> */}
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
