/* kb/static/qa.js — Q&A result state machine for kb-3.
 *
 * Drives the 8-state matrix per kb-3-UI-SPEC §3.2:
 *   idle -> submitting -> polling -> done | error | timeout -> fts5_fallback
 *
 * The CSS selectors in style.css (kb-3 Q&A section) reveal the matching
 * sub-region per state. This script's job is to:
 *   1. Update data-qa-state on #qa-result on each transition
 *   2. POST /api/synthesize, then poll GET /api/synthesize/{job_id}
 *   3. Render markdown answer (marked.js), source chips, entity chips
 *   4. Persist localStorage feedback as kb_qa_feedback_{job_id}
 *   5. Wire retry button + auto-transition timeout -> fts5_fallback (D-8)
 *
 * Polling cadence:
 *   window.KB_QA_POLL_INTERVAL_MS (default 1500)
 *   window.KB_QA_POLL_TIMEOUT_MS  (default 60000)
 * Both injected by ask.html before this script loads.
 *
 * Skill invocations applied (per kb/docs/10-DESIGN-DISCIPLINE.md Rule 1):
 *   Skill(skill="ui-ux-pro-max", args="State-machine driven UX: spinner
 *     during submitting/polling, honest 'fts5_fallback' chip on degraded
 *     answers (no anthropomorphism), result-reveal animation as signature
 *     moment, manual retry button (no auto-retry per D-12).")
 *   Skill(skill="frontend-design", args="Pure ES2017 IIFE, no jQuery,
 *     no transpiler. Single window.KbQA.submit(question, lang) entry.
 *     marked.js v4 for markdown render. Source chips per UI-SPEC §3.1.
 *     localStorage for feedback (no backend POST per D-7).")
 */
(function () {
  'use strict';

  var POLL_INTERVAL = window.KB_QA_POLL_INTERVAL_MS || 1500;
  // 260527-tk-stale-poll: floor POLL_TIMEOUT at 240000ms to match backend
  // KB_SYNTHESIZE_TIMEOUT prod default. ask.html ships window value 60000
  // which is too short for long_form mode (real wallclock 90-180s per
  // arx-3 Gate 4 evidence). Sync-only deploy: ask.html template change
  // won't take effect until apps deploy, so floor must live here.
  var POLL_TIMEOUT = Math.max(window.KB_QA_POLL_TIMEOUT_MS || 0, 240000);

  var resultEl = null;
  var currentJobId = null;
  var pollTimer = null;
  var pollStarted = 0;

  // kb-v2.1-5: synthesis mode persisted across page reloads. Default 'qa' so
  // pre-existing users see the same Quick-answer flow they had before.
  var currentMode = 'qa';
  try {
    currentMode = localStorage.getItem('kb_qa_mode') || 'qa';
  } catch (e) {
    // localStorage unavailable (private mode) — keep default
  }
  if (currentMode !== 'qa' && currentMode !== 'long_form') currentMode = 'qa';

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $all(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function setState(state) {
    if (!resultEl) return;
    resultEl.setAttribute('data-qa-state', state);
    if (state !== 'idle') resultEl.hidden = false;
    var stateText = $('.qa-state-text', resultEl);
    if (stateText) {
      var attr = 'data-state-text-' + state;
      var t = stateText.getAttribute(attr);
      if (t) stateText.textContent = t;
    }
  }

  function setQuestionEcho(q) {
    var p = $('.qa-question-text', resultEl);
    if (p) p.textContent = q;
  }

  // Build a hash -> title map from sources[] (server-side _resolve_sources)
  // so orphan citations can use the real article title as link label.
  function buildTitleMap(sources) {
    var map = {};
    if (!sources || !sources.length) return map;
    for (var i = 0; i < sources.length; i++) {
      var s = sources[i];
      var hash = (typeof s === 'string') ? s : (s && s.hash) || '';
      var title = (s && s.title) || '';
      if (hash) map[hash] = title;
    }
    return map;
  }

  // Convert orphan inline citations into real markdown links. LLM emits
  // several broken formats observed in prod:
  //   [/article/abc1234567]
  //   [/article:abc1234567]
  //   [abc1234567]            ← bare 10-hex hash with no /article/ prefix
  // All collapse to [<title-or-hash>](base/articles/<hash>.html). Runs on
  // raw markdown BEFORE marked.js parse so the result emits real <a>.
  function rewriteOrphanCitations(md, titleMap) {
    var base = window.KB_BASE_PATH || '';
    function makeLink(hash) {
      var label = (titleMap && titleMap[hash]) || hash.slice(0, 6);
      return '[' + label + '](' + base + '/articles/' + hash + '.html)';
    }
    // Pass 1: bracketed article refs in any of these LLM-emitted shapes:
    //   [/article/<hash>]  [/article:<hash>]
    //   [article/<hash>]   [article:<hash>]
    //   [article-<hash>]   [article <hash>]
    md = md.replace(/\[\/?article[\s/:_-]([a-f0-9]{10})\]/g, function (_m, hash) {
      return makeLink(hash);
    });
    // Pass 2: bare [<10-hex hash>] — must run AFTER pass 1 so we don't
    // double-rewrite. Look-behind avoids matching `[abc...](...)` markdown
    // links the LLM did emit correctly (they have `(` after `]`).
    md = md.replace(/\[([a-f0-9]{10})\](?!\()/g, function (_m, hash) {
      return makeLink(hash);
    });
    return md;
  }

  // After marked render: prepend KB_BASE_PATH to absolute /static/img/ and
  // /articles/ paths so they work on Aliyun (/kb/ prefix) and Databricks (/).
  // Also nuke broken base64 placeholder srcs (Caddy SPA fallback returned
  // vitaclaw HTML, lazy-load embedded as data:image/jpeg). If data-sv-src
  // exists, swap src to use it; otherwise rely on rewritten src.
  //
  // sourceHashes is the whitelist of real article hashes from data.result.sources.
  // Any <a> whose href doesn't resolve to a hash in this set is downgraded to
  // <span> (LLM hallucinated link target — better to look unclickable than to
  // 404 the user). Also dedupes consecutive References sections (LLM sometimes
  // emits the list twice).
  function rewriteAnswerHtml(rootEl, sourceHashes) {
    var base = window.KB_BASE_PATH || '';
    if (!rootEl) return;
    var validSet = {};
    if (sourceHashes && sourceHashes.length) {
      for (var k = 0; k < sourceHashes.length; k++) validSet[sourceHashes[k]] = true;
    }
    // <a href> rewrite + dead-link sanitize
    var anchors = rootEl.querySelectorAll('a[href]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var h = a.getAttribute('href') || '';
      var m = h.match(/^\/?articles?\/([a-f0-9]{10})(?:\.html)?$/);
      var hash = m ? m[1] : null;
      if (hash && (!sourceHashes || !sourceHashes.length || validSet[hash])) {
        a.setAttribute('href', base + '/articles/' + hash + '.html');
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener');
      } else {
        var span = document.createElement('span');
        span.className = 'qa-dead-citation';
        span.textContent = a.textContent;
        a.parentNode.replaceChild(span, a);
      }
    }

    // Image sanitize. LLM emits ![alt](path) where path is a description
    // ("Claude Code harness architecture") or invalid. Real images live at
    // /static/img/<10hex>/<n>.<ext>. Anything else is removed entirely
    // (broken image icon worse than nothing).
    var validImgRe = /\/static\/img\/[a-f0-9]{10}\/\d+\.\w+(\?.*)?$/;
    var imgs = rootEl.querySelectorAll('img');
    for (var j = imgs.length - 1; j >= 0; j--) {
      var img = imgs[j];
      var dataSv = img.getAttribute('data-sv-src');
      var srcAttr = img.getAttribute('src') || '';
      var resolved = null;
      if (dataSv && validImgRe.test(dataSv)) {
        resolved = dataSv;
        img.removeAttribute('data-sv-src');
      } else if (validImgRe.test(srcAttr) && srcAttr.indexOf('data:') !== 0) {
        resolved = srcAttr;
      }
      if (!resolved) {
        if (img.parentNode) img.parentNode.removeChild(img);
        continue;
      }
      if (resolved.charAt(0) === '/' && resolved.indexOf(base + '/') !== 0) {
        resolved = base + resolved;
      }
      img.setAttribute('src', resolved);
      img.setAttribute('loading', 'lazy');
    }

    // Dedupe References sections. LLM uses BOTH H2 (`## References`) and
    // BOLD (`**References**`) — a duplicate may be one of each. Walk
    // top-level children, find heading-like nodes whose text matches a
    // References keyword, keep the first, drop later candidates + their
    // following siblings until the next heading-like node.
    var REF_KEYWORDS = ['references', 'reference', '参考文献', '参考来源', '引用', '参考资料'];
    function isReferenceText(t) {
      t = (t || '').trim().toLowerCase();
      if (!t || t.length > 30) return false;
      for (var x = 0; x < REF_KEYWORDS.length; x++) {
        if (t === REF_KEYWORDS[x] || t.indexOf(REF_KEYWORDS[x]) === 0) return true;
      }
      return false;
    }
    function headingLike(node) {
      if (!node || node.nodeType !== 1) return null;
      if (/^H[1-6]$/.test(node.tagName)) {
        return { level: parseInt(node.tagName.substring(1), 10), text: node.textContent };
      }
      // <p><strong>References</strong></p> — bold-as-heading
      if (node.tagName === 'P' && node.children.length === 1) {
        var c = node.children[0];
        if ((c.tagName === 'STRONG' || c.tagName === 'B') &&
            c.textContent.trim() === node.textContent.trim()) {
          return { level: 99, text: c.textContent };
        }
      }
      return null;
    }
    // Collect every References-like section + its trailing siblings.
    // Score each by anchor count (links pointing to /articles/<hash>.html).
    // Keep the highest-scoring one — LLM commonly emits a disclaimer/no-link
    // version alongside the real link list, and we want the link list.
    var refSections = [];
    var ch = rootEl.children;
    for (var ci = 0; ci < ch.length; ci++) {
      var info = headingLike(ch[ci]);
      if (info && isReferenceText(info.text)) {
        var startNode = ch[ci];
        var sectLevel = info.level;
        var members = [startNode];
        var sib = startNode.nextElementSibling;
        while (sib) {
          var sibInfo = headingLike(sib);
          if (sibInfo && sibInfo.level <= sectLevel) break;
          members.push(sib);
          sib = sib.nextElementSibling;
        }
        var linkCount = 0;
        for (var mm = 0; mm < members.length; mm++) {
          var qel = members[mm];
          if (qel && qel.querySelectorAll) {
            linkCount += qel.querySelectorAll('a[href*="/articles/"]').length;
          }
        }
        refSections.push({ members: members, linkCount: linkCount });
      }
    }
    if (refSections.length > 1) {
      // Tie-break: keep LAST section with max linkCount (LLM tends to put
      // structured link list at the very end).
      var bestIdx = 0;
      for (var bb = 1; bb < refSections.length; bb++) {
        if (refSections[bb].linkCount >= refSections[bestIdx].linkCount) {
          bestIdx = bb;
        }
      }
      for (var rs = 0; rs < refSections.length; rs++) {
        if (rs === bestIdx) continue;
        var sweep = refSections[rs].members;
        for (var sn = 0; sn < sweep.length; sn++) {
          if (sweep[sn].parentNode) sweep[sn].parentNode.removeChild(sweep[sn]);
        }
      }
    }
    // <img src> rewrite + data:image placeholder cleanup
    var imgs = rootEl.querySelectorAll('img');
    for (var j = 0; j < imgs.length; j++) {
      var img = imgs[j];
      var dataSv = img.getAttribute('data-sv-src');
      var src = img.getAttribute('src') || '';
      // If data-sv-src exists, that's the truthful path — use it, ignore src.
      if (dataSv) {
        src = dataSv;
        img.removeAttribute('data-sv-src');
      } else if (src.indexOf('data:') === 0) {
        // Broken base64 placeholder with no data-sv-src — skip (already broken).
        continue;
      }
      // Rewrite absolute /static/img/... to base + /static/img/...
      if (src.charAt(0) === '/' && src.indexOf(base + '/') !== 0) {
        src = base + src;
      }
      img.setAttribute('src', src);
      img.setAttribute('loading', 'lazy');
    }
  }

  function renderAnswerMarkdown(md, sources) {
    var article = $('.qa-answer', resultEl);
    if (!article) return;
    var titleMap = buildTitleMap(sources);
    var sourceHashes = Object.keys(titleMap);
    var text = rewriteOrphanCitations(md || '', titleMap);
    var html;
    if (window.marked && typeof window.marked.parse === 'function') {
      html = window.marked.parse(text);
    } else {
      // Fallback: escape and wrap so the answer still renders if marked.js failed to load
      var div = document.createElement('div');
      div.textContent = text;
      html = '<pre>' + div.innerHTML + '</pre>';
    }
    article.innerHTML = html;
    rewriteAnswerHtml(article, sourceHashes);
  }

  function renderSources(sources) {
    var ul = $('.qa-sources-list', resultEl);
    if (!ul) return;
    ul.innerHTML = '';
    if (!sources || !sources.length) return;
    sources.forEach(function (s) {
      var hash = (typeof s === 'string') ? s : (s && s.hash) || '';
      var title = (s && s.title) || hash;
      if (!hash) return;
      var li = document.createElement('li');
      li.className = 'qa-source-chip';
      var a = document.createElement('a');
      a.href = (window.KB_BASE_PATH || '') + '/articles/' + encodeURIComponent(hash) + '.html';
      a.target = '_blank';
      a.rel = 'noopener';
      a.className = 'qa-source-link';
      var titleSpan = document.createElement('span');
      titleSpan.className = 'qa-source-title';
      titleSpan.textContent = String(title).slice(0, 60);
      a.appendChild(titleSpan);
      if (s && s.lang) {
        var langBadge = document.createElement('span');
        langBadge.className = 'lang-badge';
        langBadge.setAttribute('data-lang', s.lang);
        langBadge.textContent = s.lang === 'en' ? 'EN' : (s.lang === 'zh-CN' ? '中' : '?');
        a.appendChild(langBadge);
      }
      li.appendChild(a);
      ul.appendChild(li);
    });
  }

  function renderEntities(entities) {
    var ul = $('.qa-entities-list', resultEl);
    if (!ul) return;
    ul.innerHTML = '';
    (entities || []).forEach(function (e) {
      var name = (e && e.name) || (typeof e === 'string' ? e : '');
      if (!name) return;
      var li = document.createElement('li');
      li.className = 'entity-chip chip chip--entity';
      li.textContent = name;
      ul.appendChild(li);
    });
  }

  function setError(msg) {
    var p = $('.qa-error-text', resultEl);
    if (p) p.textContent = msg || 'Unknown error';
  }

  function setupFeedbackHandlers() {
    $all('.qa-feedback-btn', resultEl).forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (!currentJobId) return;
        var dir = btn.classList.contains('qa-feedback-btn--up') ? 'up' : 'down';
        try {
          localStorage.setItem('kb_qa_feedback_' + currentJobId, dir);
        } catch (e) {
          // localStorage may be unavailable (private mode); silently ignore
        }
        $all('.qa-feedback-btn', resultEl).forEach(function (b) {
          b.setAttribute('aria-pressed', 'false');
        });
        btn.setAttribute('aria-pressed', 'true');
      });
    });
  }

  function setupRetryHandler() {
    var btn = $('.qa-retry-btn', resultEl);
    if (!btn) return;
    btn.addEventListener('click', function () {
      var input = document.getElementById('ask-input');
      var q = input ? (input.value || '').trim() : '';
      if (!q) return;
      var lang = (document.documentElement.lang || 'zh-CN').indexOf('en') === 0 ? 'en' : 'zh';
      submit(q, lang);
    });
  }

  // kb-v2.1-5: mode toggle wiring. The toggle lives outside #qa-result, so
  // queries are document-rooted, not resultEl-rooted.
  function setActiveModeButton(mode) {
    $all('.qa-mode-btn').forEach(function (btn) {
      var on = btn.getAttribute('data-mode') === mode;
      btn.setAttribute('aria-checked', on ? 'true' : 'false');
    });
  }

  function setupModeToggle() {
    var buttons = $all('.qa-mode-btn');
    if (!buttons.length) return;
    setActiveModeButton(currentMode);
    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var nextMode = btn.getAttribute('data-mode');
        if (nextMode !== 'qa' && nextMode !== 'long_form') return;
        currentMode = nextMode;
        try {
          localStorage.setItem('kb_qa_mode', currentMode);
        } catch (e) {
          // localStorage unavailable — runtime state only
        }
        setActiveModeButton(currentMode);
      });
    });
  }

  function clearPoll() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function pollOnce() {
    if (!currentJobId) return;
    var elapsed = Date.now() - pollStarted;
    if (elapsed > POLL_TIMEOUT) {
      setState('timeout');
      // Auto-transition to fts5_fallback after 500ms (UI-SPEC §3.2 D-8)
      setTimeout(function () {
        setState('fts5_fallback');
      }, 500);
      clearPoll();
      return;
    }
    fetch((window.KB_BASE_PATH || '') + '/api/synthesize/' + encodeURIComponent(currentJobId), {
      headers: { 'Accept': 'application/json' }
    })
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 404) throw new Error('job not found');
          throw new Error('HTTP ' + r.status);
        }
        return r.json();
      })
      .then(function (data) {
        if (data.status === 'running') {
          pollTimer = setTimeout(pollOnce, POLL_INTERVAL);
          return;
        }
        if (data.status === 'done') {
          // F2: confidence-aware 4-branch dispatch (AUDIT.md F2 — P1).
          // The 2-branch fallback_used check collapsed 'no_results' onto
          // 'fts5_fallback', mismatching banner text vs actual confidence.
          // Backend confidence values: 'kg' | 'fts5_fallback' | 'no_results'.
          var fallback = data.fallback_used === true;
          var confidence = (data.result && data.result.confidence) || data.confidence || '';
          var nextState;
          if (confidence === 'no_results') nextState = 'no_results';
          else if (fallback || confidence === 'fts5_fallback') nextState = 'fts5_fallback';
          else nextState = 'done';
          setState(nextState);
          if (data.result) {
            renderAnswerMarkdown(data.result.markdown || '', data.result.sources || []);
            renderSources(data.result.sources || []);
            // entities only render on the real KG branch (D-9): fallback +
            // no_results both hide the entity cloud.
            if (nextState === 'done') renderEntities(data.result.entities || []);
          }
          clearPoll();
          return;
        }
        // status === 'failed' or anything else: surface as error
        setError(data.error || 'Unexpected status: ' + data.status);
        setState('error');
        clearPoll();
      })
      .catch(function (e) {
        setError(e && e.message ? e.message : String(e));
        setState('error');
        clearPoll();
      });
  }

  function submit(question, lang) {
    if (!resultEl) resultEl = document.getElementById('qa-result');
    if (!resultEl) return;
    clearPoll();
    currentJobId = null;
    setQuestionEcho(question);
    setState('submitting');
    // 260527-tk-stale-poll: clear stale answer DOM so timeout/fts5_fallback
    // path doesn't show prior job's markdown above the new state banner.
    renderAnswerMarkdown('');
    fetch((window.KB_BASE_PATH || '') + '/api/synthesize', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({
        question: question,
        lang: lang || 'zh',
        mode: currentMode
      })
    })
      .then(function (r) {
        if (!r.ok) {
          if (r.status === 422) throw new Error('Invalid question');
          throw new Error('HTTP ' + r.status);
        }
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.job_id) throw new Error('No job_id returned');
        currentJobId = data.job_id;
        setState('polling');
        pollStarted = Date.now();
        pollTimer = setTimeout(pollOnce, POLL_INTERVAL);
      })
      .catch(function (e) {
        setError(e && e.message ? e.message : String(e));
        setState('error');
      });
  }

  window.KbQA = { submit: submit };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () {
      resultEl = document.getElementById('qa-result');
      setupModeToggle();
      if (!resultEl) return;
      setupFeedbackHandlers();
      setupRetryHandler();
    });
  } else {
    resultEl = document.getElementById('qa-result');
    setupModeToggle();
    if (resultEl) {
      setupFeedbackHandlers();
      setupRetryHandler();
    }
  }
})();
