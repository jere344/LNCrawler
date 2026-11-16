import { describe, expect, it } from 'vitest';
import { entryKey } from './useScrollRestoration';

describe('entryKey', () => {
  it('tells apart two pages whose first entry shares the "default" key', () => {
    const first = entryKey({ key: 'default', pathname: '/novels', search: '' });
    const second = entryKey({ key: 'default', pathname: '/chat', search: '' });
    expect(first).not.toBe(second);
  });

  it('gives the same key for the same entry and path', () => {
    const a = entryKey({ key: 'abc123', pathname: '/novel/1', search: '?page=2' });
    const b = entryKey({ key: 'abc123', pathname: '/novel/1', search: '?page=2' });
    expect(a).toBe(b);
  });
});
