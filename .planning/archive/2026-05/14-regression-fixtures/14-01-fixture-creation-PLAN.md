---
phase: 14-regression-fixtures
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - test/fixtures/sparse_image_article/metadata.json
  - test/fixtures/sparse_image_article/article.md
  - test/fixtures/sparse_image_article/article.html
  - test/fixtures/sparse_image_article/images/
  - test/fixtures/dense_image_article/metadata.json
  - test/fixtures/dense_image_article/article.md
  - test/fixtures/dense_image_article/article.html
  - test/fixtures/dense_image_article/images/
  - test/fixtures/text_only_article/metadata.json
  - test/fixtures/text_only_article/article.md
  - test/fixtures/text_only_article/article.html
  - test/fixtures/mixed_quality_article/metadata.json
  - test/fixtures/mixed_quality_article/article.md
  - test/fixtures/mixed_quality_article/article.html
  - test/fixtures/mixed_quality_article/images/
autonomous: false
requirements:
  - REGR-01
  - REGR-02

must_haves:
  truths:
    - "Four new fixture directories exist under test/fixtures/ (sparse/dense/text_only/mixed_quality)"
    - "Each fixture has metadata.json matching PRD §B3.2 schema exactly"
    - "dense_image_article has images with min(w,h) < 300 that exercise v3.1 Phase 8 IMG-01 filter"
    - "mixed_quality_article has 2-3 intentionally corrupted images that exercise Phase 13 cascade error paths"
    - "text_only_article has zero image files (edge case)"
  artifacts:
    - path: "test/fixtures/sparse_image_article/metadata.json"
      provides: "Fixture metadata (3 images, ~8000 chars)"
      contains: "\"total_images_raw\": 3"
    - path: "test/fixtures/dense_image_article/metadata.json"
      provides: "Fixture metadata (45 images, ~2000 chars)"
      contains: "\"total_images_raw\": 45"
    - path: "test/fixtures/text_only_article/metadata.json"
      provides: "Fixture metadata (0 images, ~3000 chars)"
      contains: "\"total_images_raw\": 0"
    - path: "test/fixtures/mixed_quality_article/metadata.json"
      provides: "Fixture metadata (15 images, ~5000 chars, 2-3 corrupted)"
      contains: "\"total_images_raw\": 15"
  key_links:
    - from: "test/fixtures/{fixture}/article.md"
      to: "test/fixtures/{fixture}/metadata.json:text_chars"
      via: "wc -m article.md matches metadata.text_chars exactly"
      pattern: "\"text_chars\":\\s*\\d+"
    - from: "test/fixtures/{fixture}/images/"
      to: "test/fixtures/{fixture}/metadata.json:total_images_raw"
      via: "ls images/ | wc -l equals metadata.total_images_raw"
      pattern: "\"total_images_raw\":\\s*\\d+"
---

<objective>
Create the 4 new regression fixture directories (sparse_image, dense_image, text_only, mixed_quality) with content + metadata.json matching PRD §B3.2 schema. These fixtures exercise distinct edge cases that the 56+ article batch will encounter. The 5th fixture (gpt55_article) already exists from Milestone A baseline.

Purpose: Supply deterministic offline test inputs for `validate_regression_batch.py` (Plan 14-02). Each fixture isolates a specific regression risk — sparse images (timeout @ LLM path), dense images (IMG-01 filter), text-only (Vision skip edge case), mixed quality (Vision cascade error handling).

Output: 4 populated directories under `test/fixtures/` + 4 metadata.json files.

**NOTE — this plan requires human intervention** for fixture acquisition (scraping real WeChat articles). This is marked `autonomous: false` and contains a checkpoint at the start to confirm source URLs.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/MILESTONE_v3.2_REQUIREMENTS.md
@.planning/phases/14-regression-fixtures/14-CONTEXT.md
@test/fixtures/gpt55_article/metadata.json
@test/fixtures/gpt55_article/article.md
@CLAUDE.md

<interfaces>
<!-- Baseline fixture schema (from existing test/fixtures/gpt55_article/metadata.json). -->
<!-- NOTE: baseline metadata is SLIMMER than Phase 14 PRD schema — Phase 14 fixtures ADD expected_chunks/expected_entities/notes. -->

Baseline metadata.json (gpt55_article, already on disk):
```json
{
  "title": "GPT-5.5来了！全榜第一碾压Opus 4.7，OpenAI今夜雪耻",
  "url": "http://mp.weixin.qq.com/s?__biz=...",
  "text_chars": 4574,
  "total_images_raw": 39,
  "images_after_filter": 28
}
```

Phase 14 LOCKED schema (PRD §B3.2) — superset used for NEW fixtures:
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

Baseline fixture file layout (from `ls test/fixtures/gpt55_article/`):
- article.md
- raw.html (baseline uses `raw.html` — new fixtures use `article.html` per PRD layout; both are acceptable; keep consistent per-fixture)
- images/img_000.jpg, img_001.png, ... (28 files kept after filter)
- metadata.json

v3.1 Phase 8 IMG-01 filter rule (for dense_image_article design):
- Images kept when `min(width, height) >= 300`
- A 100×800 narrow banner has `min(100, 800) = 100 < 300` → FILTERED OUT
</interfaces>

</context>

<tasks>

<task type="checkpoint:decision" gate="blocking">
  <name>Task 1: Confirm fixture source URLs</name>
  <decision>Which specific WeChat article URLs to scrape for each of the 4 new fixture profiles?</decision>
  <context>
  Fixtures must be real WeChat articles (per 14-CONTEXT.md §decisions — "Source real WeChat articles matching each profile"). Each fixture isolates one regression risk. Operator selects URLs that satisfy the profile constraints:

  1. **sparse_image_article** — article with ~3 images and ~8000 chars of text (long-form analysis piece; exercises timeout-at-LLM path)
  2. **dense_image_article** — article with ~45 images and ~2000 chars of text (gallery-style post with many 100×800 banners; exercises v3.1 Phase 8 IMG-01 `min(w,h)>=300` filter)
  3. **text_only_article** — article with 0 images and ~3000 chars (editorial / pure-text piece; exercises Vision-skip edge case)
  4. **mixed_quality_article** — article with ~15 images and ~5000 chars (any tech article; corruption will be applied artificially in Task 5)

  Character counts are targets — ±20% tolerance is acceptable; pick the closest real articles.
  </context>
  <options>
    <option id="option-a">
      <name>Operator provides 4 URLs upfront</name>
      <pros>Deterministic; planner can proceed without delay</pros>
      <cons>Requires operator time to curate URLs matching profiles</cons>
    </option>
    <option id="option-b">
      <name>Planner suggests URLs from recent KOL database</name>
      <pros>Leverages existing 302 classified articles (v3.1 Phase 10); may already have matching profiles</pros>
      <cons>Requires SQLite query; may not have text_only or dense_image candidates</cons>
    </option>
    <option id="option-c">
      <name>Synthesize text-only + mixed, scrape only sparse + dense</name>
      <pros>Reduces external dependency (WeChat throttle on 4 back-to-back scrapes)</pros>
      <cons>Violates 14-CONTEXT.md decision "Source real WeChat articles" — NOT RECOMMENDED</cons>
    </option>
  </options>
  <resume-signal>Provide 4 WeChat URLs labeled sparse/dense/text_only/mixed, OR select option-b and provide SQLite query results</resume-signal>
</task>

<task type="auto">
  <name>Task 2: Scrape 4 fixtures via existing ingest path</name>
  <read_first>
    - ingest_wechat.py (full file — main ingestion entry point)
    - config.py (BASE_IMAGE_DIR for scrape output location)
    - CLAUDE.md § Testing the CDP / MCP Scraping Path (CDP_URL modes)
    - test/fixtures/gpt55_article/ (reference layout to replicate)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Fixture Preparation Recipe
  </read_first>
  <files>
    - test/fixtures/sparse_image_article/article.md
    - test/fixtures/sparse_image_article/article.html
    - test/fixtures/sparse_image_article/images/
    - test/fixtures/dense_image_article/article.md
    - test/fixtures/dense_image_article/article.html
    - test/fixtures/dense_image_article/images/
    - test/fixtures/text_only_article/article.md
    - test/fixtures/text_only_article/article.html
    - test/fixtures/mixed_quality_article/article.md
    - test/fixtures/mixed_quality_article/article.html
    - test/fixtures/mixed_quality_article/images/
  </files>
  <action>
  For each of the 4 URLs confirmed in Task 1, perform offline fixture scrape:

  1. Ensure CDP is available: either `APIFY_TOKEN` is set OR Edge is running with `--remote-debugging-port=9223` (see CLAUDE.md § Testing the CDP / MCP Scraping Path).
  2. Create fixture directory: `mkdir -p test/fixtures/{fixture_name}/images`
  3. Run ingest in DRY-MODE to capture scraped output WITHOUT ingesting into LightRAG. Since `ingest_wechat.py` does not currently have a `--fixture-only` flag, use the following manual procedure:

     ```bash
     # Step A: Run normal ingest to BASE_IMAGE_DIR (this hits WeChat once via CDP/Apify)
     python ingest_wechat.py "<url-for-fixture>"

     # Step B: After ingest completes, locate the scraped artifacts:
     # - HTML: ~/.hermes/omonigraph-vault/images/{article_hash}/ (if retained) OR re-scrape via scrape-only helper
     # - Markdown: ingest_wechat.py writes final_content.md to the image dir — copy it
     # - Images: ~/.hermes/omonigraph-vault/images/{article_hash}/*.{jpg,png}

     # Step C: Copy to fixture:
     ARTICLE_HASH=$(python -c "import hashlib; print(hashlib.md5('<url>'.encode()).hexdigest()[:10])")
     cp ~/.hermes/omonigraph-vault/images/$ARTICLE_HASH/final_content.md test/fixtures/{fixture_name}/article.md
     cp ~/.hermes/omonigraph-vault/images/$ARTICLE_HASH/*.{jpg,png} test/fixtures/{fixture_name}/images/ 2>/dev/null || true
     # If raw HTML was preserved, copy it too; otherwise leave article.html absent (it is optional per PRD)
     ```

  4. For **text_only_article**: manually delete the `images/` directory contents after copy (it should be empty). Verify with `ls test/fixtures/text_only_article/images/ | wc -l` → `0`.
     - If the scraped article had images (e.g., tracking pixels), remove the images/ dir entirely so `total_images_raw` is truly 0.

  5. For **dense_image_article**: verify that at least 10+ images have `min(w,h) < 300` using:
     ```bash
     python -c "
     from PIL import Image
     from pathlib import Path
     narrow = [p for p in Path('test/fixtures/dense_image_article/images').iterdir() if p.is_file() and min(Image.open(p).size) < 300]
     print(f'Narrow images: {len(narrow)}/{len(list(Path(\"test/fixtures/dense_image_article/images\").iterdir()))}')
     "
     ```
     - If fewer than 10 narrow images, replace the URL (the article does not adequately exercise IMG-01). Return to Task 1.

  6. For **sparse_image_article**, **mixed_quality_article**: no special processing — just verify image counts match profile (±20%).

  **Do NOT run the full LightRAG ingest chain for these scrape-only extractions** — only the scrape + image download phases are needed. If this is operationally difficult (because `ingest_wechat.py` does not separate scrape from ingest cleanly), accept the full ingest but immediately run `python scripts/checkpoint_reset.py --hash $ARTICLE_HASH` (Phase 12 dependency) or `rm -rf ~/.hermes/omonigraph-vault/lightrag_storage/*` to discard graph state so the fixture is not contaminated (fixture is a FILE INPUT, not a graph state).

  Idempotency: if a fixture dir already has content, skip scrape for that URL (check `test -s test/fixtures/{fixture_name}/article.md`).
  </action>
  <verify>
    <automated>
test -s test/fixtures/sparse_image_article/article.md &&
test -s test/fixtures/dense_image_article/article.md &&
test -s test/fixtures/text_only_article/article.md &&
test -s test/fixtures/mixed_quality_article/article.md &&
test -d test/fixtures/sparse_image_article/images &&
test -d test/fixtures/dense_image_article/images &&
test -d test/fixtures/mixed_quality_article/images
    </automated>
  </verify>
  <done>All 4 fixture directories contain article.md (non-empty) and images/ directory (may be empty for text_only). Verified with `ls -la test/fixtures/{sparse,dense,text_only,mixed}_article/`.</done>
</task>

<task type="auto">
  <name>Task 3: Corrupt 2-3 images in mixed_quality_article</name>
  <read_first>
    - test/fixtures/mixed_quality_article/images/ (listing — need actual filenames after scrape)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Fixture Preparation Recipe (corruption recipe)
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B3.1 (mixed_quality_article profile)
  </read_first>
  <files>
    - test/fixtures/mixed_quality_article/images/
  </files>
  <action>
  Deliberately corrupt 2-3 images in `test/fixtures/mixed_quality_article/images/` to exercise Phase 13 Vision cascade error handling (per 14-CONTEXT.md decisions).

  Strategy — overwrite first 100 bytes of each target file with random data. This mangles the magic bytes + header so image decoders raise errors (triggers cascade fallback in Phase 13):

  ```bash
  # List images sorted; pick indices 2, 5, 8 (or first 3 if fewer than 10 exist)
  cd test/fixtures/mixed_quality_article/images
  FILES=($(ls | sort))
  COUNT=${#FILES[@]}
  if [ $COUNT -ge 10 ]; then
    TARGETS=(${FILES[2]} ${FILES[5]} ${FILES[8]})
  else
    # Take first 3 (or all if fewer than 3)
    TARGETS=(${FILES[@]:0:3})
  fi

  for F in "${TARGETS[@]}"; do
    echo "Corrupting: $F"
    # Overwrite first 100 bytes with random data (mangles magic bytes + header)
    dd if=/dev/urandom of="$F" bs=1 count=100 seek=0 conv=notrunc status=none
  done

  echo "Corrupted files:"
  for F in "${TARGETS[@]}"; do
    echo "  $F (size: $(stat -c%s $F 2>/dev/null || stat -f%z $F) bytes)"
  done
  ```

  If `/dev/urandom` is unavailable on Windows Git Bash, alternative:
  ```bash
  # Python one-liner fallback
  python -c "
  import os, random
  from pathlib import Path
  imgs = sorted(Path('test/fixtures/mixed_quality_article/images').iterdir())
  targets = [imgs[2], imgs[5], imgs[8]] if len(imgs) >= 10 else imgs[:3]
  for t in targets:
      with open(t, 'r+b') as f:
          f.write(bytes(random.randint(0, 255) for _ in range(100)))
      print(f'Corrupted: {t.name}')
  "
  ```

  Verify corruption: each target file must now fail PIL decode:
  ```bash
  python -c "
  from PIL import Image
  from pathlib import Path
  for p in sorted(Path('test/fixtures/mixed_quality_article/images').iterdir())[:10]:
      try:
          Image.open(p).verify()
          print(f'OK      {p.name}')
      except Exception as e:
          print(f'CORRUPT {p.name}: {type(e).__name__}')
  "
  ```

  Expected output: 2-3 `CORRUPT` lines, remaining `OK`. If zero corrupt lines appear, dd/write failed — re-run.
  </action>
  <verify>
    <automated>
python -c "
from PIL import Image, UnidentifiedImageError
from pathlib import Path
corrupt = 0
for p in sorted(Path('test/fixtures/mixed_quality_article/images').iterdir())[:20]:
    try:
        Image.open(p).verify()
    except Exception:
        corrupt += 1
assert 2 <= corrupt <= 4, f'Expected 2-3 corrupted images, got {corrupt}'
print(f'Corrupted count: {corrupt} (OK)')
"
    </automated>
  </verify>
  <done>mixed_quality_article/images/ contains 2-3 files that raise `UnidentifiedImageError` (or similar) when opened with PIL, while the rest decode successfully. Verified via Python count script.</done>
</task>

<task type="auto">
  <name>Task 4: Generate metadata.json for all 4 fixtures</name>
  <read_first>
    - test/fixtures/gpt55_article/metadata.json (baseline schema — note Phase 14 adds 3 new fields)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Fixture Layout (LOCKED schema)
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B3.2 (verbatim schema)
    - test/fixtures/sparse_image_article/article.md, dense_image_article/article.md, text_only_article/article.md, mixed_quality_article/article.md (from Task 2 output)
  </read_first>
  <files>
    - test/fixtures/sparse_image_article/metadata.json
    - test/fixtures/dense_image_article/metadata.json
    - test/fixtures/text_only_article/metadata.json
    - test/fixtures/mixed_quality_article/metadata.json
  </files>
  <action>
  For each fixture, populate `metadata.json` with the LOCKED PRD §B3.2 schema. Use the Python snippet below to compute derived fields automatically:

  ```python
  # scripts/compute_fixture_metadata.py  (one-off; can be inline)
  import json, sys
  from pathlib import Path
  from PIL import Image, UnidentifiedImageError

  def compute(fixture_dir, title, url, expected_chunks, expected_entities, notes):
      fixture = Path(fixture_dir)
      article = fixture / "article.md"
      images_dir = fixture / "images"

      text_chars = len(article.read_text(encoding="utf-8"))

      image_files = []
      if images_dir.exists():
          image_files = [p for p in sorted(images_dir.iterdir())
                         if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}]
      total_raw = len(image_files)

      kept = 0
      for p in image_files:
          try:
              with Image.open(p) as img:
                  w, h = img.size
              if min(w, h) >= 300:  # IMG-01 filter rule
                  kept += 1
          except (UnidentifiedImageError, OSError):
              # Corrupted images — they WILL reach Vision; count as kept for filter semantics
              # (filter happens BEFORE Vision, based on decodable dimensions; corrupt images
              # fail at filter-read → excluded from kept)
              pass

      meta = {
          "title": title,
          "url": url,
          "text_chars": text_chars,
          "total_images_raw": total_raw,
          "images_after_filter": kept,
          "expected_chunks": expected_chunks,
          "expected_entities": expected_entities,
          "notes": notes,
      }
      (fixture / "metadata.json").write_text(
          json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
      )
      print(f"{fixture_dir}: text_chars={text_chars} total_raw={total_raw} kept={kept}")
  ```

  Run compute() for each fixture with operator-supplied title/URL + planner-assigned expected counts:

  | Fixture | expected_chunks | expected_entities | notes |
  |---------|-----------------|-------------------|-------|
  | sparse_image_article | `max(1, text_chars // 4800)` | `max(5, text_chars // 400)` | "Few images, long text — exercises timeout-at-LLM path (Hermes original #5)" |
  | dense_image_article | `max(1, text_chars // 4800)` | `max(5, text_chars // 400)` | "Many narrow-banner images — exercises v3.1 Phase 8 IMG-01 min(w,h)>=300 filter (Hermes original #2, #6)" |
  | text_only_article | `max(1, text_chars // 4800)` | `max(5, text_chars // 400)` | "Zero images — exercises Vision-skip edge case (no Vision call at all)" |
  | mixed_quality_article | `max(1, text_chars // 4800)` | `max(5, text_chars // 400)` | "2-3 corrupted images — exercises Phase 13 Vision cascade error handling" |

  Heuristic rationale (Claude's Discretion per 14-CONTEXT.md):
  - `expected_chunks`: LightRAG default chunk size ~1200 tokens ≈ 4800 chars (matches `scripts/bench_ingest_fixture.py` heuristic at line 524)
  - `expected_entities`: ~1 entity per 400 chars (empirically ≈ 10-15 entities for a 5000-char article; conservative floor of 5)
  - Tolerance (±10%) is applied by the validation script, not baked into metadata

  After writing, validate each metadata.json:
  ```bash
  python -c "
  import json
  from pathlib import Path
  REQUIRED = {'title', 'url', 'text_chars', 'total_images_raw',
              'images_after_filter', 'expected_chunks', 'expected_entities', 'notes'}
  for f in ['sparse_image_article', 'dense_image_article', 'text_only_article', 'mixed_quality_article']:
      meta = json.loads(Path(f'test/fixtures/{f}/metadata.json').read_text(encoding='utf-8'))
      missing = REQUIRED - set(meta.keys())
      assert not missing, f'{f}: missing fields {missing}'
      print(f'{f}: OK ({len(meta)} fields)')
  "
  ```
  </action>
  <verify>
    <automated>
python -c "
import json
from pathlib import Path
REQUIRED = {'title', 'url', 'text_chars', 'total_images_raw',
            'images_after_filter', 'expected_chunks', 'expected_entities', 'notes'}
for f in ['sparse_image_article', 'dense_image_article', 'text_only_article', 'mixed_quality_article']:
    meta = json.loads(Path(f'test/fixtures/{f}/metadata.json').read_text(encoding='utf-8'))
    assert set(meta.keys()) >= REQUIRED, f'{f}: missing {REQUIRED - set(meta.keys())}'
    assert isinstance(meta['text_chars'], int) and meta['text_chars'] > 0, f'{f}: bad text_chars'
    assert isinstance(meta['total_images_raw'], int) and meta['total_images_raw'] >= 0, f'{f}: bad total_images_raw'
print('All 4 metadata.json files valid')
"
    </automated>
  </verify>
  <done>All 4 metadata.json files exist, contain the LOCKED 8-field PRD schema, text_chars matches article.md size, total_images_raw matches images/ directory count.</done>
</task>

<task type="auto">
  <name>Task 5: Cross-fixture profile validation</name>
  <read_first>
    - test/fixtures/{sparse,dense,text_only,mixed}_image_article/metadata.json (from Task 4)
    - .planning/phases/14-regression-fixtures/14-CONTEXT.md § Fixture Profiles table
    - .planning/MILESTONE_v3.2_REQUIREMENTS.md §B3.1 (Fixture Profiles table)
  </read_first>
  <files>
    - (no files modified — validation only)
  </files>
  <action>
  Verify that each fixture actually satisfies its intended profile constraints (from PRD §B3.1 + 14-CONTEXT.md table). Run the cross-validation script:

  ```bash
  python -c "
  import json
  from pathlib import Path

  PROFILES = {
      'sparse_image_article':  {'img_min': 1, 'img_max': 8,  'chars_min': 5000, 'chars_max': 12000},
      'dense_image_article':   {'img_min': 30, 'img_max': 60, 'chars_min': 500,  'chars_max': 4000},
      'text_only_article':     {'img_min': 0, 'img_max': 0,  'chars_min': 1500, 'chars_max': 5000},
      'mixed_quality_article': {'img_min': 10, 'img_max': 25, 'chars_min': 3000, 'chars_max': 8000},
  }

  failed = []
  for fixture, prof in PROFILES.items():
      meta = json.loads(Path(f'test/fixtures/{fixture}/metadata.json').read_text(encoding='utf-8'))
      imgs = meta['total_images_raw']
      chars = meta['text_chars']
      if not (prof['img_min'] <= imgs <= prof['img_max']):
          failed.append(f'{fixture}: total_images_raw={imgs} outside [{prof[\"img_min\"]}, {prof[\"img_max\"]}]')
      if not (prof['chars_min'] <= chars <= prof['chars_max']):
          failed.append(f'{fixture}: text_chars={chars} outside [{prof[\"chars_min\"]}, {prof[\"chars_max\"]}]')

  if failed:
      print('PROFILE VIOLATIONS:')
      for f in failed:
          print(f'  - {f}')
      raise SystemExit(1)
  print('All 4 fixtures satisfy their target profiles')
  "
  ```

  Tolerance is intentionally wide here (±50-100% of PRD nominal values) since operator picked real WeChat articles that are unlikely to match exact counts. Tighten if operator wishes.

  If any fixture fails profile validation:
  - For **text_only_article**: delete images/ subdirectory entirely, re-run Task 4 for that fixture only
  - For **dense_image_article**: if < 30 images, it's the wrong URL; return to Task 1 to pick a better candidate
  - For **sparse_image_article**: if > 8 images, delete excess images from images/ dir (keep the largest 3-5)
  - For **mixed_quality_article**: if < 10 images, no hard failure — note in metadata.notes

  Additionally verify dense_image_article narrow-banner coverage:
  ```bash
  python -c "
  from PIL import Image, UnidentifiedImageError
  from pathlib import Path
  imgs = list(Path('test/fixtures/dense_image_article/images').iterdir())
  narrow = 0
  for p in imgs:
      try:
          with Image.open(p) as img:
              if min(img.size) < 300:
                  narrow += 1
      except (UnidentifiedImageError, OSError):
          pass
  total = len([p for p in imgs if p.is_file()])
  print(f'dense_image_article: {narrow}/{total} images have min(w,h) < 300 (IMG-01 filter targets)')
  assert narrow >= 5, f'dense_image_article needs >=5 narrow images to exercise IMG-01; found {narrow}'
  "
  ```

  (Threshold of 5 is softer than the 10 mentioned in Task 2 — operator-provided article may have fewer narrow banners than ideal; 5 is the minimum meaningful coverage.)
  </action>
  <verify>
    <automated>
python -c "
import json
from pathlib import Path

PROFILES = {
    'sparse_image_article':  {'img_min': 1, 'img_max': 8,  'chars_min': 5000, 'chars_max': 12000},
    'dense_image_article':   {'img_min': 30, 'img_max': 60, 'chars_min': 500,  'chars_max': 4000},
    'text_only_article':     {'img_min': 0, 'img_max': 0,  'chars_min': 1500, 'chars_max': 5000},
    'mixed_quality_article': {'img_min': 10, 'img_max': 25, 'chars_min': 3000, 'chars_max': 8000},
}
for fixture, prof in PROFILES.items():
    meta = json.loads(Path(f'test/fixtures/{fixture}/metadata.json').read_text(encoding='utf-8'))
    assert prof['img_min'] <= meta['total_images_raw'] <= prof['img_max'], f'{fixture} image count off'
    assert prof['chars_min'] <= meta['text_chars'] <= prof['chars_max'], f'{fixture} char count off'
print('Profile validation PASS')
"
    </automated>
  </verify>
  <done>All 4 fixtures satisfy their profile constraints (image count + char count in range). dense_image_article has >=5 narrow-banner images that exercise v3.1 Phase 8 IMG-01 filter.</done>
</task>

</tasks>

<verification>
All-fixtures sanity check (runnable from repo root):

```bash
# Structural: 4 dirs exist with required files
for f in sparse_image_article dense_image_article text_only_article mixed_quality_article; do
  test -d test/fixtures/$f && test -f test/fixtures/$f/metadata.json && test -f test/fixtures/$f/article.md || { echo "FAIL: $f"; exit 1; }
done

# Schema: all metadata.json have required 8 fields
python -c "
import json
from pathlib import Path
REQ = {'title','url','text_chars','total_images_raw','images_after_filter','expected_chunks','expected_entities','notes'}
for f in ['sparse_image_article','dense_image_article','text_only_article','mixed_quality_article']:
    m = json.loads(Path(f'test/fixtures/{f}/metadata.json').read_text(encoding='utf-8'))
    assert set(m.keys()) >= REQ, f'{f}: missing {REQ - set(m.keys())}'
print('Schema OK')
"

# Semantic: text_only has 0 images, dense has >=30, sparse has <=8, mixed has 10-25
python -c "
import json
from pathlib import Path
counts = {f: json.loads(Path(f'test/fixtures/{f}/metadata.json').read_text(encoding='utf-8'))['total_images_raw']
          for f in ['sparse_image_article','dense_image_article','text_only_article','mixed_quality_article']}
assert counts['text_only_article'] == 0
assert counts['dense_image_article'] >= 30
assert counts['sparse_image_article'] <= 8
assert 10 <= counts['mixed_quality_article'] <= 25
print(f'Counts OK: {counts}')
"

# Corruption: mixed_quality has 2-3 corrupted images
python -c "
from PIL import Image
from pathlib import Path
c = 0
for p in Path('test/fixtures/mixed_quality_article/images').iterdir():
    try: Image.open(p).verify()
    except Exception: c += 1
assert 2 <= c <= 4, f'mixed_quality: {c} corrupted (expected 2-3)'
print(f'Corruption OK: {c} corrupted images')
"
```

All four assertions must pass for this plan to be complete.
</verification>

<success_criteria>
- [ ] 4 new fixture directories exist under `test/fixtures/` (sparse/dense/text_only/mixed)
- [ ] Each fixture has `article.md` with non-empty Markdown content
- [ ] Each fixture has `metadata.json` matching PRD §B3.2 8-field schema
- [ ] `text_only_article` has 0 image files (edge case for Vision skip)
- [ ] `dense_image_article` has ≥30 images, ≥5 with `min(w,h) < 300` (IMG-01 filter coverage)
- [ ] `mixed_quality_article` has 2-3 intentionally corrupted images that fail PIL decode
- [ ] `sparse_image_article` has ≤8 images and ≥5000 chars of text
- [ ] All 4 fixtures satisfy their target profile constraints (automated check)
</success_criteria>

<output>
After completion, create `.planning/phases/14-regression-fixtures/14-01-fixture-creation-SUMMARY.md` with:
- Summary of fixture creation (tasks completed)
- Specific URLs used for each fixture
- Final counts per fixture (text_chars, total_images_raw, images_after_filter)
- List of corrupted files in mixed_quality_article
- Any deviations from PRD profile constraints
- Files created / modified
</output>
