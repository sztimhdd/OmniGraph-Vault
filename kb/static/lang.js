/* I18N-01/02/08: Bilingual chrome switcher.
 *
 * Resolution order:
 *   1. ?lang=zh|en|zh-CN query param (hard switch — sets cookie)
 *   2. kb_lang cookie (persisted choice)
 *   3. navigator.languages (Accept-Language equivalent)
 *   4. fallback: 'zh-CN'
 *
 * Sets <html lang> on chrome pages (home, articles list, ask).
 * On article detail pages, server-side sets <html lang> = content language;
 * this script does NOT override that — only toggles UI chrome spans.
 * Detection: <html data-fixed-lang="true"> means content-fixed page.
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
  var DEFAULT_LANG = 'zh-CN';

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
    return detectFromBrowser();
  }

  function applyLang(lang) {
    var html = document.documentElement;
    if (html.getAttribute('data-fixed-lang') !== 'true') {
      html.setAttribute('lang', lang);
    }
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
