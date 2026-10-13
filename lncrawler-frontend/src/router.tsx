import { createBrowserRouter, Outlet, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import App from './App';
import RouteSpinner from '@components/common/RouteSpinner';
import RouteError from '@components/common/RouteError';
import NotFoundRedirect from '@components/common/NotFoundRedirect';
import HomeSkeleton from '@components/home/HomeSkeleton';
import {
    homeLoader,
    novelRedirectLoader,
    chatLoader,
    readingListsLoader,
    readingListDetailLoader,
    chapterListLoader,
    galleryLoader,
    searchLoader,
} from './router/loaders';

// Route-level code splitting: each page (and everything it alone imports, e.g.
// the reader or mdxeditor) is fetched on navigation instead of on first paint.
const DownloaderHome = lazy(() => import('@components/downloader/DownloaderHome'));
const SearchResults = lazy(() => import('@components/downloader/SearchResults'));
const DownloadForm = lazy(() => import('@components/downloader/DownloadForm'));
const DownloadStatus = lazy(() => import('@components/downloader/DownloadStatus'));
const RunningJobsPage = lazy(() => import('@components/downloader/RunningJobsPage'));
const NovelRedirect = lazy(() => import('@components/novels/NovelRedirect'));
const SourceDetail = lazy(() => import('@components/novels/SourceDetail'));
const ChapterList = lazy(() => import('@components/novels/ChapterList'));
const ChapterReader = lazy(() => import('@components/reader/ChapterReader'));
const SearchPage = lazy(() => import('@components/search/SearchPage'));
const HomePage = lazy(() => import('@components/home/HomePage'));
const LoginPage = lazy(() => import('@components/auth/LoginPage'));
const RegisterPage = lazy(() => import('@components/auth/RegisterPage'));
const SettingsPage = lazy(() => import('@components/auth/SettingsPage'));
const PublicProfilePage = lazy(() => import('@components/profile/PublicProfilePage'));
const ResetPasswordPage = lazy(() => import('@components/auth/ResetPasswordPage'));
const LibraryPage = lazy(() => import('@components/library/LibraryPage'));
const ReadingHistoryPage = lazy(() => import('@components/history/ReadingHistoryPage'));
const ImageGallery = lazy(() => import('@components/novels/ImageGallery'));
const ChatPage = lazy(() => import('@components/chat/ChatPage'));
const ReadingListsPage = lazy(() => import('@components/readinglist/ReadingListsPage'));
const ReadingListDetail = lazy(() => import('@components/readinglist/ReadingListDetail'));
const NovelUpdatesImportPage = lazy(() => import('@components/import/NovelUpdatesImportPage'));

// Pathless layout: keeps App's chrome (Header/Footer) while the deepest matched
// route's loader is still pending, swapping only the Outlet for the fallback.
const Layout = () => <Outlet />;

export const router = createBrowserRouter([
    {
        element: <App />,
        children: [
            {
                element: <Layout />,
                HydrateFallback: RouteSpinner,
                children: [
                    // Authentication routes
                    { path: '/login', element: <LoginPage />, errorElement: <RouteError /> },
                    { path: '/register', element: <RegisterPage />, errorElement: <RouteError /> },
                    { path: '/settings', element: <SettingsPage /> },
                    { path: '/u/:username', element: <PublicProfilePage /> },
                    { path: '/reset-password', element: <ResetPasswordPage /> },

                    // Library and History routes
                    { path: '/library', element: <LibraryPage /> },
                    { path: '/history', element: <ReadingHistoryPage /> },

                    // Loader routes hand back an un-awaited promise (see AsyncData
                    // in router/loaders.ts): navigation commits instantly and this
                    // Suspense boundary shows the fallback until the request lands.
                    // Reading Lists routes
                    { path: '/reading-lists', element: <Suspense fallback={<RouteSpinner />}><ReadingListsPage /></Suspense>, loader: readingListsLoader, errorElement: <RouteError /> },
                    { path: '/reading-lists/:listId', element: <Suspense fallback={<RouteSpinner />}><ReadingListDetail /></Suspense>, loader: readingListDetailLoader, errorElement: <RouteError /> },

                    // Import route
                    { path: '/import', element: <NovelUpdatesImportPage /> },

                    // Chat route
                    { path: '/chat', element: <Suspense fallback={<RouteSpinner />}><ChatPage /></Suspense>, loader: chatLoader, errorElement: <RouteError /> },
                    // Legacy board URLs
                    { path: '/boards', element: <Navigate to="/chat" replace /> },
                    { path: '/boards/:boardSlug', element: <Navigate to="/chat" replace /> },

                    // Downloader routes
                    { path: '/download', element: <DownloaderHome /> },
                    { path: '/download/jobs', element: <RunningJobsPage /> },
                    { path: '/download/search/:jobId', element: <SearchResults /> },
                    { path: '/download/:jobId/:novelIndex/:sourceIndex', element: <DownloadForm /> },
                    { path: '/download/status/:jobId', element: <DownloadStatus /> },

                    // Novel reading routes with new URL structure
                    { path: '/novels/search', element: <Suspense fallback={<RouteSpinner />}><SearchPage /></Suspense>, loader: searchLoader, errorElement: <RouteError /> },
                    { path: '/novels/:novelSlug', element: <NovelRedirect />, loader: novelRedirectLoader, errorElement: <RouteError /> },
                    { path: '/novels/:novelSlug/:sourceSlug', element: <SourceDetail /> },
                    { path: '/novels/:novelSlug/:sourceSlug/chapterlist', element: <Suspense fallback={<RouteSpinner />}><ChapterList /></Suspense>, loader: chapterListLoader, errorElement: <RouteError /> },
                    { path: '/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber', element: <ChapterReader /> },
                    { path: '/novels/:novelSlug/:sourceSlug/gallery', element: <Suspense fallback={<RouteSpinner />}><ImageGallery /></Suspense>, loader: galleryLoader, errorElement: <RouteError /> },

                    // Home page: the loader returns an un-awaited promise so navigation
                    // commits instantly; Suspense shows the skeleton until it resolves
                    // (HydrateFallback covers the cold-load initialize tick).
                    { path: '/', element: <Suspense fallback={<HomeSkeleton />}><HomePage /></Suspense>, loader: homeLoader, HydrateFallback: HomeSkeleton, errorElement: <RouteError /> },

                    // Fallback route - redirect to home
                    { path: '*', element: <NotFoundRedirect /> },
                ],
            },
        ],
    },
]);
