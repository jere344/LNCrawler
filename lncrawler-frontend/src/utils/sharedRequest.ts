export interface SharedRequests<T> {
  // Sends the request for `key` unless one is in flight; callers asking meanwhile share its promise.
  // `settle` turns the response into the shared value before the key is free, so a state it stores is there for the next caller.
  run: <R>(key: string, send: () => Promise<R>, settle: (response: R) => T) => Promise<T>;
}

// Requests on their way by key. A key is free again as soon as its request settles, a failure included.
export function createSharedRequests<T>(): SharedRequests<T> {
  const inflight = new Map<string, Promise<T>>();

  return {
    run: (key, send, settle) => {
      const pending = inflight.get(key);
      if (pending) return pending;
      const request = send().then(
        (response) => {
          inflight.delete(key);
          return settle(response);
        },
        (error: unknown) => {
          inflight.delete(key);
          throw error;
        },
      );
      inflight.set(key, request);
      return request;
    },
  };
}
