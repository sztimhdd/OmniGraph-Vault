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
  var POLL_TIMEOUT = window.KB_QA_POLL_TIMEOUT_MS || 60000;

  var resultEl = null;
  var currentJobId = null;
  var pollTimer = null;
  var pollStarted = 0;

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

  function renderAnswerMarkdown(md) {
    var article = $('.qa-answer', resultEl);
    if (!article) return;
    var text = md || '';
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
      a.href = '/article/' + encodeURIComponent(hash) + '.html';
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
        setState('fallback');
      }, 500);
      clearPoll();
      return;
    }
    fetch('/api/synthesize/' + encodeURIComponent(currentJobId), {
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
          var fallback = data.fallback_used === true;
          if (fallback) {
            setState('fallback');
          } else {
            setState('done');
          }
          if (data.result) {
            renderAnswerMarkdown(data.result.markdown || '');
            renderSources(data.result.sources || []);
            // fts5_fallback never has entities (D-9)
            if (!fallback) renderEntities(data.result.entities || []);
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
    fetch('/api/synthesize', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      body: JSON.stringify({ question: question, lang: lang || 'zh' })
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
      if (!resultEl) return;
      setupFeedbackHandlers();
      setupRetryHandler();
    });
  } else {
    resultEl = document.getElementById('qa-result');
    if (resultEl) {
      setupFeedbackHandlers();
      setupRetryHandler();
    }
  }
})();
