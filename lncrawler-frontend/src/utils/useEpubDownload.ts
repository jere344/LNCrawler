import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNotification } from '@context/NotificationContext';
import { jobService, novelService } from '@services/api';
import { apiErrorMessage } from '@utils/apiError';

const POLL_INTERVAL_MS = 2000;

// Trigger a browser download of a URL without leaving the page.
const triggerDownload = (url: string) => {
  const link = document.createElement('a');
  link.href = url;
  link.download = '';
  document.body.appendChild(link);
  link.click();
  link.remove();
};

// Downloads a source as EPUB. The backend either serves a fresh file right away
// ("ready") or queues a background job ("pending") that we poll until it completes.
// preparingKey is 'full' or the volume number of the build in progress, or null.
export function useEpubDownload(novelSlug: string, sourceSlug: string) {
  const { t } = useTranslation();
  const { notify, update, dismiss } = useNotification();
  const [preparingKey, setPreparingKey] = useState<string | null>(null);

  const activeKeyRef = useRef<string | null>(null);
  // Identifies the build currently being polled, so a late response from an
  // ended build is ignored.
  const runRef = useRef<object | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastRef = useRef<number | null>(null);
  const mountedRef = useRef(false);

  const stopPolling = useCallback(() => {
    runRef.current = null;
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const closeToast = useCallback(() => {
    if (toastRef.current !== null) {
      dismiss(toastRef.current);
      toastRef.current = null;
    }
  }, [dismiss]);

  // Shows the build's state in the toast: opens it on the first call, updates it afterwards.
  const showJob = useCallback(
    (job: { status: string; progress: number; total_items: number; progress_percentage: number }) => {
      const content =
        job.status === 'created'
          ? { message: t('sourceDetail.epubQueued'), progress: 'indeterminate' as const }
          : job.total_items > 0
            ? {
                message: t('sourceDetail.epubProgress', { done: job.progress, total: job.total_items }),
                progress: job.progress_percentage,
              }
            : { message: t('sourceDetail.epubPreparing'), progress: 'indeterminate' as const };
      if (toastRef.current === null) {
        toastRef.current = notify({ ...content, severity: 'info', duration: null });
      } else {
        update(toastRef.current, content);
      }
    },
    [notify, update, t],
  );

  // Reset the in-progress state once a build has ended (success, failure or error).
  const finish = useCallback(() => {
    stopPolling();
    closeToast();
    activeKeyRef.current = null;
    if (mountedRef.current) setPreparingKey(null);
  }, [stopPolling, closeToast]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      stopPolling();
      closeToast();
    };
  }, [stopPolling, closeToast]);

  const startDownload = useCallback(
    async (volume?: number) => {
      // Only one build at a time: ignore clicks while one is still being prepared.
      if (activeKeyRef.current !== null) return;

      const key = volume === undefined ? 'full' : String(volume);
      const url = novelService.getSourceEpubUrl(novelSlug, sourceSlug, volume);
      activeKeyRef.current = key;
      setPreparingKey(key);

      try {
        const result = await novelService.prepareSourceEpub(novelSlug, sourceSlug, volume);
        if (!mountedRef.current) return;

        if (result.status !== 'pending') {
          finish();
          triggerDownload(url);
          return;
        }

        const jobId = String(result.job.id);
        showJob(result.job);

        // Poll with chained timeouts so requests never overlap.
        const run = {};
        runRef.current = run;
        const poll = async () => {
          let job;
          try {
            job = (await jobService.getJobDetails(jobId))?.job;
          } catch (err) {
            if (runRef.current !== run) return;
            if ((err as { response?: { status?: number } })?.response?.status === 404) {
              // The job is gone; it will never report a final state.
              finish();
              notify({ message: t('sourceDetail.epubFailed'), severity: 'error' });
              return;
            }
            // Transient network error: keep polling until the job reports a final state.
          }
          if (runRef.current !== run) return;

          if (job?.status === 'download_completed') {
            finish();
            triggerDownload(url);
          } else if (job?.status === 'failed') {
            finish();
            notify({
              message: job.error_message || t('sourceDetail.epubFailed'),
              severity: 'error',
            });
          } else {
            if (job) showJob(job);
            timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
          }
        };
        timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
      } catch (err) {
        finish();
        notify({
          message: apiErrorMessage(err) ?? t('sourceDetail.epubFailed'),
          severity: 'error',
        });
      }
    },
    [novelSlug, sourceSlug, notify, showJob, t, finish],
  );

  return { startDownload, preparingKey };
}
