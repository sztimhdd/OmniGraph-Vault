# Phase 14: Regression Test Fixtures (B3) - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning
**Source:** PRD Express Path (`.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B3)

<domain>
## Phase Boundary

**Delivers:** 5 fixture profiles covering distinct article characteristics + `validate_regression_batch.py` script producing `batch_validation_report.json`. Core artifacts:
1. **4 new fixture directories** under `test/fixtures/`: `sparse_image_article/`, `dense_image_article/`, `text_only_article/`, `mixed_quality_article/` (the 5th, `gpt55_article/`, already exists from Milestone A)
2. **`scripts/validate_regression_batch.py`** — CLI that runs ingest on multiple fixtures + produces JSON report
3. **`batch_validation_report.json` schema** matching PRD §B3.4 verbatim
4. **Exit code contract**: 0 on all-pass, 1 on any failure (CI-ready)

**Does NOT deliver:**
- Changes to ingest logic itself (Phase 12 + 13 own that)
- CI/CD pipeline configuration (this phase delivers the script; CI integration is operator/devops task)
- New fixtures beyond the 5 specified (deferred)
- Automated fixture generation (fixtures are hand-curated for coverage)

**Dependency:** Phase 12 (checkpoint infra for resume semantics), Phase 13 (cascade for provider_usage reporting), v3.1 Phase 11 (bench harness pattern + `benchmark_result.json` schema — partial overlap; this phase reuses where applicable but produces a distinct BATCH report).

</domain>

<decisions>
## Implementation Decisions (from PRD §B3)

### Fixture Profiles (REGR-01) — LOCKED from PRD §B3.1

| Name | Image Count | Text Length | Characteristics | Hermes Issue Covered |
|------|-------------|-------------|-----------------|----------------------|
| `gpt55_article` | 28 | 4574 chars | Complex (baseline, from Milestone A) | — (already exists) |
| `sparse_image_article` | 3 | 8000 chars | Few images, long text (timeout @ LLM path) | Original #5, New #2 |
| `dense_image_article` | 45 | 2000 chars | Many small images (<300px filter) | Original #2, #6, New #1 |
| `text_only_article` | 0 | 3000 chars | No images (skip Vision entirely) | Edge case |
| `mixed_quality_article` | 15 | 5000 chars | Mix of JPEG/PNG, some corrupted (fallback) | Vision cascade coverage |

**Fixture acquisition strategy:**
- Source real WeChat articles matching each profile if available (avoid synthetic content that doesn't trigger real-world parse edge cases)
- For `mixed_quality_article`: include 2-3 intentionally corrupted images (truncated JPEG, oversized PNG header) to exercise Phase 13 cascade error paths
- For `dense_image_article`: seed with an article that has many 100×800 narrow banners (exercises v3.1 Phase 8 IMG-01 filter fix)
- For `text_only_article`: seed with an article that has zero images or only 1×1 tracking pixels (to be filtered)
- Archive the raw HTML + image files so fixtures are deterministic across machines

### Fixture Layout (REGR-02) — LOCKED

Each fixture directory schema (matches existing `test/fixtures/gpt55_article/` layout):

```
test/fixtures/{fixture_name}/
├── metadata.json       # Required; see schema below
├── article.md          # Rendered Markdown of article (scraped offline)
├── article.html        # Optional: raw HTML source
└── images/
    ├── img_000.jpg
    ├── img_001.png
    ├── ...
    └── manifest.json   # Optional: per-image expected dimensions + filter-expected flag
```

**metadata.json schema (LOCKED from PRD §B3.2):**
```json
{
  "title": "...",
  "url": "...",
  "text_chars": 0000,
  "total_images_raw": 00,
  "images_after_filter": 00,
  "expected_chunks": 00,
  "expected_entities": 00,
  "notes": "..."
}
```

- `text_chars`: exact character count of `article.md` (sanity check)
- `total_images_raw`: count of files in `images/` dir
- `images_after_filter`: expected count after IMG-01 filter applied (`min(w,h) >= 300`)
- `expected_chunks`: LightRAG chunk count post-ingest (for assertion against `batch_validation_report.json` counters)
- `expected_entities`: entity count extracted from article (ballpark; planner chooses tolerance ±10%)
- `notes`: what this fixture specifically exercises

### Validation Script (REGR-03) — LOCKED

**CLI signature (LOCKED from PRD §B3.3):**
```bash
python scripts/validate_regression_batch.py \
  --fixtures test/fixtures/gpt55_article \
              test/fixtures/sparse_image_article \
              test/fixtures/dense_image_article \
              test/fixtures/text_only_article \
  --output batch_validation_report.json
```

**Behavior:**
1. For each fixture: ingest via the batch pipeline (exercising Phase 12 checkpoint + Phase 13 cascade)
2. Collect per-stage timings + counters + provider usage
3. Compare against `metadata.json` expected values (tolerance ±10% for fuzzy counts, exact for total_images_raw)
4. Emit `batch_validation_report.json` per schema (see REGR-04)
5. Exit 0 if all `articles[].status == "PASS"`; exit 1 if any FAIL or TIMEOUT

**Ingest mode:**
- Use fixture-based ingest path (no live WeChat scrape); mirror v3.1 Phase 11 pattern (`scripts/benchmark_single_article.py`)
- Reuse checkpoint directory for resume semantics; fresh-run per fixture (delete checkpoint before each fixture test)

### Report Schema (REGR-04) — LOCKED VERBATIM from PRD §B3.4

```json
{
  "batch_id": "regression_2026-05-01_001",
  "timestamp": "2026-05-01T14:30:00Z",
  "articles": [
    {
      "fixture": "gpt55_article",
      "status": "PASS|FAIL|TIMEOUT",
      "timings_ms": {
        "scrape": 0,
        "classify": 1234,
        "image_filter": 45,
        "text_ingest": 12345,
        "vision_worker_start": 100
      },
      "counters": {
        "images_input": 28,
        "images_kept": 22,
        "chunks": 15,
        "entities": 47
      },
      "errors": []
    }
  ],
  "aggregate": {
    "total_articles": 5,
    "passed": 5,
    "failed": 0,
    "total_wall_time_s": 72,
    "batch_pass": true
  },
  "provider_usage": {
    "siliconflow": 110,
    "openrouter": 0,
    "gemini": 0
  }
}
```

**Status enum:**
- `PASS` — all counters within ±10% of expected, all stages completed
- `FAIL` — any counter outside tolerance OR any exception raised
- `TIMEOUT` — `asyncio.wait_for` killed the article (bubbled from Phase 9 single-article timeout)

### CI Integration Readiness (REGR-05) — LOCKED

- Script exit code 0 on all-pass, 1 on any failure → usable in `pytest`/GitHub Actions `run:` step directly
- `batch_validation_report.json` saved to a predictable path (default CWD; `--output` overrides); CI can diff across runs for trend analysis
- Report includes `batch_id` timestamped for uniqueness; CI can archive per-run reports

### Claude's Discretion

- **Fixture content source** (which specific WeChat articles to use) — planner picks; must satisfy profile constraints
- **Tolerance thresholds** (±10% is default, but planner can tighten for deterministic counters like `total_images_raw`)
- **Fixture file size** — image content should be real (not placeholder); planner trims to minimum viable size (e.g., JPEG quality 70%)
- **Test execution parallelism** — planner decides if fixtures run sequentially or in parallel (batch ingest may have concurrency limits)
- **Mock harness** — for `mixed_quality_article`, planner decides whether to use real corrupted images or synthesize them in-test

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source of Truth
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §B3 — verbatim requirements
- `.planning/MILESTONE_v3.2_REQUIREMENTS.md` §Acceptance Criteria Gate 3 — end-to-end acceptance

### Dependency Interfaces
- Phase 12 `lib/checkpoint.py` + `scripts/checkpoint_reset.py` — reset fixture checkpoints before each test run
- Phase 13 `lib/vision_cascade.py` — cascade provides `provider_usage` metrics for the report
- v3.1 Phase 11 `scripts/benchmark_single_article.py` — reference pattern for fixture-based ingest + report emission
- v3.1 Phase 11 `benchmark_result.json` schema — SINGLE-article schema; Phase 14 adds BATCH-level aggregation on top

### Existing Assets to Read
- `test/fixtures/gpt55_article/` — baseline fixture (already complete from Milestone A)
- `test/fixtures/gpt55_article/metadata.json` — schema reference
- `scripts/benchmark_single_article.py` (if v3.1 Phase 11 delivered) — reuse CLI patterns, timing capture, error handling

### External Dependencies (planner researches)
- WeChat article URLs matching each profile (or synthesize — planner's call)
- Image corruption tools (e.g., `truncate` command or Python `struct.pack` to mangle JPEG headers for `mixed_quality_article`)

</canonical_refs>

<specifics>
## Specific Ideas

### Script Skeleton (illustrative)

```python
#!/usr/bin/env python
"""Run regression ingestion against a batch of fixtures; emit JSON report.

Usage:
  python scripts/validate_regression_batch.py \
    --fixtures test/fixtures/gpt55_article test/fixtures/sparse_image_article ... \
    --output batch_validation_report.json
"""

import argparse, json, time, uuid
from datetime import datetime, timezone
from pathlib import Path

from lib.checkpoint import reset_article, get_article_hash  # Phase 12
from lib.vision_cascade import VisionCascade  # Phase 13
from ingest_wechat import ingest_article_from_fixture  # to be added as fixture entry point

def run_fixture(fixture_dir: Path, rag, cascade) -> dict:
    meta = json.loads((fixture_dir / "metadata.json").read_text())
    url = meta["url"]
    article_hash = get_article_hash(url)
    reset_article(article_hash)  # Clean checkpoint for each fixture run

    t_start = time.time()
    try:
        result = ingest_article_from_fixture(fixture_dir, rag=rag, cascade=cascade)
        status = "PASS" if within_tolerance(result, meta) else "FAIL"
    except TimeoutError:
        status = "TIMEOUT"
        result = {}
    except Exception as e:
        status = "FAIL"
        result = {"error": str(e)}

    return {
        "fixture": fixture_dir.name,
        "status": status,
        "timings_ms": result.get("timings_ms", {}),
        "counters": result.get("counters", {}),
        "errors": result.get("errors", [result["error"]] if "error" in result else []),
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", nargs="+", required=True, type=Path)
    parser.add_argument("--output", default="batch_validation_report.json")
    args = parser.parse_args()

    rag = get_rag(flush=True)  # Phase 9 API
    cascade = VisionCascade(...)

    articles = [run_fixture(fix, rag, cascade) for fix in args.fixtures]
    passed = sum(1 for a in articles if a["status"] == "PASS")
    failed = sum(1 for a in articles if a["status"] == "FAIL")
    timed_out = sum(1 for a in articles if a["status"] == "TIMEOUT")

    report = {
        "batch_id": f"regression_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "articles": articles,
        "aggregate": {
            "total_articles": len(articles),
            "passed": passed,
            "failed": failed,
            "timed_out": timed_out,
            "total_wall_time_s": sum(sum(a.get("timings_ms", {}).values()) for a in articles) / 1000,
            "batch_pass": failed == 0 and timed_out == 0,
        },
        "provider_usage": cascade.total_usage(),
    }

    Path(args.output).write_text(json.dumps(report, indent=2))
    exit(0 if report["aggregate"]["batch_pass"] else 1)

if __name__ == "__main__":
    main()
```

### Fixture Preparation Recipe

For each NEW fixture:
1. Identify source WeChat article URL matching profile
2. Run existing `ingest_wechat.py <url>` once manually to scrape HTML + download images
3. Copy output to `test/fixtures/{fixture_name}/`:
   - HTML → `article.html`
   - Markdown → `article.md`
   - Images → `images/`
4. Run a count script to populate `metadata.json` fields (`text_chars`, `total_images_raw`, etc.)
5. Manually run ingest ONE TIME against the fixture to capture `expected_chunks` + `expected_entities`
6. For `mixed_quality_article`: deliberately corrupt 2-3 images via `dd if=/dev/urandom of=images/img_003.jpg bs=1 count=100 seek=0 conv=notrunc` (overwrite first 100 bytes to break header)

### CI Integration Hook (not in scope, but documented for operator)

```yaml
# .github/workflows/regression.yml (post-v3.2 setup)
- name: Run regression fixtures
  run: |
    python scripts/validate_regression_batch.py \
      --fixtures test/fixtures/gpt55_article test/fixtures/sparse_image_article \
                  test/fixtures/dense_image_article test/fixtures/text_only_article \
                  test/fixtures/mixed_quality_article \
      --output batch_validation_report.json
- name: Upload report
  uses: actions/upload-artifact@v4
  with:
    name: regression-report
    path: batch_validation_report.json
```

</specifics>

<deferred>
## Deferred Ideas (out of scope)

- **Dynamic fixture generation** (synthesize articles from templates) — all 5 fixtures are manually curated for this phase
- **Fixture maintenance tooling** (auto-refresh fixture when source URL updates) — manual refresh only
- **Expanded fixture matrix** (non-Chinese articles, PDFs, other sources) — 5 fixtures is the design; Zhihu / RSS / PDF fixtures deferred to future phases
- **Trend analysis dashboard** (track fixture runs over time) — operator can diff `batch_validation_report.json` manually; no DB/dashboard in this phase
- **Fuzz testing** (generate random corrupt images) — `mixed_quality_article` provides deterministic coverage; fuzz deferred
- **Fixture checksum verification** (hash fixture files to detect drift) — not needed; git tracks fixtures

</deferred>

---

*Phase: 14-regression-fixtures*
*Context gathered: 2026-04-30 via PRD Express Path*

---

## Appendix: Phase 14 Partial Closure (2026-05-03)

Plans 14-01 (5-fixture creation) and 14-03 (E2E validation run) were deprecated 2026-05-03 and their STUB-PUNCH placeholders deleted. Rationale:

- v3.2 closed 2026-05-02 without these two plans executing.
- Wave 0 Close-Out (2026-05-02, Phase 5 Plan 05-00) performed a real multi-article batch that surfaced 2 bugs (async multi-image embedding blocking, Cognee module-level import blocking) that synthetic fixtures could not have caught. Real-batch validation empirically outperformed the 5-fixture approach on actual defect yield.
- 14-02 (validate_regression_batch.py skeleton) is retained — Milestone v3.3 Plan 18-04 reuses it as the backbone for a lighter, single-fixture + CI-hook regression harness.

See Milestone v3.3 Plan 18-04 for the replacement approach.
