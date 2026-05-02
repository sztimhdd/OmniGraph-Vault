---
phase: 14-regression-fixtures
plan: 01
status: stub-punch-to-hermes
stub_reason: "autonomous: false plan; requires WeChat scraping which is blocked locally by Cisco Umbrella TLS — must run on Hermes prod host"
punch_target: hermes
created: 2026-05-01
---

## What Claude did

**Nothing directly.** Plan 14-01 is marked `autonomous: false` in its frontmatter and requires operator-curated WeChat URLs + actual scraping against the WeChat CDN. Local dev machine is blocked by Cisco Umbrella proxy for `api.deepseek.com` / `api.siliconflow.cn` and WeChat QR login is operator-specific (see v3.2 prompt `R4` environment ceiling).

## What Hermes needs to do

### Scrape 4 WeChat articles against these profiles

From the session notes, Hermes already shortlisted titles for the 4 profiles. Confirm URLs for each, then scrape:

| Profile | Target | Article (from Hermes shortlist) |
|---|---|---|
| sparse_image_article | ~3 images, ~8000 chars, long-form analysis | DeepSeek-V4 深度解读 |
| dense_image_article | ~45 images, ~2000 chars, gallery-style with narrow banners | DeepSeek-V4 开源实测 |
| text_only_article | 0 images, ~3000 chars | QCon 复盘 |
| mixed_quality_article | ~15 images, ~5000 chars (will be corrupted post-scrape) | MiniCPM-o 4.5 |

### Execution on Hermes

```bash
cd ~/OmniGraph-Vault
git pull --ff-only
source venv/bin/activate

# For each of the 4 URLs:
python ingest_wechat.py "<wechat-url-for-profile>"

# Copy scraped artifacts to fixture dirs (replace ${ARTICLE_HASH} with the md5[:10])
ARTICLE_HASH=$(python -c "import hashlib; print(hashlib.md5('${URL}'.encode()).hexdigest()[:10])")
mkdir -p test/fixtures/${PROFILE}_article/images
cp ~/.hermes/omonigraph-vault/images/${ARTICLE_HASH}/final_content.md test/fixtures/${PROFILE}_article/article.md
cp ~/.hermes/omonigraph-vault/images/${ARTICLE_HASH}/*.{jpg,png} test/fixtures/${PROFILE}_article/images/ 2>/dev/null || true
```

### Special handling per profile

1. **text_only_article** — `rm -rf test/fixtures/text_only_article/images` after scrape (zero-image edge case)
2. **dense_image_article** — verify ≥5 images have `min(w,h) < 300` to exercise IMG-01 filter:
   ```bash
   python -c "
   from PIL import Image
   from pathlib import Path
   narrow = sum(1 for p in Path('test/fixtures/dense_image_article/images').iterdir()
                if p.is_file() and min(Image.open(p).size) < 300)
   print(f'narrow={narrow} — need >=5'); assert narrow >= 5"
   ```
3. **mixed_quality_article** — corrupt 2-3 images post-scrape:
   ```bash
   python -c "
   import random
   from pathlib import Path
   imgs = sorted(Path('test/fixtures/mixed_quality_article/images').iterdir())
   targets = imgs[:3] if len(imgs) < 10 else [imgs[2], imgs[5], imgs[8]]
   for t in targets:
       with open(t, 'r+b') as f:
           f.write(bytes(random.randint(0, 255) for _ in range(100)))
       print(f'corrupted {t.name}')
   "
   ```

### Generate metadata.json per fixture

Use the compute script pattern from 14-01-PLAN Task 4. Each `metadata.json` needs 8 fields:

```json
{
  "title": "...",
  "url": "...",
  "text_chars": 0,
  "total_images_raw": 0,
  "images_after_filter": 0,
  "expected_chunks": 0,
  "expected_entities": 0,
  "notes": "..."
}
```

Heuristics for `expected_*`:
- `expected_chunks = max(1, text_chars // 4800)`
- `expected_entities = max(5, text_chars // 400)`

### Acceptance validation

After all 4 fixtures are on disk, Hermes runs:

```bash
DEEPSEEK_API_KEY=... python scripts/validate_regression_batch.py \
  --fixtures test/fixtures/gpt55_article \
             test/fixtures/sparse_image_article \
             test/fixtures/dense_image_article \
             test/fixtures/text_only_article \
             test/fixtures/mixed_quality_article \
  --output batch_validation_report.json
```

Exit code 0 = all 5 fixtures pass (aggregate.batch_pass=true). This closes Gate 3 of Milestone v3.2.

### Commit suggestion

```
feat(14-01): scrape 4 regression fixtures (sparse/dense/text_only/mixed_quality)

- Scraped against Hermes production-stack CDP scraping path.
- text_only_article has 0 images; images/ dir removed.
- dense_image_article: N narrow-banner images for IMG-01 coverage.
- mixed_quality_article: 3 corrupted images for Phase 13 cascade error paths.
- All 4 metadata.json written with PRD §B3.2 schema.
```

## Why this cannot run locally

- Cisco Umbrella proxy blocks `api.deepseek.com` + `api.siliconflow.cn` TLS at the network layer
- WeChat QR login is operator-specific to Hermes's account (50-article throttle per session)
- `ingest_wechat.py` needs real CDP or Apify access to scrape production articles

Plan `14-01` is the ONE item in v3.2 that cannot be executed on the Claude dev machine.
