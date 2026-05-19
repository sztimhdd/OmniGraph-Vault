/* Test infrastructure for kb-v2.2-7 Wave 5 lang.js behavioral tests.
 *
 * Reads JSON params from stdin, executes kb/static/lang.js inside a
 * vm sandbox with mocked window/document/navigator, captures the side
 * effects (cookie writes + html setAttribute calls), and prints them
 * as JSON on stdout.
 *
 * Why this approach:
 *   - No package.json / no jsdom dep (the project is Python-first).
 *   - Node's built-in vm module is enough for IIFE behavioral testing.
 *   - The IIFE's only globals are window/document/navigator + URL +
 *     URLSearchParams — all easy to mock.
 *
 * Param schema (stdin JSON):
 *   - window_kb_default_lang: string | null | undefined
 *   - navigator_languages: string[]    (default ['en-US'])
 *   - initial_cookie: string           (e.g. 'kb_lang=en' or '')
 *   - location_search: string          (e.g. '?lang=en' or '')
 *   - data_fixed_lang_on_html: boolean (sets a stray <html data-fixed-lang="true">
 *                                       to verify the post-Wave 5 guard removal)
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Read params from stdin.
const params = JSON.parse(fs.readFileSync(0, 'utf-8'));

// Capture buffers.
const cookieWrites = [];
const setAttrs = [];
let toggleClickHandler = null;
const eventListeners = [];

// document.documentElement mock.
const htmlElement = {
  _attrs: {},
  setAttribute(k, v) {
    setAttrs.push([k, v]);
    this._attrs[k] = v;
  },
  getAttribute(k) {
    if (k === 'data-fixed-lang' && params.data_fixed_lang_on_html) {
      return 'true';
    }
    return this._attrs[k] || null;
  },
};

// document mock — cookie via getter/setter so writes are observable.
let cookieJar = params.initial_cookie || '';
const documentMock = {
  documentElement: htmlElement,
  querySelector(_sel) {
    // No .lang-toggle in the test sandbox — bindToggle becomes a no-op.
    return null;
  },
  addEventListener(evt, handler) {
    eventListeners.push([evt, handler]);
    // The IIFE registers a DOMContentLoaded listener when readyState is
    // 'loading'. We invoke it synchronously so resolveLang/applyLang
    // run inside the sandbox before we capture state.
    if (evt === 'DOMContentLoaded') {
      handler();
    }
  },
  readyState: params.ready_state || 'complete',
};
Object.defineProperty(documentMock, 'cookie', {
  get() { return cookieJar; },
  set(value) {
    cookieWrites.push(value);
    // Mimic browser semantics: parse out the name=value pair and merge
    // into the jar (overwrite same-name entries).
    const pair = value.split(';')[0].trim();
    const [name] = pair.split('=');
    const existing = cookieJar.split(';')
      .map((p) => p.trim())
      .filter((p) => p && !p.startsWith(name + '='));
    existing.push(pair);
    cookieJar = existing.join('; ');
  },
});

const windowMock = {
  // Only set the property when the param is a string — leaving it
  // undefined exercises the `typeof window.KB_DEFAULT_LANG === 'string'`
  // branch in the IIFE.
  location: {
    search: params.location_search || '',
    href: 'http://localhost/' + (params.location_search || ''),
  },
};
if (typeof params.window_kb_default_lang === 'string') {
  windowMock.KB_DEFAULT_LANG = params.window_kb_default_lang;
}

const navigatorMock = {
  languages: params.navigator_languages || ['en-US'],
  language: (params.navigator_languages || ['en-US'])[0] || 'en-US',
};

// Build sandbox. URL + URLSearchParams come from the host Node so they
// behave per spec (they are V8 built-ins).
const sandbox = {
  window: windowMock,
  document: documentMock,
  navigator: navigatorMock,
  URL,
  URLSearchParams,
  // The IIFE references `window.location.href`; we expose globalThis
  // shape so a bare `window.location.href = ...` assignment is harmless.
};

// Source path resolution: this script lives at tests/unit/kb/_lang_js_runner.js;
// lang.js is at kb/static/lang.js.
const langJsPath = path.resolve(__dirname, '..', '..', '..', 'kb', 'static', 'lang.js');
const code = fs.readFileSync(langJsPath, 'utf-8');

vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: 'lang.js' });

// Final state read-out.
const finalLangAttr = htmlElement._attrs['lang'] || null;
const out = {
  cookie_writes: cookieWrites,
  set_attrs: setAttrs,
  final_lang_attr: finalLangAttr,
  final_cookie: cookieJar,
};
process.stdout.write(JSON.stringify(out));
