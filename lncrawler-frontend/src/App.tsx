import { Routes, Route, useLocation } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider } from "@mui/material";
import { useLayoutEffect } from "react";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import Header from '@components/Header';
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
                    <Route path="/novels/search" element={<SearchPage />} />
                    <Route path="/novels/:novelSlug" element={<NovelDetail />} />
                    <Route path="/novels/:novelSlug/:sourceSlug" element={<SourceDetail />} />
                    <Route path="/novels/:novelSlug/:sourceSlug/chapterlist" element={<ChapterList />} />
                    <Route path="/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber" element={<ChapterReader />} />
                    
                    {/* Home page */}
                    <Route path="/" element={<HomePage />} />
                    
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
