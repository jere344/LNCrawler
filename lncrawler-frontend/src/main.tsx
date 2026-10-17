import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { router } from './router'
import { AuthProvider } from './context/AuthContext'
import { AdultContentProvider } from './context/AdultContentContext'
import { LanguageProvider } from './context/LanguageContext'
import { i18nReady } from './i18n'
import { reportError } from './services/errorReporter'

// Catch errors React's error boundary cannot: async rejects and non-render throws.
window.addEventListener('error', (event) => {
  reportError(event.error ?? event.message, { context: 'window.onerror' })
})
window.addEventListener('unhandledrejection', (event) => {
  reportError(event.reason, { context: 'unhandledrejection' })
})

// Wait for the initial locale chunk so the first paint isn't raw translation keys.
i18nReady.finally(() => {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <AuthProvider>
        <AdultContentProvider>
          <LanguageProvider>
            <RouterProvider router={router} />
          </LanguageProvider>
        </AdultContentProvider>
      </AuthProvider>
    </StrictMode>,
  )
})

// Register the service worker (installability only, see public/sw.js).
window.addEventListener('load', () => {
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(() => {})
  }
})
