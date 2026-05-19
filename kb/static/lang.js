/* I18N-01/02/08: Bilingual chrome switcher.
 *
 * Resolution order:
 *   1. ?lang=zh|en|zh-CN query param (hard switch — sets cookie).
 *   2. kb_lang cookie (persisted choice — user preference always wins
 *      once set; window.KB_DEFAULT_LANG is ignored).
 *   3. navigator.languages (Accept-Language equivalent) — persisted to
 *      cookie on first visit so the choice is sticky from then on
 *      (kb-v2.2-7 first-visit cookie persistence).
 *   4. fallback: window.KB_DEFAULT_LANG (deployment env var injected by
 *      base.html, validated against SUPPORTED), then 'zh-CN'.
 *
 * Always sets <html lang> on apply — kb-v2.2-7 (locked decision A1) deletes
 * the article-detail content-fixed special case. Site language IS reading
 * language; the toggle button preserves user override.
 *
 * Toggle button (.lang-toggle): cycles zh ↔ en, sets cookie, reloads.
 *
 * ES5-compatible (no arrow functions, no let/const) for older WeChat
 * in-app browser support. No bundler, no minification, no build step.
 */
(function () {
  'use strict';

  var SUPPORTED = ['zh-CN', 'en'];
  var COOKIE_NAME = 'kb_lang';
  var COOKIE_MAX_AGE = 31536000; // 1 year

  // kb-v2.2-7 (A9): per-deployment default lang from window.KB_DEFAULT_LANG
  // (set by base.html from KB_DEFAULT_LANG env var). Validated against
  // SUPPORTED — invalid / missing values fall back to 'zh-CN' so an operator
  // typo (e.g. KB_DEFAULT_LANG=fr) does not silently break rendering.
  var DEFAULT_LANG = (typeof window !== 'undefined'
    && typeof window.KB_DEFAULT_LANG === 'string'
    && SUPPORTED.indexOf(window.KB_DEFAULT_LANG) !== -1)
    ? window.KB_DEFAULT_LANG : 'zh-CN';

  function readCookie(name) {
    var pairs = document.cookie.split(';');
    for (var i = 0; i < pairs.length; i++) {
      var p = pairs[i].trim();
      if (p.indexOf(name + '=') === 0) return p.substring(name.length + 1);
    }
    return null;
  }

  function writeCookie(name, value) {
    document.cookie = name + '=' + value
      + '; path=/; max-age=' + COOKIE_MAX_AGE
      + '; SameSite=Lax';
  }

  function readQueryLang() {
    var params = new URLSearchParams(window.location.search);
    var q = params.get('lang');
    if (!q) return null;
    if (q === 'zh' || q === 'zh-CN') return 'zh-CN';
    if (q === 'en') return 'en';
    return null;
  }

  function detectFromBrowser() {
    var langs = navigator.languages || [navigator.language || ''];
    for (var i = 0; i < langs.length; i++) {
      var l = (langs[i] || '').toLowerCase();
      if (l.indexOf('zh') === 0) return 'zh-CN';
      if (l.indexOf('en') === 0) return 'en';
    }
    return DEFAULT_LANG;
  }

  function resolveLang() {
    var q = readQueryLang();
    if (q) {
      writeCookie(COOKIE_NAME, q);
      return q;
    }
    var c = readCookie(COOKIE_NAME);
    if (c && SUPPORTED.indexOf(c) !== -1) return c;
    // First-visit persistence (kb-v2.2-7): persist the browser-detect /
    // deployment-default choice to cookie so subsequent visits stick.
    var detected = detectFromBrowser();
    writeCookie(COOKIE_NAME, detected);
    return detected;
  }

  function applyLang(lang) {
    // kb-v2.2-7 (A1): always set <html lang>. The previous data-fixed-lang
    // guard for article-detail pages is deleted — site language drives
    // reading language uniformly.
    document.documentElement.setAttribute('lang', lang);
    var toggle = document.querySelector('.lang-toggle');
    if (toggle) toggle.setAttribute('data-current', lang);
  }

  function bindToggle() {
    var toggle = document.querySelector('.lang-toggle');
    if (!toggle) return;
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var current = toggle.getAttribute('data-current') || DEFAULT_LANG;
      var next = current === 'zh-CN' ? 'en' : 'zh-CN';
      writeCookie(COOKIE_NAME, next);
      var url = new URL(window.location.href);
      url.searchParams.set('lang', next);
      window.location.href = url.toString();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      applyLang(resolveLang());
      bindToggle();
    });
  } else {
    applyLang(resolveLang());
    bindToggle();
  }
})();
