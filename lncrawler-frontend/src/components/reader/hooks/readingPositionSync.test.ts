import { describe, it, expect, vi } from 'vitest';
import {
  POSITION_SAVE_INTERVAL_MS,
  createPositionQueue,
  isScrollKey,
  isScrollable,
  isTypingTarget,
  isUnavailableSave,
  readProgress,
  reportSaveError,
  recordPositionSaved,
  resumeProgressFrom,
  saveStateFor,
  shouldSavePosition,
  withoutResumeProgress,
  type PositionTarget,
} from './readingPositionSync';

const target = (progress: number, chapterNumber = 3): PositionTarget => ({
  novelSlug: 'novel',
  sourceSlug: 'source',
  chapterNumber,
  progress,
});

// A send the test settles by hand
const deferredSend = () => {
  const calls: { target: PositionTarget; settle: (ok: boolean) => void }[] = [];
  const send = vi.fn((t: PositionTarget) => new Promise<unknown>((resolve, reject) => {
    calls.push({ target: t, settle: (ok) => (ok ? resolve(null) : reject(new Error('failed'))) });
  }));
  return { send, calls };
};

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('scroll keys', () => {
  it('counts the keys that scroll the page', () => {
    for (const key of [' ', 'ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End']) {
      expect(isScrollKey(key)).toBe(true);
    }
  });

  it('ignores the keys that only navigate', () => {
    expect(isScrollKey('ArrowLeft')).toBe(false);
    expect(isScrollKey('ArrowRight')).toBe(false);
    expect(isScrollKey('c')).toBe(false);
  });
});

describe('isTypingTarget', () => {
  it('is true for fields', () => {
    expect(isTypingTarget(document.createElement('input'))).toBe(true);
    expect(isTypingTarget(document.createElement('textarea'))).toBe(true);
    expect(isTypingTarget(document.createElement('select'))).toBe(true);
  });

  it('is true for editable text', () => {
    const div = document.createElement('div');
    div.setAttribute('contenteditable', 'true');
    expect(isTypingTarget(div)).toBe(true);
  });

  it('is false for the page and for nothing', () => {
    expect(isTypingTarget(document.body)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
  });
});

describe('save errors', () => {
  it('treats a 409 as the expected no-content answer', () => {
    expect(isUnavailableSave(Object.assign(new Error('x'), { response: { status: 409 } }))).toBe(true);
    expect(isUnavailableSave(Object.assign(new Error('x'), { response: { status: 500 } }))).toBe(false);
    expect(isUnavailableSave(new Error('x'))).toBe(false);
  });

  it('logs every error but a 409', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    reportSaveError(Object.assign(new Error('gap'), { response: { status: 409 } }));
    expect(spy).not.toHaveBeenCalled();
    reportSaveError(new Error('network'));
    expect(spy).toHaveBeenCalledTimes(1);
    spy.mockRestore();
  });
});

describe('isScrollable', () => {
  it('is false for a page no taller than the viewport', () => {
    expect(isScrollable({ scrollHeight: 800, clientHeight: 800 })).toBe(false);
  });

  it('is true for a page taller than the viewport', () => {
    expect(isScrollable({ scrollHeight: 2400, clientHeight: 800 })).toBe(true);
  });
});

describe('readProgress', () => {
  it('is 0 when the chapter is not on the page', () => {
    expect(readProgress(null, 0)).toBe(0);
  });

  it('is 1 for a chapter too short to scroll, which is read in full once shown', () => {
    expect(readProgress({ start: 0, length: 0, height: 700 }, 0)).toBe(1);
    expect(readProgress({ start: 0, length: -100, height: 700 }, 0)).toBe(1);
  });

  it('is the share scrolled through a chapter that scrolls', () => {
    expect(readProgress({ start: 0, length: 1000, height: 1800 }, 250)).toBe(0.25);
  });
});

describe('withoutResumeProgress', () => {
  it('drops the progress and keeps the other state', () => {
    expect(withoutResumeProgress({ resumeProgress: 0.4, keepScroll: true, layers: 'x' }))
      .toEqual({ keepScroll: true, layers: 'x' });
  });

  it('is empty for no state', () => {
    expect(withoutResumeProgress(null)).toEqual({});
  });
});

describe('save pacing', () => {
  const key = 'novel|source|3';

  it('sends the first save of a chapter at once', () => {
    expect(shouldSavePosition(saveStateFor(null, key), 0.1, 1000)).toBe(true);
  });

  it('waits for the interval after a save', () => {
    const sent = recordPositionSaved(saveStateFor(null, key), 0.2, 1000);

    expect(shouldSavePosition(sent, 0.3, 1000 + POSITION_SAVE_INTERVAL_MS - 1)).toBe(false);
    expect(shouldSavePosition(sent, 0.3, 1000 + POSITION_SAVE_INTERVAL_MS)).toBe(true);
  });

  it('sends at once the first time the chapter is finished, within the interval', () => {
    const sent = recordPositionSaved(saveStateFor(null, key), 0.2, 1000);

    expect(shouldSavePosition(sent, 0.96, 1001)).toBe(true);
    const finished = recordPositionSaved(sent, 0.96, 1001);
    expect(shouldSavePosition(finished, 0.99, 1002)).toBe(false);
  });

  it('starts over for another chapter', () => {
    const sent = recordPositionSaved(saveStateFor(null, key), 0.99, 1000);
    const next = saveStateFor(sent, 'novel|source|4');

    expect(next).toEqual({ key: 'novel|source|4', lastSavedAt: null, finished: false });
    expect(shouldSavePosition(next, 0.1, 1001)).toBe(true);
  });
});

describe('resumeProgressFrom', () => {
  it('reads the progress a Continue link passes', () => {
    expect(resumeProgressFrom({ resumeProgress: 0.4 })).toBe(0.4);
  });

  it('keeps zero, which means the top of the chapter', () => {
    expect(resumeProgressFrom({ resumeProgress: 0 })).toBe(0);
  });

  it('is null without a progress in the state', () => {
    expect(resumeProgressFrom(null)).toBeNull();
    expect(resumeProgressFrom('text')).toBeNull();
    expect(resumeProgressFrom({ keepScroll: true })).toBeNull();
    expect(resumeProgressFrom({ resumeProgress: 'half' })).toBeNull();
  });

  it('keeps the progress within 0 and 1', () => {
    expect(resumeProgressFrom({ resumeProgress: 3 })).toBe(1);
    expect(resumeProgressFrom({ resumeProgress: -1 })).toBe(0);
  });
});

describe('position queue', () => {
  it('sends a single payload at once', async () => {
    const { send, calls } = deferredSend();
    const queue = createPositionQueue(send, vi.fn());

    queue.push(target(0.5));

    expect(send).toHaveBeenCalledTimes(1);
    expect(calls[0].target).toEqual(target(0.5));
  });

  it('keeps only the latest payload while one is in flight', async () => {
    const { send, calls } = deferredSend();
    const queue = createPositionQueue(send, vi.fn());

    queue.push(target(0.1));
    queue.push(target(0.2));
    queue.push(target(0.3));
    expect(send).toHaveBeenCalledTimes(1);

    calls[0].settle(true);
    await flush();

    expect(send).toHaveBeenCalledTimes(2);
    expect(calls[1].target.progress).toBe(0.3);
  });

  it('never has two requests in flight', async () => {
    let inFlight = 0;
    let maxInFlight = 0;
    const send = vi.fn(async () => {
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      await flush();
      inFlight--;
    });
    const queue = createPositionQueue(send, vi.fn());

    queue.push(target(0.1));
    queue.push(target(0.2));
    queue.push(target(0.3));
    await flush();
    await flush();

    expect(maxInFlight).toBe(1);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('logs a failed request and still sends the waiting one', async () => {
    const { send, calls } = deferredSend();
    const onError = vi.fn();
    const queue = createPositionQueue(send, onError);

    queue.push(target(0.1));
    queue.push(target(0.2));
    calls[0].settle(false);
    await flush();

    expect(onError).toHaveBeenCalledWith(expect.any(Error));
    expect(send).toHaveBeenCalledTimes(2);
    expect(calls[1].target.progress).toBe(0.2);
  });

  it('drops the waiting payload when asked', async () => {
    const { send, calls } = deferredSend();
    const queue = createPositionQueue(send, vi.fn());

    queue.push(target(0.1));
    queue.push(target(0.2));
    queue.drop();
    calls[0].settle(true);
    await flush();

    expect(send).toHaveBeenCalledTimes(1);
  });
});
