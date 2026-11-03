import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useFullscreen } from './useFullscreen';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

type Hook = ReturnType<typeof useFullscreen>;

let roots: Root[] = [];
let standalone = false;
let fullscreenEl: Element | null = null;
let webkitFullscreenEl: Element | null = null;

// Renders the hook into a probe component and returns a getter for its latest value
const mount = (): (() => Hook) => {
  const latest: { current: Hook | null } = { current: null };
  const Probe = () => {
    latest.current = useFullscreen();
    return null;
  };
  const root = createRoot(document.createElement('div'));
  roots.push(root);
  act(() => root.render(createElement(Probe)));
  return () => latest.current as Hook;
};

const stubRequest = (name: 'requestFullscreen' | 'webkitRequestFullscreen', impl: () => unknown) =>
  Object.defineProperty(document.documentElement, name, { configurable: true, value: impl });

beforeEach(() => {
  standalone = false;
  fullscreenEl = null;
  webkitFullscreenEl = null;
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    value: (query: string) => ({ matches: query.includes('standalone') && standalone }),
  });
  Object.defineProperty(document, 'fullscreenElement', { configurable: true, get: () => fullscreenEl });
  Object.defineProperty(document, 'webkitFullscreenElement', { configurable: true, get: () => webkitFullscreenEl });
});

afterEach(() => {
  roots.forEach((root) => act(() => root.unmount()));
  roots = [];
  Reflect.deleteProperty(window, 'matchMedia');
  Reflect.deleteProperty(document, 'fullscreenElement');
  Reflect.deleteProperty(document, 'webkitFullscreenElement');
  Reflect.deleteProperty(document, 'exitFullscreen');
  Reflect.deleteProperty(document, 'webkitExitFullscreen');
  Reflect.deleteProperty(document.documentElement, 'requestFullscreen');
  Reflect.deleteProperty(document.documentElement, 'webkitRequestFullscreen');
});

describe('useFullscreen', () => {
  it('is not supported where the browser has no fullscreen API, and toggling does nothing', () => {
    const hook = mount();
    expect(hook().supported).toBe(false);
    expect(() => act(() => hook().toggle())).not.toThrow();
    expect(hook().active).toBe(false);
  });

  it('is supported when the page can request fullscreen', () => {
    stubRequest('requestFullscreen', () => Promise.resolve());
    expect(mount()().supported).toBe(true);
  });

  it('is not supported in an installed web app, even with the API', () => {
    stubRequest('requestFullscreen', () => Promise.resolve());
    standalone = true;
    expect(mount()().supported).toBe(false);
  });

  it('requests fullscreen on the page root, and reports it through fullscreenchange', () => {
    const request = vi.fn(() => {
      fullscreenEl = document.documentElement;
      return Promise.resolve();
    });
    stubRequest('requestFullscreen', request);
    const hook = mount();

    act(() => hook().toggle());
    expect(request).toHaveBeenCalledTimes(1);
    act(() => document.dispatchEvent(new Event('fullscreenchange')));
    expect(hook().active).toBe(true);
  });

  it('leaves fullscreen when it is already active', () => {
    stubRequest('requestFullscreen', () => Promise.resolve());
    fullscreenEl = document.documentElement;
    const exit = vi.fn(() => {
      fullscreenEl = null;
      return Promise.resolve();
    });
    Object.defineProperty(document, 'exitFullscreen', { configurable: true, value: exit });
    const hook = mount();
    expect(hook().active).toBe(true);

    act(() => hook().toggle());
    expect(exit).toHaveBeenCalledTimes(1);
    act(() => document.dispatchEvent(new Event('fullscreenchange')));
    expect(hook().active).toBe(false);
  });

  it('uses the WebKit names and events when the standard ones are missing', () => {
    const request = vi.fn(() => {
      webkitFullscreenEl = document.documentElement;
    });
    stubRequest('webkitRequestFullscreen', request);
    const hook = mount();
    expect(hook().supported).toBe(true);

    act(() => hook().toggle());
    expect(request).toHaveBeenCalledTimes(1);
    act(() => document.dispatchEvent(new Event('webkitfullscreenchange')));
    expect(hook().active).toBe(true);
  });

  it('ignores a request the browser refuses, and keeps the state as it was', async () => {
    stubRequest('requestFullscreen', () => Promise.reject(new Error('denied')));
    const hook = mount();

    await act(async () => {
      hook().toggle();
    });
    expect(hook().active).toBe(false);
  });
});
