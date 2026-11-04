import { describe, it, expect } from 'vitest';
import {
  CLOSED_LAYERS,
  addComposing,
  addPage,
  addSearch,
  addThread,
  openLayer,
  pageStack,
  readLayers,
  replaceBelowSearch,
  replacePages,
  writeLayers,
} from './readerLayers';

describe('readLayers', () => {
  it('reads closed when the state is missing or not an object', () => {
    expect(readLayers(null)).toEqual(CLOSED_LAYERS);
    expect(readLayers(undefined)).toEqual(CLOSED_LAYERS);
    expect(readLayers('readerLayers')).toEqual(CLOSED_LAYERS);
    expect(readLayers([1, 2])).toEqual(CLOSED_LAYERS);
    expect(readLayers({})).toEqual(CLOSED_LAYERS);
  });

  it('reads closed for malformed layers without throwing', () => {
    expect(readLayers({ readerLayers: 'settings' })).toEqual(CLOSED_LAYERS);
    expect(readLayers({ readerLayers: { panel: 'unknown', depth: 1 } })).toEqual(CLOSED_LAYERS);
    expect(readLayers({ readerLayers: { panel: 'display', depth: 0 } })).toEqual(CLOSED_LAYERS);
    expect(readLayers({ readerLayers: { panel: 'display', depth: 1.5 } })).toEqual(CLOSED_LAYERS);
    expect(readLayers({ readerLayers: { panel: 'display', depth: '1' } })).toEqual(CLOSED_LAYERS);
    expect(readLayers({ readerLayers: { panel: 'none', depth: 1 } })).toEqual(CLOSED_LAYERS);
  });

  it('drops settings page ids it does not know', () => {
    const state = { readerLayers: { panel: 'settings', pages: ['listen', 'nope', 42, 'voice'], depth: 3 } };

    expect(readLayers(state).pages).toEqual(['listen', 'voice']);
  });

  it('drops thread ids that are not non-empty strings', () => {
    const state = { readerLayers: { panel: 'comments', threads: ['a', '', 42, null, 'b'], depth: 2 } };

    expect(readLayers(state).threads).toEqual(['a', 'b']);
    expect(readLayers({ readerLayers: { panel: 'comments', threads: 'a', depth: 1 } }).threads).toEqual([]);
  });

  it('returns the same threads array while the saved ids are unchanged', () => {
    const state = { readerLayers: { panel: 'comments', threads: ['a', 'b'], depth: 2 } };
    const first = readLayers(state).threads;

    expect(readLayers({ readerLayers: { panel: 'comments', threads: ['a', 'b'], depth: 2 } }).threads).toBe(first);
    expect(readLayers({ readerLayers: { panel: 'comments', threads: ['a', 'c'], depth: 2 } }).threads).not.toBe(first);
  });

  it('reads the composer as open only when it is saved as true', () => {
    expect(readLayers({ readerLayers: { panel: 'comments', composing: 'yes', depth: 1 } }).composing).toBe(false);
    expect(readLayers({ readerLayers: { panel: 'comments', composing: true, depth: 1 } }).composing).toBe(true);
  });

  it('drops the thread views and the composer of any other panel', () => {
    const state = { readerLayers: { panel: 'display', threads: ['a'], composing: true, depth: 1 } };

    expect(readLayers(state)).toEqual({ panel: 'display', pages: [], searching: false, threads: [], composing: false, depth: 1 });
  });

  it('defaults the optional fields of a saved panel', () => {
    expect(readLayers({ readerLayers: { panel: 'display', depth: 1 } })).toEqual({
      panel: 'display',
      pages: [],
      searching: false,
      threads: [],
      composing: false,
      depth: 1,
    });
  });
});

describe('writeLayers', () => {
  it('keeps the other keys of the state', () => {
    const written = writeLayers({ keepScroll: true, other: 'x' }, openLayer(CLOSED_LAYERS, 'display'));

    expect(written).toEqual({
      keepScroll: true,
      other: 'x',
      readerLayers: { panel: 'display', pages: [], searching: false, threads: [], composing: false, depth: 1 },
    });
  });

  it('round-trips through readLayers', () => {
    const layers = addSearch(addPage(openLayer(CLOSED_LAYERS, 'settings'), 'listen'));

    expect(readLayers(writeLayers(null, layers))).toEqual(layers);
  });
});

describe('transitions', () => {
  it('the chapter list is a panel of its own, one entry above the base', () => {
    const chapters = openLayer(CLOSED_LAYERS, 'chapters');
    expect(chapters).toEqual({ panel: 'chapters', pages: [], searching: false, threads: [], composing: false, depth: 1 });
    expect(readLayers(writeLayers(null, chapters))).toEqual(chapters);
  });

  it('the comments panel is a panel of its own, one entry above the base', () => {
    const comments = openLayer(CLOSED_LAYERS, 'comments');
    expect(comments).toEqual({ panel: 'comments', pages: [], searching: false, threads: [], composing: false, depth: 1 });
    expect(readLayers(writeLayers(null, comments))).toEqual(comments);
  });

  it('opening a panel adds one entry above the base', () => {
    const display = openLayer(CLOSED_LAYERS, 'display');
    const customize = openLayer(display, 'customize', ['custom']);

    expect(display.depth).toBe(1);
    expect(customize).toEqual({ panel: 'customize', pages: ['custom'], searching: false, threads: [], composing: false, depth: 2 });
  });

  it('pushing a page adds one entry and keeps the order', () => {
    const home = openLayer(CLOSED_LAYERS, 'settings');
    const listen = addPage(home, 'listen');
    const voice = addPage(listen, 'backup');

    expect(listen.pages).toEqual(['listen']);
    expect(voice.pages).toEqual(['listen', 'backup']);
    expect(voice.depth).toBe(3);
  });

  it('the first search adds one entry', () => {
    const home = openLayer(CLOSED_LAYERS, 'settings');

    expect(addSearch(home)).toEqual({ panel: 'settings', pages: [], searching: true, threads: [], composing: false, depth: 2 });
  });

  it('opening a thread view adds one entry, keeps the order and closes the composer', () => {
    const comments = openLayer(CLOSED_LAYERS, 'comments');
    const first = addThread(comments, 'c1');
    const second = addThread(first, 'c2');
    const composing = addComposing(comments);

    expect(first).toEqual({ panel: 'comments', pages: [], searching: false, threads: ['c1'], composing: false, depth: 2 });
    expect(second.threads).toEqual(['c1', 'c2']);
    expect(second.depth).toBe(3);
    expect(addThread(composing, 'c1')).toEqual({ ...composing, threads: ['c1'], composing: false, depth: 3 });
  });

  it('opening the composer adds one entry above the threads', () => {
    const composing = addComposing(addThread(openLayer(CLOSED_LAYERS, 'comments'), 'c1'));

    expect(composing).toEqual({ panel: 'comments', pages: [], searching: false, threads: ['c1'], composing: true, depth: 3 });
  });

  it('round-trips thread views and the composer through writeLayers', () => {
    const layers = addComposing(addThread(openLayer(CLOSED_LAYERS, 'comments'), 'c1'));

    expect(readLayers(writeLayers(null, layers))).toEqual(layers);
  });

  it('showing a page in place of the current entry keeps the depth and ends the search', () => {
    const searching = addSearch(addPage(openLayer(CLOSED_LAYERS, 'settings'), 'listen'));

    expect(replacePages(searching, 'text')).toEqual({ panel: 'settings', pages: ['text'], searching: false, threads: [], composing: false, depth: 3 });
    expect(replacePages(searching, null)).toEqual({ panel: 'settings', pages: [], searching: false, threads: [], composing: false, depth: 3 });
  });

  it('a result chosen from a search replaces the entry below it and drops the search entry', () => {
    // Desktop: the settings entry (depth 1) is searched over, so the result replaces it and Back closes
    const searching = addSearch(openLayer(CLOSED_LAYERS, 'settings'));
    const chosen = replaceBelowSearch(searching, 'listen');

    expect(chosen).toEqual({ panel: 'settings', pages: ['listen'], searching: false, threads: [], composing: false, depth: 1 });
    expect(replaceBelowSearch(searching, 'voice')).toEqual({ panel: 'settings', pages: ['listen', 'voice'], searching: false, threads: [], composing: false, depth: 1 });
  });

  it('a result chosen from a search over a pushed page replaces that page entry, one level up', () => {
    const searching = addSearch(addPage(openLayer(CLOSED_LAYERS, 'settings'), 'listen'));

    expect(replaceBelowSearch(searching, 'text')).toEqual({ panel: 'settings', pages: ['text'], searching: false, threads: [], composing: false, depth: 2 });
  });

  it('a subpage stacks over its parent page', () => {
    expect(pageStack('voice')).toEqual(['listen', 'voice']);
    expect(pageStack('listen')).toEqual(['listen']);
  });

  it('showing the voice subpage from a search keeps listen beneath it', () => {
    const searching = addSearch(openLayer(CLOSED_LAYERS, 'settings'));

    expect(replacePages(searching, 'voice')).toEqual({ panel: 'settings', pages: ['listen', 'voice'], searching: false, threads: [], composing: false, depth: 2 });
  });

  it('pushing the voice subpage from listen adds one entry above listen', () => {
    const onListen = addPage(openLayer(CLOSED_LAYERS, 'settings'), 'listen');

    expect(addPage(onListen, 'voice')).toEqual({ panel: 'settings', pages: ['listen', 'voice'], searching: false, threads: [], composing: false, depth: 3 });
  });
});
