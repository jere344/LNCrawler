import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from './api';
import { API_BASE_URL } from './config';

// api.ts sends a CSRF fetch on import, so the stub is installed before the module loads
const { fetchMock } = vi.hoisted(() => {
  const fetchMock = vi.fn<typeof fetch>(async () => new Response('{}', { status: 200, headers: { 'content-type': 'application/json' } }));
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return { fetchMock };
});

const lastUrl = () => {
  const calls = fetchMock.mock.calls;
  return String(calls[calls.length - 1][0]);
};

describe('api params', () => {
  beforeEach(() => {
    fetchMock.mockClear();
  });

  it('repeats the key for each array item', async () => {
    await api.get('/items/', { params: { tag: ['a b', 'c'] } });
    expect(lastUrl()).toBe(`${API_BASE_URL}/items/?tag=a+b&tag=c`);
  });

  it('skips undefined and null values', async () => {
    await api.get('/items/', { params: { page: 2, q: undefined, sort: null } });
    expect(lastUrl()).toBe(`${API_BASE_URL}/items/?page=2`);
  });

  it('keeps empty strings, 0 and false', async () => {
    await api.get('/items/', { params: { q: '', page: 0, listening: false } });
    expect(lastUrl()).toBe(`${API_BASE_URL}/items/?q=&page=0&listening=false`);
  });

  it('adds no query string when an array is empty or every value is skipped', async () => {
    await api.get('/items/', { params: { tag: [], q: undefined } });
    expect(lastUrl()).toBe(`${API_BASE_URL}/items/`);
  });

  it('appends to a url that already has a query', async () => {
    await api.get('/items/?x=1', { params: { tag: ['a', 'b'] } });
    expect(lastUrl()).toBe(`${API_BASE_URL}/items/?x=1&tag=a&tag=b`);
  });
});
