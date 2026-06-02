---
plan_id: aim-5-5
phase: aim-5
wave: 2
depends_on:
  - aim-5-6
requirements_addressed:
  - STAB-05
files_modified:
  - .planning/phases/aim-5-stability-watch/aim-5-5-EVIDENCE.md
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-baseline.md
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-0.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-1.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-2.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-3.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-4.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-5.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-6.png
  - .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-7.png
autonomous: false
t_shirt: S
---

# aim-5-5 — STAB-05 Vertex AI quota readout (7-day window) + Hermes baseline

## Goal

Two-phase quota watch: at aim-5 day-0, capture the **Hermes-side
pre-migration monthly Vertex spend** (e.g., the 2026-04 Hermes-only
month) as the baseline. During day-1..7, capture daily snapshots of
**Aliyun-side Vertex spend** for the active milestone window. At day-7,
compute `7-day_aliyun × 4.3 ≤ baseline_hermes_monthly` for the
threshold verdict.

REQ STAB-05 verbatim
(`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 84):

> **STAB-05**: Vertex AI quota usage in the 7-day window does not
> exceed the pre-migration Hermes-side monthly baseline (extrapolated
> linearly: 7-day Aliyun spend × ~4.3 ≤ Hermes-side prior monthly
> Vertex spend). Measured via GCP project's "Quotas & System Limits"
> dashboard. §7 SC #5. Failure case: quota usage exceeds the linear
> projection by > 20% triggers operator review (PROJECT §6 Risk row 6
> cost-up alarm).

Per `aim-5-CONTEXT.md` FINDING 4, the dashboard URL pattern is
`https://console.cloud.google.com/iam-admin/quotas?project=<gcp-project-id>`
filtered by Service = "Vertex AI API"; Metric = "Generate content
requests" + "Embed content requests".

Per FINDING 1 (tolerance asymmetry): STAB-05 is "threshold (≤ baseline

+ 20%)". Threshold bust > 20% over linear projection → OPERATOR-REVIEW
(NOT auto-RESTART; per FINDING 1 row 5).

**autonomous: false** — this plan is the only `[operator-only]` task in
aim-5 because the GCP "Quotas & System Limits" dashboard is browser-side
(not exposed via gcloud CLI for Vertex AI quota usage with the same
fidelity). The agent CAN derive an approximation by querying GCP billing
API + Vertex AI logging, but the operator-supplied screenshot is the
authoritative artifact per REQ wording. Per FINDING 9, the agent labels
each task `[operator-only]` and emits prompts; operator captures and
saves screenshots into `aim-5-EVIDENCE/vertex-quota-day-N.png`.

## Acceptance criteria

1. **Day-0 Hermes baseline** captured in
   `.planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-baseline.md`:
   - Hermes-side GCP project ID (`<hermes-gcp-project>`)
   - Reference month for the baseline (e.g., 2026-04 — most recent
     full Hermes-only month before migration)
   - Total Vertex spend for that month: `$<X>` USD
   - Service breakdown: Generate content requests, Embed content
     requests, total
   - Screenshot at `aim-5-EVIDENCE/vertex-quota-day-0.png` showing
     Hermes-project Vertex spend for the reference month
2. **Daily Aliyun snapshots** captured at
   `aim-5-EVIDENCE/vertex-quota-day-N.png` for N in 1..7:
   - One screenshot per day from the Aliyun-side GCP project's
     "Quotas & System Limits" dashboard
   - Same filter: Vertex AI API; Generate + Embed content requests
   - Daily Aliyun spend captured in
     `aim-5-EVIDENCE/vertex-baseline.md` as a running 7-day cumulative
     tally
3. **Day-7 verdict** in `aim-5-5-EVIDENCE.md`:
   - 7-day Aliyun cumulative spend: `$<Y>`
   - Linear projection to monthly: `Y × 4.3 = $<Z>`
   - Hermes monthly baseline: `$<X>`
   - Verdict:
     - `Z ≤ X` → PASS
     - `X < Z ≤ X × 1.2` → PASS (within 20% tolerance band)
     - `Z > X × 1.2` → OPERATOR-REVIEW (PROJECT §6 Risk row 6 cost-up alarm)
4. **Failure-day handling**: per FINDING 1 row 5, > 20% over linear
   projection → OPERATOR-REVIEW (NOT auto-RESTART). Operator decides
   RESTART vs. continue; document decision in EVIDENCE.md.
5. `aim-5-5-EVIDENCE.md` records:
   - Day-0 Hermes baseline summary + screenshot path
   - Daily Aliyun spend table (Day | spend | running 7-day total | screenshot path)
   - Day-7 projection computation
   - Aggregate STAB-05 verdict: PASS / OPERATOR-REVIEW
6. Forward-only commits per CLAUDE.md 2026-05-15 #1. Two natural
   commit boundaries: (a) day-0 baseline + first daily screenshot,
   (b) day-7 verdict with all 7 screenshots. Daily commits MAY batch
   at operator's discretion.
7. **Cost guard:** if any single day's Aliyun spend deviates wildly
   from running average (e.g., 3× day-1 spend on day-3 with no
   ingest-volume justification), surface as immediate operator review
   even before day-7 — do not silently accumulate.

## Tasks

### Task 1 — Day-0 Hermes baseline capture `[operator-only]`

**`<read_first>`**

- `aim-5-CONTEXT.md` lines 360-371 (STAB-05 dashboard pattern)
- `aim-5-CONTEXT.md` FINDING 4 (baseline procedure — Hermes-side
  pre-migration monthly spend)
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` §6 Risk row 6
  (cost-up alarm threshold)

**`<acceptance_criteria>`**

- `vertex-baseline.md` exists with Hermes baseline summary.
- `vertex-quota-day-0.png` exists at correct path; image shows
  Hermes-project Vertex spend for the reference month.
- Reference month is documented (e.g., "2026-04 — last full Hermes-only
  month before aim-1 migration began").

**`<action>`**

Operator-driven step. Emit operator prompt:

```text
[OPERATOR PROMPT — aim-5-5 day-0 Hermes Vertex baseline capture]

Please open the GCP Console for the Hermes-side project:

  URL: https://console.cloud.google.com/iam-admin/quotas?project=<HERMES_GCP_PROJECT_ID>

Filter:
  - Service: "Vertex AI API"
  - Metrics: "Generate content requests" + "Embed content requests"
  - Time range: <REFERENCE_MONTH> (e.g., 2026-04-01 through 2026-04-30)

Capture:
  1. Screenshot of the dashboard showing the full month's totals.
     Save to:
     .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-0.png
  2. Total spend for the month in USD.
  3. Per-service breakdown if visible.

Reply with the numbers; agent will populate vertex-baseline.md.
```

After operator replies, agent authors `vertex-baseline.md`:

```markdown
# Vertex AI quota baseline + daily tally (aim-5-5)

## Hermes-side baseline (day-0 freeze)

- **GCP project:** `<hermes-gcp-project-id>`
- **Reference month:** <YYYY-MM>
- **Total Vertex AI spend:** $<X> USD
- **Service breakdown:**
  - Generate content requests: $<a>
  - Embed content requests: $<b>
  - Other Vertex services: $<c>
- **Screenshot:** `aim-5-EVIDENCE/vertex-quota-day-0.png`
- **Captured:** <day-0 ts ADT>

## Daily Aliyun snapshots (running tally)

| Day | Date (ADT) | Aliyun spend ($) | Running 7-day total ($) | Screenshot |
| --- | --- | --- | --- | --- |
| 1 | <ts> | <s_1> | <s_1> | day-1.png |
| 2 | <ts> | <s_2> | <s_1+s_2> | day-2.png |
| 3 | <ts> | ... | ... | day-3.png |
| 4 | <ts> | ... | ... | day-4.png |
| 5 | <ts> | ... | ... | day-5.png |
| 6 | <ts> | ... | ... | day-6.png |
| 7 | <ts> | <s_7> | <Y total> | day-7.png |

## Day-7 projection (computed at day-7)

- 7-day Aliyun total: $<Y>
- Linear projection to month: $<Y> × 4.3 = $<Z>
- Hermes baseline: $<X>
- Δ = Z - X = $<delta>
- % over baseline = (Z - X) / X × 100% = <pct>%

## Verdict

PASS / OPERATOR-REVIEW (per FINDING 1 row 5: > 20% over → OPERATOR-REVIEW)
```

Commit day-0:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-baseline.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-0.png
git status
git commit -m "docs(aim-5): Vertex AI day-0 Hermes baseline (aim-5-5)"
git log -1 --name-only
```

### Task 2 — Daily Aliyun snapshot (day 1..7) `[operator-only]`

**`<read_first>`**

- `vertex-baseline.md` (table to update)
- `aim-5-CONTEXT.md` lines 360-371 (dashboard URL pattern)

**`<acceptance_criteria>`**

- For each day N in 1..7, `vertex-quota-day-N.png` exists at correct
  path.
- `vertex-baseline.md` table is updated with that day's spend +
  cumulative running total.
- Acceptance commit-cadence: per-day OR batched at day-7 (operator
  discretion); each daily entry MUST appear by day-7 close.

**`<action>`**

Operator prompt per day:

```text
[OPERATOR PROMPT — aim-5-5 day N Vertex spend snapshot]

Please open:

  URL: https://console.cloud.google.com/iam-admin/quotas?project=<ALIYUN_GCP_PROJECT_ID>

Filter:
  - Service: "Vertex AI API"
  - Metrics: "Generate content requests" + "Embed content requests"
  - Time range: today (last 24h)

Capture:
  1. Screenshot saved to:
     .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-<N>.png
  2. 24h spend total for the Aliyun project.

Reply with the spend value; agent will append to vertex-baseline.md table.
```

After operator replies, agent uses the `Edit` tool to append the row to
the daily Aliyun snapshots table in `vertex-baseline.md` and increment
the running 7-day total.

Cost-spike guard (each day, before appending):

```bash
# After day 3+, compute running average and flag spikes
PREV_AVG=<average of days 1..N-1>
DAY_N=<today's spend>
if [ "$(echo "$DAY_N > 3 * $PREV_AVG" | bc -l)" -eq 1 ]; then
  echo "WARN: day $N spend ($DAY_N) is > 3× running average ($PREV_AVG)"
  echo "      surface to operator review immediately, do NOT wait for day-7"
fi
```

If a spike is flagged, document the spike + investigation in
`vertex-baseline.md` table notes column.

### Task 3 — Day-7 verdict + aim-5-5-EVIDENCE.md `[agent-runnable]`

**`<read_first>`**

- `vertex-baseline.md` (full populated table day-1..7)
- `aim-5-CONTEXT.md` FINDING 1 (threshold-based: > 20% → OPERATOR-REVIEW)
- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` §6 Risk row 6

**`<acceptance_criteria>`**

- `vertex-baseline.md` "Day-7 projection" section is fully populated.
- `aim-5-5-EVIDENCE.md` exists with summary table + projection +
  aggregate verdict.
- Single forward-only commit on `main` containing:
  - `vertex-baseline.md` (final populated)
  - `aim-5-5-EVIDENCE.md`
  - All `vertex-quota-day-N.png` files for N in 1..7 (if not already
    committed daily)
- Conventional commit message: `docs(aim-5): STAB-05 7-day Vertex quota verdict (aim-5-5)`.
- `git status` clean post-commit.

**`<action>`**

Compute projection from `vertex-baseline.md` table:

```bash
# Pseudo-extraction — agent does this with a small inline script
TOTAL_7D=$(awk -F'|' '/^| 7 /{print $5}' vertex-baseline.md)   # last "running total" value
PROJECTION=$(echo "$TOTAL_7D * 4.3" | bc -l)
HERMES_BASELINE=$(grep "Total Vertex AI spend" vertex-baseline.md | grep -oE '\$[0-9.]+' | head -1)
DELTA=$(echo "$PROJECTION - $HERMES_BASELINE" | bc -l)
PCT_OVER=$(echo "($PROJECTION - $HERMES_BASELINE) / $HERMES_BASELINE * 100" | bc -l)

# Verdict logic
if [ "$(echo "$PROJECTION <= $HERMES_BASELINE" | bc -l)" -eq 1 ]; then
  VERDICT="PASS"
elif [ "$(echo "$PROJECTION <= $HERMES_BASELINE * 1.2" | bc -l)" -eq 1 ]; then
  VERDICT="PASS (within 20% tolerance)"
else
  VERDICT="OPERATOR-REVIEW (> 20% over baseline; PROJECT §6 Risk row 6)"
fi
```

Then author `aim-5-5-EVIDENCE.md`:

```markdown
# aim-5-5 — STAB-05 7-day Vertex AI quota evidence

**Timestamp:** <day-7 ts>
**Plan:** aim-5-5
**REQs:** STAB-05
**Status:** PASS / OPERATOR-REVIEW

## Day-0 Hermes baseline

- GCP project: <hermes-gcp-project>
- Reference month: <YYYY-MM>
- Hermes monthly Vertex spend: $<X>
- Screenshot: `aim-5-EVIDENCE/vertex-quota-day-0.png`

## Daily Aliyun spend (7-day window)

| Day | Date (ADT) | Spend ($) | Running total ($) | Screenshot |
| --- | --- | --- | --- | --- |
| 1 | <ts> | <s_1> | <s_1> | day-1.png |
| 2 | <ts> | <s_2> | <total> | day-2.png |
| 3 | <ts> | ... | ... | day-3.png |
| 4 | <ts> | ... | ... | day-4.png |
| 5 | <ts> | ... | ... | day-5.png |
| 6 | <ts> | ... | ... | day-6.png |
| 7 | <ts> | <s_7> | <Y total> | day-7.png |

## Linear projection

- 7-day Aliyun total: $<Y>
- × 4.3 = $<Z> (extrapolated to monthly)
- Hermes baseline: $<X>
- Δ = $<delta> (<pct>% over baseline)

## Aggregate verdict

**STAB-05:** <PASS / OPERATOR-REVIEW>

(Decision per FINDING 1 row 5: ≤ baseline → PASS; ≤ baseline × 1.2 →
PASS; > baseline × 1.2 → OPERATOR-REVIEW per PROJECT §6 Risk row 6
cost-up alarm.)

## Cost-spike notes

(Document any flagged single-day spikes and investigation results.)

## References

- REQUIREMENTS STAB-05 (line 84)
- aim-5 CONTEXT FINDING 1 + FINDING 4
- PROJECT §6 Risk row 6 (cost-up alarm)
- `aim-5-EVIDENCE/vertex-baseline.md` (full daily table)
- `aim-5-EVIDENCE/vertex-quota-day-{0..7}.png` (8 screenshots)
```

Commit:

```bash
git add .planning/phases/aim-5-stability-watch/aim-5-5-EVIDENCE.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-baseline.md \
        .planning/phases/aim-5-stability-watch/aim-5-EVIDENCE/vertex-quota-day-*.png
git status
git commit -m "docs(aim-5): STAB-05 7-day Vertex quota verdict (aim-5-5)"
git log -1 --name-only
```

## Risk and mitigation

| Risk | Mitigation |
| ---- | ---------- |
| Operator forgets a daily screenshot → mid-window gap | Surface gap honestly in vertex-baseline.md; agent CAN approximate from GCP billing API for the missed day if dashboard is unavailable retroactively (`gcloud billing invoices` or BigQuery billing export); document approximation source |
| `× 4.3` extrapolation is mathematically simplistic — assumes uniform daily spend | This is the explicit REQ wording (line 84); deviations from uniformity are accepted as part of the linear projection. Cost-spike guard catches non-uniform days. |
| Hermes-side reference month is itself unrepresentative (e.g., low-volume month before migration) | Pick the most recent full-month before aim-1 migration started; document choice rationale in `vertex-baseline.md`. If two candidate months differ > 30%, prefer the higher (conservative — favors PASS) |
| Aliyun GCP project ID not yet documented | Resolve from aim-1 / aim-2 evidence (`OMNIGRAPH_GCP_PROJECT` env var on Aliyun) or via `gcloud config get-value project` over SSH |
| Threshold bust > 20% on day-7 → operator decides RESTART vs. continue | OPERATOR-REVIEW is NOT auto-RESTART per FINDING 1 row 5; aim-5-5 captures the data, operator owns the decision; document decision + rationale in EVIDENCE.md |
| Forward-only commit discipline broken by `git commit --amend` after operator-supplied screenshot lands | Per CLAUDE.md 2026-05-15 #1 + memory `feedback_no_amend_in_concurrent_quicks.md`: NEVER amend; if a screenshot is wrong, commit a new corrected file with sibling name (`vertex-quota-day-N-correction.png`) and document |
| Cost-spike on day N (3× running average) | Surface immediate operator review before day-7; do not silently accumulate. Flag in vertex-baseline.md notes column with timestamp + suspected cause. |

## Evidence

- `aim-5-EVIDENCE/vertex-baseline.md` — Hermes baseline + daily Aliyun
  tally + day-7 projection
- `aim-5-EVIDENCE/vertex-quota-day-{0..7}.png` — 8 screenshots
- `aim-5-5-EVIDENCE.md` — summary + aggregate verdict
- Two (or more) forward-only commits on `main`
