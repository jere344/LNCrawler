import { Routes, Route, useLocation, Navigate } from "react-router-dom";
import { CssBaseline, ThemeProvider as MuiThemeProvider } from "@mui/material";
import { useLayoutEffect } from "react";
import "./App.css";
import { ThemeProvider, useTheme } from "@theme/ThemeContext";
import Header from '@components/Header';
import Home from '@components/Home';
import SearchResults from '@components/SearchResults';
import DownloadForm from '@components/DownloadForm';
import DownloadStatus from '@components/DownloadStatus';

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
                    <Route path="/" element={<Home />} />
                    <Route path="/search/:jobId" element={<SearchResults />} />
                    <Route path="/download/:jobId/:sourceIndex/:novelIndex" element={<DownloadForm />} />
                    <Route path="/download/status/:jobId" element={<DownloadStatus />} />
                    
                    {/* Catch all route */}
                    <Route path="*" element={<Navigate to="/" replace />} />
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
