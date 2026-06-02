---
plan_id: aim-5-4
phase: aim-5
wave: 2
depends_on:
  - aim-5-6
requirements_addressed:
  - STAB-04
files_modified:
  - .planning/phases/aim-5-stability-watch/aim-5-4-EVIDENCE.md
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-day7-verdict.md
autonomous: true
t_shirt: S
---

# aim-5-4 — STAB-04 kb-api regression probes (day-0 baseline + day-7 verdict)

## Goal

Two-phase regression watch on the Aliyun kb-api: at aim-5 day-0,
freeze a baseline (article count + 3 known hashes + 1 known FTS query)
into `kb-api-baseline-day0.json`. At day-7, re-curl all probes and
assert no regression. Crucially, **also probe `/api/synthesize` and
require it returns ≠ 200** as a hard-fail discipline for Decision 4 /
Q5c (kb-api scope unchanged in aim-5; `/api/synthesize` is owned by
Agentic-RAG-v1, NOT Aliyun-Ingest-Migration-v1).

REQ STAB-04 verbatim
(`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 83):

> **STAB-04**: kb-api on Aliyun has no behavioral regression vs.
> pre-migration baseline. Verify: `curl -s
> http://<aliyun>/api/articles | jq '. | length'` matches pre-migration
> count (or grows monotonically as Aliyun ingest adds articles); `curl
> -s http://<aliyun>/api/article/<known-hash>` returns 200 with same
> body shape; `curl -s
> http://<aliyun>/api/search?mode=fts&q=<known>` returns expected hit.
> §7 SC #6 + Decision 4 (kb-api scope unchanged — no
> `/api/synthesize` introduced).

Per `aim-5-CONTEXT.md` FINDING 5, "pre-migration count" is anchored at
aim-5 day-0 (= aim-4 close + 1 day grace, ~2026-05-25). Monotonic
growth is acceptable; shape regression is not.

Per `aim-5-CONTEXT.md` lines 121-124, the Decision 4 / Q5c discipline
is a hard fail: if `/api/synthesize` returns 200, the kb-api scope was
violated → Agentic-RAG-v1 milestone leaked into Aliyun-Ingest-Migration-v1
→ STAB-04 FAIL.

Per FINDING 1 (tolerance asymmetry): STAB-04 is "continuous — one
regression breaks PASS". One regression = STAB-04 FAIL = aim-5 RESTART.

Per FINDING 9, all probes are read-only HTTP curl — `[agent-runnable]`.
Aliyun host endpoint resolved from memory `aliyun_vitaclaw_ssh.md`
(host `101.133.154.49` — though kb-api may be exposed on a different
public-facing host/port; planner: confirm via aim-3 cutover evidence).

## Acceptance criteria

1. **Day-0 baseline** captured in
   `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json`
   with:
   - `article_count` from `/api/articles | jq '. | length'`
   - `known_hashes` array of 3 hashes (sampled from `/api/articles | jq '.[0:3] | map(.hash)'`)
   - `known_fts_query` (1 representative term that returns ≥ 1 hit at
     day-0 — sourced from a sample article title or known content)
   - `aliyun_kb_api_endpoint` (URL captured at day-0; documents the
     host/port resolution for day-7 reuse)
   - `day0_timestamp` (ADT + UTC)
2. **Day-7 verdict** captured in
   `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-day7-verdict.md`:
   - Re-curl `/api/articles` and assert article_count ≥ baseline (monotonic; growth OK)
   - Re-curl `/api/article/<hash>` for each of the 3 known hashes; assert HTTP 200 with parseable JSON body
   - Re-curl `/api/search?mode=fts&q=<known_fts_query>` and assert ≥ 1 result
   - Re-curl `/api/synthesize` and assert HTTP code **≠ 200**
     (expect 404 / 405 / 501 / "not implemented" — anything other
     than 200; per Decision 4 / Q5c hard-fail discipline)
3. **Pass criterion (all four must hold):**
   - `article_count_day7 ≥ article_count_day0`
   - all 3 hash probes return 200 with valid JSON body
   - FTS query returns ≥ 1 hit
   - `/api/synthesize` returns code ≠ 200
4. **Failure-day tolerance: continuous** (per FINDING 1) — ONE
   regression on any of the 4 probes breaks PASS. STAB-04 FAIL = aim-5
   RESTART.
5. `aim-5-4-EVIDENCE.md` records:
   - Day-0 baseline file path + contents summary
   - Day-7 probe results table
   - Aggregate STAB-04 verdict: PASS / FAIL
   - Decision 4 / Q5c discipline outcome (synthesize endpoint code)
6. Forward-only commits per CLAUDE.md 2026-05-15 #1. Two natural commit
   boundaries: (a) day-0 baseline freeze, (b) day-7 verdict.
7. The `kb-api-baseline-day0.json` file is treated as **immutable**
   after day-0 freeze. Any post-day-0 edit is a forward-only correction
   commit on a sibling file (e.g., add a `kb-api-baseline-day0-correction.md`),
   never an in-place edit of the frozen JSON.

## Tasks

### Task 1 — Day-0 baseline capture `[agent-runnable]`

**`<read_first>`**

- `aim-5-CONTEXT.md` lines 337-358 (STAB-04 baseline + day-7 probes)
- `aim-5-CONTEXT.md` FINDING 5 (baseline anchor procedure)
- Memory `aliyun_vitaclaw_ssh.md` (host details — note: kb-api may be
  exposed on a different host/port from SSH; agent must resolve at
  day-0 from aim-3 cutover evidence files in
  `.planning/phases/aim-3-cutover/`)
- aim-3 cutover evidence (any file documenting kb-api endpoint URL)

**`<acceptance_criteria>`**

- `kb-api-baseline-day0.json` exists with the 5 fields specified above.
- `article_count` is a positive integer.
- `known_hashes` array has exactly 3 elements, each a non-empty string
  matching the kb-api hash format.
- `known_fts_query` returns ≥ 1 hit at day-0 (sanity-checked at freeze
  time).
- File is committed in a single forward-only commit on `main` with
  message `docs(aim-5): kb-api day-0 baseline freeze (aim-5-4)`.

**`<action>`**

Resolve the kb-api endpoint first. The agent inspects aim-3 cutover
evidence:

```bash
grep -rE "kb-api|/api/articles|aliyun.*:[0-9]+" \
  .planning/phases/aim-3-cutover/ 2>&1 | head -20
```

If endpoint URL is found (e.g., `http://101.133.154.49:8766` or
`https://kb.<aliyun-public-domain>`), use it. If not, resolve via
aim-2 / aim-1 evidence or query Aliyun via SSH:

```bash
ssh aliyun-vitaclaw '
  systemctl status kb-api.service 2>&1 | head -5
  ss -tlnp | grep -E "8766|8080|443|80" | head -5
'
```

Then capture baseline:

```bash
ENDPOINT="http://<resolved-host>:<port>"   # e.g., http://101.133.154.49:8766
BASELINE=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json
mkdir -p "$(dirname "$BASELINE")"

# Capture article count
ARTICLE_COUNT=$(curl -s "$ENDPOINT/api/articles" | jq '. | length')
echo "article_count_day0=$ARTICLE_COUNT"

# Capture 3 known hashes (planner: pick deterministically — first 3 of /api/articles list)
KNOWN_HASHES=$(curl -s "$ENDPOINT/api/articles" | jq '.[0:3] | map(.hash)')
echo "known_hashes=$KNOWN_HASHES"

# Identify a known FTS query (planner: derive from sample article title)
SAMPLE_TITLE=$(curl -s "$ENDPOINT/api/articles" | jq -r '.[0].title // empty')
# Pick a representative single word from sample title or use a known domain term
KNOWN_FTS_QUERY="<derived from sample title or known KB term>"

# Sanity-check the FTS query returns ≥ 1 hit
FTS_HIT_COUNT=$(curl -s "$ENDPOINT/api/search?mode=fts&q=$KNOWN_FTS_QUERY" | jq '. | length')
[ "$FTS_HIT_COUNT" -ge 1 ] || { echo "ERROR: FTS query returns 0 hits at day-0; pick another"; exit 1; }

# Author baseline JSON
cat > "$BASELINE" <<EOF
{
  "aliyun_kb_api_endpoint": "$ENDPOINT",
  "day0_timestamp_adt": "$(date '+%Y-%m-%d %H:%M:%S %Z')",
  "day0_timestamp_utc": "$(date -u '+%Y-%m-%d %H:%M:%S UTC')",
  "article_count": $ARTICLE_COUNT,
  "known_hashes": $KNOWN_HASHES,
  "known_fts_query": "$KNOWN_FTS_QUERY",
  "fts_hit_count_day0": $FTS_HIT_COUNT
}
EOF

cat "$BASELINE"
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json
git status
git commit -m "docs(aim-5): kb-api day-0 baseline freeze (aim-5-4)"
git log -1 --name-only
```

### Task 2 — Day-7 verdict probe `[agent-runnable]`

**`<read_first>`**

- `kb-api-baseline-day0.json` (the frozen baseline from Task 1)
- `aim-5-CONTEXT.md` lines 121-124 (Decision 4 / Q5c hard-fail
  discipline on `/api/synthesize`)
- `aim-5-CONTEXT.md` FINDING 1 (continuous tolerance — one regression
  = FAIL)

**`<acceptance_criteria>`**

- `kb-api-day7-verdict.md` exists at
  `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-day7-verdict.md`
  with:
  - All 4 probe results (article count, 3 hash probes, FTS query,
    synthesize probe)
  - Comparison vs. day-0 baseline (delta + monotonic check)
  - Aggregate verdict: PASS / FAIL
  - Decision 4 / Q5c discipline outcome line

**`<action>`**

Run on day-7:

```bash
ENDPOINT=$(jq -r .aliyun_kb_api_endpoint .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json)
BASELINE_COUNT=$(jq -r .article_count .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json)
KNOWN_HASHES=$(jq -r '.known_hashes | .[]' .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json)
KNOWN_FTS=$(jq -r .known_fts_query .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-baseline-day0.json)

VERDICT=.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-day7-verdict.md

{
  echo "# kb-api day-7 verdict"
  echo ""
  echo "**Timestamp:** $(date '+%Y-%m-%d %H:%M:%S %Z') / $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
  echo "**Endpoint:** $ENDPOINT"
  echo ""

  # Probe 1: article count (monotonic)
  echo "## Probe 1: /api/articles count"
  COUNT_DAY7=$(curl -s "$ENDPOINT/api/articles" | jq '. | length')
  echo "- day-0 baseline: $BASELINE_COUNT"
  echo "- day-7 actual: $COUNT_DAY7"
  if [ "$COUNT_DAY7" -ge "$BASELINE_COUNT" ]; then
    echo "- verdict: ✅ PASS (monotonic)"
  else
    echo "- verdict: ❌ FAIL (article count regressed)"
  fi
  echo ""

  # Probe 2: 3 known-hash GETs
  echo "## Probe 2: known-hash article GETs"
  HASH_FAIL=0
  for h in $KNOWN_HASHES; do
    CODE=$(curl -s -o /dev/null -w "%{http_code}" "$ENDPOINT/api/article/$h")
    BODY_VALID=$(curl -s "$ENDPOINT/api/article/$h" | jq -e . >/dev/null 2>&1 && echo "yes" || echo "no")
    echo "- hash $h → HTTP $CODE, JSON valid: $BODY_VALID"
    if [ "$CODE" != "200" ] || [ "$BODY_VALID" != "yes" ]; then
      HASH_FAIL=$((HASH_FAIL + 1))
    fi
  done
  if [ "$HASH_FAIL" -eq 0 ]; then
    echo "- verdict: ✅ PASS (3/3 hashes return 200 with valid JSON)"
  else
    echo "- verdict: ❌ FAIL ($HASH_FAIL/3 hashes regressed)"
  fi
  echo ""

  # Probe 3: FTS query
  echo "## Probe 3: FTS query"
  FTS_HITS=$(curl -s "$ENDPOINT/api/search?mode=fts&q=$KNOWN_FTS" | jq '. | length')
  echo "- query: $KNOWN_FTS"
  echo "- hits: $FTS_HITS"
  if [ "$FTS_HITS" -ge 1 ]; then
    echo "- verdict: ✅ PASS (≥ 1 hit)"
  else
    echo "- verdict: ❌ FAIL (FTS query returned 0 hits)"
  fi
  echo ""

  # Probe 4: Decision 4 / Q5c — /api/synthesize MUST NOT exist
  echo "## Probe 4: /api/synthesize discipline (Decision 4 / Q5c)"
  SYNTHESIZE_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$ENDPOINT/api/synthesize")
  echo "- HTTP code: $SYNTHESIZE_CODE"
  if [ "$SYNTHESIZE_CODE" != "200" ]; then
    echo "- verdict: ✅ PASS (≠ 200; kb-api scope unchanged per Decision 4)"
  else
    echo "- verdict: ❌ FAIL (200; Agentic-RAG-v1 leaked into aim-5 — milestone scope violation)"
  fi
  echo ""

  echo "## Aggregate STAB-04 verdict"
  echo ""
  echo "PASS / FAIL (all 4 probes must PASS)"
} > "$VERDICT"

cat "$VERDICT"
```

### Task 3 — aim-5-4-EVIDENCE.md `[agent-runnable]`

**`<read_first>`**

- `kb-api-baseline-day0.json` + `kb-api-day7-verdict.md` (sources)
- `aim-5-CONTEXT.md` FINDING 1 + lines 121-124

**`<acceptance_criteria>`**

- `aim-5-4-EVIDENCE.md` summarizes:
  - Day-0 baseline path + key fields
  - Day-7 probe table
  - Aggregate STAB-04 verdict
  - Decision 4 / Q5c discipline outcome
- Single forward-only commit on `main` containing
  `kb-api-day7-verdict.md` + `aim-5-4-EVIDENCE.md`.
- Conventional commit message: `docs(aim-5): STAB-04 day-7 verdict (aim-5-4)`.
- `git status` clean post-commit.

**`<action>`**

Author `aim-5-4-EVIDENCE.md`:

```markdown
# aim-5-4 — STAB-04 kb-api regression evidence

**Timestamp:** <day-7 ts>
**Plan:** aim-5-4 (Wave 1 day-0 baseline + Wave 3 day-7 verdict)
**REQs:** STAB-04
**Status:** PASS / FAIL

## Day-0 baseline

- File: `aim-5-EVIDENCE/kb-api-baseline-day0.json`
- Endpoint: <from baseline>
- article_count: <N>
- known_hashes: [<h1>, <h2>, <h3>]
- known_fts_query: "<term>"
- Frozen at: <day-0 ts>

## Day-7 probes

| Probe | Result | Verdict |
| --- | --- | --- |
| /api/articles count | <N_day7> (≥ <N_day0>) | ✅/❌ |
| /api/article/<h1> | HTTP <code>, JSON valid <yes/no> | ✅/❌ |
| /api/article/<h2> | ... | ✅/❌ |
| /api/article/<h3> | ... | ✅/❌ |
| /api/search?mode=fts&q=<term> | <hits> hits | ✅/❌ |
| /api/synthesize (Decision 4 / Q5c) | HTTP <code> (≠ 200 = PASS) | ✅/❌ |

## Decision 4 / Q5c discipline

`/api/synthesize` returned HTTP <code>.

- ≠ 200 → PASS — kb-api scope unchanged; Agentic-RAG-v1 did NOT leak
  into Aliyun-Ingest-Migration-v1 milestone scope.
- = 200 → FAIL — milestone scope violation; aim-5 RESTART; remove
  `/api/synthesize` deployment from Aliyun before re-attempting.

## Aggregate verdict

**STAB-04:** PASS (all 4 probes PASS) / FAIL (any single regression breaks PASS)

## References

- REQUIREMENTS STAB-04 (line 83)
- aim-5 CONTEXT FINDING 1 + FINDING 5
- aim-5 CONTEXT lines 121-124 (Decision 4 / Q5c)
- `aim-5-EVIDENCE/kb-api-baseline-day0.json` (frozen baseline)
- `aim-5-EVIDENCE/kb-api-day7-verdict.md` (day-7 raw probe output)
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-4-EVIDENCE.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/kb-api-day7-verdict.md
git status
git commit -m "docs(aim-5): STAB-04 day-7 verdict (aim-5-4)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| kb-api endpoint host/port not documented in aim-3 cutover evidence | Resolve via SSH to Aliyun: `systemctl status kb-api.service` + `ss -tlnp` for listening port; capture endpoint into `kb-api-baseline-day0.json` and reference at day-7 |
| `/api/articles` returns paginated response (not full list) → article_count is page-size, not total | Inspect response shape at day-0; if paginated, capture pagination params + use the same query at day-7. Document in baseline JSON. |
| Known FTS query returns 0 hits at day-0 (no obvious sample term) | Sanity-check at freeze time; if no term yields ≥ 1 hit, pick from `/api/articles | jq '.[0].title' | head -1` and use a representative substring |
| 3 known hashes are deleted/garbage-collected between day-0 and day-7 | Pick hashes from the **oldest** articles (least likely to be GC'd); document the pick rationale in baseline JSON. If a hash regresses on day-7, distinguish "deleted" (operational expected) from "404 due to bug" (regression). |
| `/api/synthesize` returns 200 with stub body — accidental introduction | Hard-fail per Decision 4 / Q5c; investigate which milestone shipped the endpoint; revert before resuming aim-5 |
| Endpoint changes between day-0 and day-7 (e.g., port migration) | Day-0 captures endpoint into JSON; if endpoint changes, document in EVIDENCE.md as a sub-pass condition (re-resolve endpoint, re-run all 4 probes against new endpoint) |
| Forward-only commit discipline broken | Per CLAUDE.md 2026-05-15 #1: NEVER amend; per acceptance criterion #7 the day-0 JSON is immutable post-freeze |

## Evidence

- `aim-5-EVIDENCE/kb-api-baseline-day0.json` — frozen day-0 baseline
- `aim-5-EVIDENCE/kb-api-day7-verdict.md` — day-7 raw probe output
- `aim-5-4-EVIDENCE.md` — summary + aggregate verdict
- Two forward-only commits on `main` (day-0 freeze + day-7 verdict)
