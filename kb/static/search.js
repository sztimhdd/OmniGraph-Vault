/* kb/static/search.js — inline search reveal for index.html + articles_index.html.
 *
 * Per kb-3-UI-SPEC §3.6 (D-6 rejected creating /search page): the existing
 * search input on the homepage hero and the article-list page reveals
 * results inline, directly below the input, by injecting into a sibling
 * `<div class="search-results" hidden>` container.
 *
 * Restraint principle (UI-SPEC §1 + §10):
 *   - Zero new visual tokens (reuses kb-1 :root vars)
 *   - Zero new component patterns: search inline reveal is a JS pattern,
 *     not a new component
 *   - Result rows reuse kb-1 .article-card class verbatim — DO NOT
 *     redesign result chips
 *   - Empty / loading / error states delegate to kb-1 .empty-state /
 *     .skeleton / .error-state
 *
 * Wire:
 *   - Hooks the canonical search input via a tolerant selector cascade
 *   - Debounces 300ms on the `input` event
 *   - Fetches GET /api/search?q=...&mode=fts&lang=...&limit=10 (kb-3-06)
 *   - Cancels superseded in-flight requests via AbortController
 *   - Falls back gracefully when JS-disabled (the form's existing Enter
 *     handler already redirects to /articles?q=... on the homepage)
 *
 * Skill invocations applied (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):
 *   Skill(skill="ui-ux-pro-max", args="Implement the kb-3-UI-SPEC §3.6
 *     search inline reveal pattern. Spec is locked: NO new /search page
 *     (D-6 rejected). The search input on homepage + list page already
 *     exists (kb-1). This task INSERTS a search-results container directly
 *     below the existing search form, then JS injects content into it on
 *     debounced input (300ms). Each result is a .article-card (kb-1 class
 *     verbatim — DO NOT redesign). Empty / loading / error states use kb-1
 *     .empty-state / .skeleton / .error-state. A 'View all' link goes to
 *     /articles?q=... (existing list endpoint with q-filter from kb-3-05).
 *     NO new component patterns.")
 *   Skill(skill="frontend-design", args="Wire the ui-ux-pro-max output:
 *     kb/static/search.js as a single IIFE, debounces 300ms on input event,
 *     fetches /api/search?q=...&mode=fts&lang=... (lang inferred from
 *     document.documentElement.lang), injects results into .search-results
 *     div. Pure ES2017 — no transpiler. Append script tag to both
 *     index.html and articles_index.html via {% block extra_scripts %}.
 *     Add minimal CSS (~5 LOC) for the search-results container only.")
 */
(function () {
  'use strict';

  var DEBOUNCE_MS = 300;
  var MIN_QUERY_LEN = 2;
  var FETCH_LIMIT = 10;

  // KG progressive enhancement (additive, never blocks FTS first paint).
  var KG_POLL_MS = 800;
  var KG_POLL_MAX = 12;  // ~9.6s ceiling — KG local mode typically returns within 4-8s

  var input = null;
  var resultsEl = null;
  var debounceTimer = null;
  var inFlight = null;  // AbortController for the current fetch
  var kgToken = 0;       // monotonic token — each new query bumps; stale KG callbacks bail

  function $(sel, root) { return (root || document).querySelector(sel); }

  function locateInput() {
    // Tolerant cascade: the homepage hero uses `<input type="search">` inside
    // `.hero-search`; the article-list page may add a similar input in future.
    return $('.hero-search input[type="search"]')
        || $('form[role="search"] input[name="q"]')
        || $('#search-form input')
        || $('input[name="q"]')
        || $('input[type="search"]');
  }

  function locateResults() {
    return $('.search-results');
  }

  function getLang() {
    var l = (document.documentElement.lang || '').toLowerCase();
    return l.indexOf('en') === 0 ? 'en' : 'zh-CN';
  }

  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, function (c) {
      return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
    });
  }

  function showLoading() {
    if (!resultsEl) return;
    resultsEl.hidden = false;
    // Reuse kb-1 .skeleton — three placeholder rows so the reveal feels
    // populated without flashing emptiness mid-debounce.
    resultsEl.innerHTML = ''
      + '<div class="skeleton search-results__skeleton-row" aria-busy="true"></div>'
      + '<div class="skeleton search-results__skeleton-row" aria-busy="true"></div>'
      + '<div class="skeleton search-results__skeleton-row" aria-busy="true"></div>';
  }

  function showEmpty() {
    if (!resultsEl) return;
    resultsEl.hidden = false;
    resultsEl.innerHTML = ''
      + '<div class="empty-state">'
      + '<p class="empty-state__hint">'
      + '<span data-lang="zh">未找到相关结果</span>'
      + '<span data-lang="en">No results found</span>'
      + '</p>'
      + '</div>';
  }

  function showError(msg) {
    if (!resultsEl) return;
    resultsEl.hidden = false;
    var detail = msg ? '<span class="error-state__detail">' + escapeHtml(msg) + '</span>' : '';
    resultsEl.innerHTML = ''
      + '<div class="error-state" role="alert">'
      + '<span data-lang="zh">搜索失败,请重试</span>'
      + '<span data-lang="en">Search failed, please retry</span>'
      + detail
      + '</div>';
  }

  function langBadgeHtml(lang) {
    var dataAttr = lang === 'en' ? 'en' : (lang === 'zh-CN' ? 'zh-CN' : 'unknown');
    var zh, en;
    if (dataAttr === 'zh-CN') { zh = '中文'; en = 'Chinese'; }
    else if (dataAttr === 'en') { zh = '英文'; en = 'English'; }
    else { zh = '未知'; en = 'Unknown'; }
    return '<span class="lang-badge" data-lang="' + dataAttr + '">'
      + '<span data-lang="zh">' + zh + '</span><span data-lang="en">' + en + '</span>'
      + '</span>';
  }

  function sourceChipHtml(source) {
    // Reuse kb-1 .source-chip; icons embedded as inline SVG would require
    // duplicating macros, so we use simple textual labels — matches kb-1's
    // RSS chip pattern (uppercase "RSS" without an icon).
    if (source === 'wechat') {
      return '<span class="source-chip">'
        + '<span data-lang="zh">微信</span><span data-lang="en">WeChat</span>'
        + '</span>';
    }
    if (source === 'rss') {
      return '<span class="source-chip">RSS</span>';
    }
    return '<span class="source-chip">'
      + '<span data-lang="zh">网页</span><span data-lang="en">Web</span>'
      + '</span>';
  }

  function renderItems(items, total, q) {
    if (!resultsEl) return;
    if (!items || items.length === 0) { showEmpty(); return; }

    var html = '<div class="article-list search-results__list">';
    items.forEach(function (it) {
      // Reuse .article-card verbatim. Snippet from FTS5 already contains
      // <mark> tags per kb-3-API-CONTRACT §5.3, so we do NOT escape it
      // (server is trusted). Title and meta are escaped.
      var hash = encodeURIComponent(it.hash || '');
      var title = escapeHtml(it.title || '');
      var snippet = it.snippet || '';
      html += '<a class="article-card" href="' + (window.KB_BASE_PATH || '') + '/articles/' + hash + '.html"'
        + ' data-lang="' + escapeHtml(it.lang || 'unknown') + '"'
        + ' data-source="' + escapeHtml(it.source || 'web') + '">'
        + '<div class="article-card-meta">'
        + langBadgeHtml(it.lang)
        + sourceChipHtml(it.source)
        + '</div>'
        + '<h3 class="article-card-title">' + title + '</h3>'
        + (snippet ? '<p class="article-card-snippet">' + snippet + '</p>' : '')
        + '</a>';
    });
    html += '</div>';

    if (total > items.length) {
      html += '<div class="search-results__footer">'
        + '<a href="' + (window.KB_BASE_PATH || '') + '/articles/?q=' + encodeURIComponent(q) + '" class="article-card-readmore">'
        + '<span data-lang="zh">查看全部 (' + total + ')</span>'
        + '<span data-lang="en">View all (' + total + ')</span>'
        + '</a>'
        + '</div>';
    }

    resultsEl.hidden = false;
    resultsEl.innerHTML = html;
  }

  function buildSearchUrl(q, lang) {
    var url = (window.KB_BASE_PATH || '') + '/api/search?q=' + encodeURIComponent(q)
      + '&mode=fts'
      + '&limit=' + FETCH_LIMIT;
    if (lang) url += '&lang=' + encodeURIComponent(lang);
    return url;
  }

  function fetchSearch(q, lang) {
    return fetch(buildSearchUrl(q, lang), {
      signal: inFlight ? inFlight.signal : undefined,
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      });
  }

  function runSearch(q) {
    if (inFlight) inFlight.abort();
    inFlight = (typeof AbortController === 'function') ? new AbortController() : null;
    var myToken = ++kgToken;  // invalidate any KG poll from a previous query
    showLoading();
    var lang = getLang();
    fetchSearch(q, lang)
      .then(function (data) {
        // Locale-filtered search is useful for bilingual browsing, but ASCII
        // tech terms such as "langchain" often only exist in the other language.
        // Retry once without lang before showing an empty state.
        if ((!data.items || data.items.length === 0) && lang) {
          return fetchSearch(q, null);
        }
        return data;
      })
      .then(function (data) {
        renderItems(data.items || [], data.total || 0, q);
        // Progressive enhancement: kick off KG augmentation AFTER FTS paint.
        // Failure modes (503, 404, network, empty) silently keep FTS-only.
        runKgEnhancement(q, myToken);
      })
      .catch(function (e) {
        if (e && e.name === 'AbortError') return;  // Superseded by newer query
        showError(e && e.message ? e.message : '');
      });
  }

  // ---- KG progressive enhancement ----------------------------------------

  function collectFtsHashes() {
    if (!resultsEl) return {};
    var seen = {};
    var nodes = resultsEl.querySelectorAll('.article-card');
    for (var i = 0; i < nodes.length; i++) {
      var href = nodes[i].getAttribute('href') || '';
      var m = href.match(/\/articles\/([a-f0-9]{10})\.html/);
      if (m) seen[m[1]] = true;
    }
    return seen;
  }

  function kgCardHtml(item) {
    var hash = encodeURIComponent(item.hash || '');
    var title = escapeHtml(item.title || '');
    var snippet = escapeHtml(item.snippet || '');
    return '<a class="article-card article-card--kg" href="'
      + (window.KB_BASE_PATH || '') + '/articles/' + hash + '.html"'
      + ' data-lang="' + escapeHtml(item.lang || 'unknown') + '"'
      + ' data-source="' + escapeHtml(item.source || 'web') + '">'
      + '<div class="article-card-meta">'
      + langBadgeHtml(item.lang)
      + sourceChipHtml(item.source)
      + '<span class="kg-badge" aria-label="Knowledge graph result">'
      + '<span aria-hidden="true">🔗</span> KG'
      + '</span>'
      + '</div>'
      + '<h3 class="article-card-title">' + title + '</h3>'
      + (snippet ? '<p class="article-card-snippet">' + snippet + '</p>' : '')
      + '</a>';
  }

  function appendKgResults(items, myToken) {
    if (myToken !== kgToken) return;  // stale — newer query already running
    if (!resultsEl || !items || items.length === 0) return;
    var ftsHashes = collectFtsHashes();
    var fresh = items.filter(function (it) {
      return it && it.hash && !ftsHashes[it.hash];
    });
    if (fresh.length === 0) return;
    var list = resultsEl.querySelector('.search-results__list');
    if (!list) {
      // FTS rendered an empty-state — replace with a fresh list to host KG cards
      var html = '<div class="article-list search-results__list">';
      fresh.forEach(function (it) { html += kgCardHtml(it); });
      html += '</div>';
      resultsEl.hidden = false;
      resultsEl.innerHTML = html;
      return;
    }
    var buf = '';
    fresh.forEach(function (it) { buf += kgCardHtml(it); });
    list.insertAdjacentHTML('beforeend', buf);
  }

  function pollKgJob(jobId, attempt, myToken) {
    if (myToken !== kgToken) return;  // superseded by newer query
    if (attempt >= KG_POLL_MAX) return;  // budget exhausted — silent giveup
    var url = (window.KB_BASE_PATH || '') + '/api/search/kg/' + encodeURIComponent(jobId);
    fetch(url, { headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (myToken !== kgToken) return;
        if (data && data.status === 'pending') {
          setTimeout(function () { pollKgJob(jobId, attempt + 1, myToken); }, KG_POLL_MS);
          return;
        }
        if (data && Array.isArray(data.results)) {
          appendKgResults(data.results, myToken);
        }
      })
      .catch(function () { /* silent — keep FTS-only view */ });
  }

  function runKgEnhancement(q, myToken) {
    var url = (window.KB_BASE_PATH || '') + '/api/search/kg';
    fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({ query: q })
    })
      .then(function (r) {
        if (r.status === 503) return null;  // KG unavailable — silent
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.job_id) return;
        if (myToken !== kgToken) return;
        setTimeout(function () { pollKgJob(data.job_id, 0, myToken); }, KG_POLL_MS);
      })
      .catch(function () { /* silent — keep FTS-only view */ });
  }

  function onInput(e) {
    clearTimeout(debounceTimer);
    var q = ((e.target && e.target.value) || '').trim();
    if (q.length < MIN_QUERY_LEN) {
      if (inFlight) { inFlight.abort(); inFlight = null; }
      if (resultsEl) { resultsEl.hidden = true; resultsEl.innerHTML = ''; }
      return;
    }
    debounceTimer = setTimeout(function () { runSearch(q); }, DEBOUNCE_MS);
  }

  function init() {
    input = locateInput();
    resultsEl = locateResults();
    if (!input || !resultsEl) return;
    input.addEventListener('input', onInput);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
