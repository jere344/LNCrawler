import { Suspense, type ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Suspense boundary around a route's page. Keyed by pathname so that every
 * navigation to another page mounts a fresh boundary, and its fallback (the
 * page's skeleton) shows while the page or its loader data is pending.
 *
 * A boundary that is reused across routes and already shows content keeps that
 * content on screen during a transition, which is how the previous page used to
 * stay visible for the whole fetch.
 */
const PageBoundary = ({ fallback, children }: { fallback: ReactNode; children: ReactNode }) => {
  const { pathname } = useLocation();
  return <Suspense key={pathname} fallback={fallback}>{children}</Suspense>;
};

export default PageBoundary;
