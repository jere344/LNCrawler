import { createBrowserRouter, Outlet, Navigate } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import App from './App';
import RouteSpinner from '@components/common/RouteSpinner';
import RouteError from '@components/common/RouteError';
import NotFoundRedirect from '@components/common/NotFoundRedirect';
import PageBoundary from '@components/common/PageBoundary';
import HomeSkeleton from '@components/home/HomeSkeleton';
import ReadingListsSkeleton from '@components/readinglist/ReadingListsSkeleton';
import ReadingListDetailSkeleton from '@components/readinglist/ReadingListDetailSkeleton';
import ChatSkeleton from '@components/chat/ChatSkeleton';
import SearchSkeleton from '@components/search/SearchSkeleton';
import ChapterListSkeleton from '@components/novels/ChapterListSkeleton';
import ImageGallerySkeleton from '@components/novels/ImageGallerySkeleton';
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

// Each page gets its own PageBoundary (keyed by pathname) so the fallback shows
// the instant navigation commits, instead of the previous page staying on screen
// until the lazy chunk or the data arrives. Pages with a loader pass their skeleton.
const S = (Page: React.LazyExoticComponent<React.ComponentType>) =>
    <PageBoundary fallback={<RouteSpinner />}><Page /></PageBoundary>;

export const router = createBrowserRouter([
    {
        element: <App />,
        children: [
            {
                element: <Layout />,
                HydrateFallback: RouteSpinner,
                children: [
                    // Authentication routes
                    { path: '/login', element: S(LoginPage), errorElement: <RouteError /> },
                    { path: '/register', element: S(RegisterPage), errorElement: <RouteError /> },
                    { path: '/settings', element: S(SettingsPage) },
                    { path: '/u/:username', element: S(PublicProfilePage) },
                    { path: '/reset-password', element: S(ResetPasswordPage) },

                    // Library and History routes
                    { path: '/library', element: S(LibraryPage) },
                    { path: '/history', element: S(ReadingHistoryPage) },

                    // Loader routes hand back an un-awaited promise (see AsyncData
                    // in router/loaders.ts): navigation commits instantly and the
                    // page's skeleton shows until the request lands. The skeleton is
                    // also the cold-load HydrateFallback.
                    // Reading Lists routes
                    { path: '/reading-lists', element: <PageBoundary fallback={<ReadingListsSkeleton />}><ReadingListsPage /></PageBoundary>, loader: readingListsLoader, HydrateFallback: ReadingListsSkeleton, errorElement: <RouteError /> },
                    { path: '/reading-lists/:listId', element: <PageBoundary fallback={<ReadingListDetailSkeleton />}><ReadingListDetail /></PageBoundary>, loader: readingListDetailLoader, HydrateFallback: ReadingListDetailSkeleton, errorElement: <RouteError /> },

                    // Import route
                    { path: '/import', element: S(NovelUpdatesImportPage) },

                    // Chat route
                    { path: '/chat', element: <PageBoundary fallback={<ChatSkeleton />}><ChatPage /></PageBoundary>, loader: chatLoader, HydrateFallback: ChatSkeleton, errorElement: <RouteError /> },
                    // Legacy board URLs
                    { path: '/boards', element: <Navigate to="/chat" replace /> },
                    { path: '/boards/:boardSlug', element: <Navigate to="/chat" replace /> },

                    // Downloader routes
                    { path: '/download', element: S(DownloaderHome) },
                    { path: '/download/jobs', element: S(RunningJobsPage) },
                    { path: '/download/search/:jobId', element: S(SearchResults) },
                    { path: '/download/:jobId/:novelIndex/:sourceIndex', element: S(DownloadForm) },
                    { path: '/download/status/:jobId', element: S(DownloadStatus) },

                    // Novel reading routes with new URL structure
                    { path: '/novels/search', element: <PageBoundary fallback={<SearchSkeleton />}><SearchPage /></PageBoundary>, loader: searchLoader, HydrateFallback: SearchSkeleton, errorElement: <RouteError /> },
                    { path: '/novels/:novelSlug', element: <PageBoundary fallback={<RouteSpinner />}><NovelRedirect /></PageBoundary>, loader: novelRedirectLoader, HydrateFallback: RouteSpinner, errorElement: <RouteError /> },
                    { path: '/novels/:novelSlug/:sourceSlug', element: S(SourceDetail) },
                    { path: '/novels/:novelSlug/:sourceSlug/chapterlist', element: <PageBoundary fallback={<ChapterListSkeleton />}><ChapterList /></PageBoundary>, loader: chapterListLoader, HydrateFallback: ChapterListSkeleton, errorElement: <RouteError /> },
                    // The reader keeps a plain Suspense: it stays mounted across chapter
                    // changes (it preloads the next chapter) instead of remounting.
                    { path: '/novels/:novelSlug/:sourceSlug/chapter/:chapterNumber', element: <Suspense fallback={<RouteSpinner />}><ChapterReader /></Suspense> },
                    { path: '/novels/:novelSlug/:sourceSlug/gallery', element: <PageBoundary fallback={<ImageGallerySkeleton />}><ImageGallery /></PageBoundary>, loader: galleryLoader, HydrateFallback: ImageGallerySkeleton, errorElement: <RouteError /> },

                    // Home page: the loader returns an un-awaited promise so navigation
                    // commits instantly; the PageBoundary shows the skeleton until it
                    // resolves (HydrateFallback covers the cold-load initialize tick).
                    { path: '/', element: <PageBoundary fallback={<HomeSkeleton />}><HomePage /></PageBoundary>, loader: homeLoader, HydrateFallback: HomeSkeleton, errorElement: <RouteError /> },

                    // Fallback route - redirect to home
                    { path: '*', element: <NotFoundRedirect /> },
                ],
            },
        ],
    },
]);
