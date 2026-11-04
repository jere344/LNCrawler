import { describe, expect, it, vi } from 'vitest';
import { createSharedRequests } from './sharedRequest';

// A request the test settles by hand
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
};

describe('createSharedRequests', () => {
  it('sends once for concurrent callers of a key and shares the promise', async () => {
    const shared = createSharedRequests<string>();
    const send = vi.fn(async () => 'data');
    const [a, b] = await Promise.all([
      shared.run('k', send, (value) => value),
      shared.run('k', send, (value) => value),
    ]);
    expect(a).toBe('data');
    expect(b).toBe('data');
    expect(send).toHaveBeenCalledTimes(1);
  });

  it('shares the promise itself while the request is in flight', () => {
    const shared = createSharedRequests<string>();
    const first = shared.run('k', () => new Promise<string>(() => {}), (value) => value);
    const second = shared.run('k', vi.fn(async () => 'other'), (value) => value);
    expect(second).toBe(first);
  });

  it('runs settle on the response before the callers get the value', async () => {
    const shared = createSharedRequests<number>();
    const stored: string[] = [];
    const value = await shared.run(
      'k',
      async () => 'raw',
      (response) => {
        stored.push(response);
        return stored.length;
      },
    );
    expect(stored).toEqual(['raw']);
    expect(value).toBe(1);
  });

  it('frees the key once the request settles, so the next call sends again', async () => {
    const shared = createSharedRequests<string>();
    const send = vi.fn(async () => 'data');
    await shared.run('k', send, (value) => value);
    await shared.run('k', send, (value) => value);
    expect(send).toHaveBeenCalledTimes(2);
  });

  it('rethrows a failure to every caller and frees the key', async () => {
    const shared = createSharedRequests<string>();
    const failing = deferred<string>();
    const settle = vi.fn((value: string) => value);
    const first = shared.run('k', () => failing.promise, settle);
    const second = shared.run('k', vi.fn(async () => 'never'), settle);
    failing.reject(new Error('offline'));

    await expect(first).rejects.toThrow('offline');
    await expect(second).rejects.toThrow('offline');
    expect(settle).not.toHaveBeenCalled();

    const retry = vi.fn(async () => 'back');
    await expect(shared.run('k', retry, (value) => value)).resolves.toBe('back');
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('keeps keys apart', async () => {
    const shared = createSharedRequests<string>();
    const send = vi.fn(async () => 'data');
    await Promise.all([
      shared.run('a', send, (value) => value),
      shared.run('b', send, (value) => value),
    ]);
    expect(send).toHaveBeenCalledTimes(2);
  });
});
