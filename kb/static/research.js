/* kb/static/research.js — Deep Research 5-stage stepper + SSE pump (arx-2-finish GAP B).
 *
 * Drives the 5-stage stepper on #research-result. Unlike qa.js (which polls
 * GET /api/synthesize/{job_id}), /api/research is a SINGLE-SHOT POST + JSON body
 * that streams SSE. EventSource is GET-only, so this uses fetch() + a
 * ReadableStream reader + a manual SSE frame parser (split on blank line, parse
 * `event:` / `data:` lines).
 *
 * SSE wire protocol (kb/api_routers/research.py + orchestrator):
 *   Request:  POST /api/research {"query": str, "max_iterations": int 1..10}
 *   Frame:    event: NAME \n data: JSON \n\n
 *   5 stage events (fixed order): web_baseline, retriever, reasoner, verifier, synthesizer
 *     stage frames: {"stage":..,"status":"ok"|"skipped"|"failed","reason":..,...}
 *     EXCEPT synthesizer: NO status field (Axis 8 terminal).
 *   Terminal: event: done \n data: {"markdown","confidence","sources":[{kind,uri,title,snippet}],"images_embedded","note_lines"}
 *   Error:    event: error \n data: {"message","type"}  (HTTP stays 200 once flushed)
 *
 * Reuse from qa.js (copied verbatim — no module system; both are self-contained IIFEs):
 *   buildTitleMap, rewriteOrphanCitations, rewriteAnswerHtml, renderAnswerMarkdown.
 * NOT reused: submit/pollOnce/setupModeToggle/setupFeedbackHandlers/setupRetryHandler.
 * Custom (Pitfall 7): renderResearchSources — done.sources[i] has .uri NOT .hash.
 */
(function () {
  'use strict';

  var base = window.KB_BASE_PATH || '';
  var STAGES = ['web_baseline', 'retriever', 'reasoner', 'verifier', 'synthesizer'];

  var resultEl = null;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  // -------------------------------------------------------------------------
  // Reused render half (verbatim from qa.js:82-323) — markdown + citation fix.
  // -------------------------------------------------------------------------

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

  function rewriteOrphanCitations(md, titleMap) {
    function makeLink(hash) {
      var label = (titleMap && titleMap[hash]) || hash.slice(0, 6);
      return '[' + label + '](' + base + '/articles/' + hash + '.html)';
    }
    md = md.replace(/\[\/?article[\s/:_-]([a-f0-9]{10})\]/g, function (_m, hash) {
      return makeLink(hash);
    });
    md = md.replace(/\[([a-f0-9]{10})\](?!\()/g, function (_m, hash) {
      return makeLink(hash);
    });
    md = md.replace(
      /(^|[^\]])\((\/?(?:kb\/)?articles?\/([a-f0-9]{10})(?:\.html)?)\)/g,
      function (_m, prefix, _path, hash) {
        return prefix + makeLink(hash);
      }
    );
    return md;
  }

  function rewriteAnswerHtml(rootEl, sourceHashes) {
    if (!rootEl) return;
    var validSet = {};
    if (sourceHashes && sourceHashes.length) {
      for (var k = 0; k < sourceHashes.length; k++) validSet[sourceHashes[k]] = true;
    }
    // <a href> rewrite + dead-link sanitize.
    var anchors = rootEl.querySelectorAll('a[href]');
    for (var i = 0; i < anchors.length; i++) {
      var a = anchors[i];
      var h = a.getAttribute('href') || '';
      var m = h.match(/articles?\/([a-f0-9]{10})(?:\.html)?$/);
      var hash = m ? m[1] : null;
      if (hash && (!sourceHashes || !sourceHashes.length || validSet[hash])) {
        a.setAttribute('href', base + '/articles/' + hash + '.html');
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener');
        var labelText = (a.textContent || '').trim();
        if (labelText.length > 20) {
          a.textContent = '[' + hash.slice(0, 6) + ']';
          a.className = (a.className ? a.className + ' ' : '') + 'qa-inline-cite';
        }
      } else {
        var span = document.createElement('span');
        span.className = 'qa-dead-citation';
        span.textContent = a.textContent;
        a.parentNode.replaceChild(span, a);
      }
    }

    // Image sanitize — only real /static/img/<10hex>/<n>.<ext> survive.
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

    // Strip LLM-emitted References sections — the page renders verified Sources
    // chips below the body (renderResearchSources); the LLM list adds noise.
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
      if (node.tagName === 'P' && node.children.length === 1) {
        var c = node.children[0];
        if ((c.tagName === 'STRONG' || c.tagName === 'B') &&
            c.textContent.trim() === node.textContent.trim()) {
          return { level: 99, text: c.textContent };
        }
      }
      return null;
    }
    var ch = rootEl.children;
    var toSweep = [];
    for (var ci = 0; ci < ch.length; ci++) {
      var info = headingLike(ch[ci]);
      if (!info || !isReferenceText(info.text)) continue;
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
      toSweep.push(members);
    }
    for (var ts = 0; ts < toSweep.length; ts++) {
      var sweep = toSweep[ts];
      for (var sn = 0; sn < sweep.length; sn++) {
        if (sweep[sn].parentNode) sweep[sn].parentNode.removeChild(sweep[sn]);
      }
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
      var div = document.createElement('div');
      div.textContent = text;
      html = '<pre>' + div.innerHTML + '</pre>';
    }
    article.innerHTML = html;
    rewriteAnswerHtml(article, sourceHashes);
  }

  // -------------------------------------------------------------------------
  // Custom renderResearchSources (Pitfall 7): done.sources[i] has .uri NOT .hash.
  // -------------------------------------------------------------------------

  function renderResearchSources(sources, root) {
    var ul = $('.qa-sources-list', root);
    if (!ul) return;
    ul.innerHTML = '';
    if (!sources || !sources.length) return;
    sources.forEach(function (s) {
      if (!s) return;
      var uri = (typeof s === 'string') ? s : (s.uri || '');
      var title = (s && s.title) || uri;
      if (!title) return;
      var li = document.createElement('li');
      li.className = 'qa-source-chip';
      var isHttp = /^https?:\/\//i.test(uri);
      var labelText = String(title).slice(0, 80);
      if (isHttp) {
        var a = document.createElement('a');
        a.href = uri;
        a.target = '_blank';
        a.rel = 'noopener';
        a.className = 'qa-source-link';
        var titleSpan = document.createElement('span');
        titleSpan.className = 'qa-source-title';
        titleSpan.textContent = labelText;
        a.appendChild(titleSpan);
        li.appendChild(a);
      } else {
        // KG chunk / non-URL source: render a plain (non-link) chip.
        var span = document.createElement('span');
        span.className = 'qa-source-link qa-source-link--plain';
        var ts = document.createElement('span');
        ts.className = 'qa-source-title';
        ts.textContent = labelText;
        span.appendChild(ts);
        li.appendChild(span);
      }
      ul.appendChild(li);
    });
  }

  // -------------------------------------------------------------------------
  // Stepper state + SSE pump.
  // -------------------------------------------------------------------------

  function setResearchState(state) {
    if (!resultEl) return;
    resultEl.setAttribute('data-research-state', state);
    if (state !== 'idle') resultEl.hidden = false;
  }

  function setStepState(stage, state) {
    if (!resultEl) return;
    var li = resultEl.querySelector('.research-step[data-stage="' + stage + '"]');
    if (li) li.setAttribute('data-step-state', state);
  }

  function resetSteps() {
    STAGES.forEach(function (s) { setStepState(s, 'pending'); });
    var banner = $('.research-error-banner', resultEl);
    if (banner) { banner.hidden = true; banner.textContent = ''; }
    var article = $('.qa-answer', resultEl);
    if (article) article.innerHTML = '';
    var ul = $('.qa-sources-list', resultEl);
    if (ul) ul.innerHTML = '';
  }

  function setQuestionEcho(q) {
    var p = $('.qa-question-text', resultEl);
    if (p) p.textContent = q;
  }

  // A stage frame arrives AT that stage's completion: mark THAT step done/
  // skipped/failed from payload.status (synthesizer has no status -> done),
  // and light the NEXT step running.
  function onStageUpdate(stage, payload) {
    var status = payload && payload.status;
    var stepState = 'done';
    if (status === 'skipped') stepState = 'skipped';
    else if (status === 'failed') stepState = 'failed';
    setStepState(stage, stepState);
    var idx = STAGES.indexOf(stage);
    if (idx >= 0 && idx + 1 < STAGES.length) {
      setStepState(STAGES[idx + 1], 'running');
    }
  }

  function onDone(payload) {
    payload = payload || {};
    renderAnswerMarkdown(payload.markdown || '', payload.sources || []);
    renderResearchSources(payload.sources || [], resultEl);
    // Any step still pending/running at done time -> done (defensive).
    STAGES.forEach(function (s) {
      var li = resultEl.querySelector('.research-step[data-stage="' + s + '"]');
      var st = li && li.getAttribute('data-step-state');
      if (st === 'pending' || st === 'running') setStepState(s, 'done');
    });
    setResearchState('done');
  }

  function onError(message) {
    var banner = $('.research-error-banner', resultEl);
    if (banner) {
      banner.textContent = message || 'Error';
      banner.hidden = false;
    }
    setResearchState('error');
  }

  // Parse one SSE frame ("event: NAME\ndata: JSON"). Dispatch by event name.
  function parseFrame(raw) {
    if (!raw || !raw.trim()) return;
    var eventName = 'message';
    var dataLines = [];
    var lines = raw.split('\n');
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (line.indexOf('event:') === 0) {
        eventName = line.slice(6).trim();
      } else if (line.indexOf('data:') === 0) {
        dataLines.push(line.slice(5).replace(/^ /, ''));
      }
    }
    if (!dataLines.length) return;
    var payload;
    try {
      payload = JSON.parse(dataLines.join('\n'));
    } catch (err) {
      return; // ignore unparseable frame
    }
    if (eventName === 'done') {
      onDone(payload);
    } else if (eventName === 'error') {
      onError(payload && (payload.message || payload.type));
    } else if (STAGES.indexOf(eventName) >= 0) {
      onStageUpdate(eventName, payload);
    }
  }

  function submit(query, iterations) {
    resultEl = document.getElementById('research-result');
    if (!resultEl) return;
    var q = (query || '').trim();
    if (!q) return;
    var maxIter = parseInt(iterations, 10);
    if (!(maxIter >= 1 && maxIter <= 10)) maxIter = 3;

    resetSteps();
    setQuestionEcho(q);
    setResearchState('running');
    setStepState('web_baseline', 'running');

    fetch(base + '/api/research', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: q, max_iterations: maxIter })
    }).then(function (r) {
      if (!r.ok || !r.body) {
        onError('HTTP ' + r.status);
        return;
      }
      var reader = r.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      function pump() {
        return reader.read().then(function (chunk) {
          if (chunk.done) {
            // Flush any trailing complete frame.
            if (buffer.trim()) parseFrame(buffer);
            // If the stream ended without an explicit done/error, settle the UI.
            if (resultEl.getAttribute('data-research-state') === 'running') {
              setResearchState('done');
            }
            return;
          }
          buffer += decoder.decode(chunk.value, { stream: true });
          var frames = buffer.split('\n\n');
          buffer = frames.pop(); // keep the incomplete trailing frame
          frames.forEach(function (frame) { parseFrame(frame); });
          return pump();
        });
      }
      return pump();
    }).catch(function (err) {
      onError((err && err.message) || 'network error');
    });
  }

  window.KbResearch = { submit: submit };
})();
