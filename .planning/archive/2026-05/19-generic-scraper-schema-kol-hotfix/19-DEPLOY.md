# Phase 19 Deploy Runbook — Hermes Operator Steps

**When to run:** After Phase 19 PR is merged to `main` and the commit is pushed. Before the next cron cycle executes `batch_ingest_from_spider.py`.

**Why this is needed:** SCH-02 migrates the article-hash function from MD5 first-10-hex to SHA-256 first-16-hex. Existing `checkpoints/<10-char-MD5>` directories on Hermes will be orphaned (`checkpoint_status.py` will still list them, but new ingest runs will not find them by the new hash). The safest cleanup is to wipe the entire checkpoints/ directory — WeChat re-scrape of articles is cheap, and the checkpoint cache is a performance optimization, not a data source.

## One-time post-deploy steps on Hermes

SSH target: see `~/.claude/projects/c--Users-huxxha-Desktop-OmniGraph-Vault/memory/hermes_ssh.md`

Run these commands in order on the Hermes box:

```bash
cd ~/OmniGraph-Vault
git pull --ff-only

# 1. Install the new trafilatura + lxml dependencies
source venv/bin/activate   # Linux-side — NOT venv/Scripts/
pip install -r requirements.txt

# 2. Verify installs
python -c "import trafilatura; print(trafilatura.__version__)"
# Expected: a 2.x version string
python -c "import lxml; print(lxml.__version__)"
# Expected: 5.x (pin <6)

# 3. Wipe legacy MD5-10 checkpoint dirs (SCH-02 migration)
python scripts/checkpoint_reset.py --all --confirm

# 4. Run the full test suite against the production venv
python -m pytest tests/ -q
# Expected: ≈ 464 passed / ≤ 13 pre-existing failed. All 8 Phase-19 tests must be GREEN:
#   tests/unit/test_scraper.py (5 pass), tests/unit/test_batch_ingest_hash.py (2 pass),
#   tests/unit/test_rss_schema_migration.py (1 pass)
# If ANY phase-19 test fails on Hermes, HALT and investigate before 06:00 ADT cron fire.

# 5. Smoke-test the KOL path: 1 article dry-run, --min-depth 2 to minimize work
python batch_ingest_from_spider.py --from-db --topic-filter Agent --min-depth 2 --max-articles 1 --dry-run
```

## Verifying the SCR-06 hotfix landed

When step 5 above runs a real (non-dry-run) ingest, the scrape log line MUST show one of:

- `method: apify` — primary path worked
- `method: cdp` — local CDP fallback worked
- `method: mcp` — remote MCP fallback worked
- `method: ua` — last-resort fallback worked

It MUST NOT be the case that the pipeline fails with a UA-only error and never tries apify / cdp / mcp. That was the Day-1 06:00 ADT regression the SCR-06 hotfix closes.

If the log shows `method: ua` for more than ~20% of articles in a normal batch, that means APIFY_TOKEN / CDP_URL are misconfigured (environment issue, not code issue). Check `~/.hermes/.env`.

## Checkpoint directory sanity check

After step 3 (checkpoint_reset), verify no legacy dirs remain:

```bash
ls ~/.hermes/omonigraph-vault/checkpoints/ 2>/dev/null | awk '{print length($0)}' | sort -u
```

Expected: either no output (directory empty or absent) or only `16`. If `10` appears in the output, re-run step 3.

## What to expect after pull (Rule 1 auto-fix callout)

Plan 19-02 landed a surgical fix in `ingest_wechat.py` to the `_pending_doc_ids` tracker — 4 call sites now use `ckpt_hash` (SHA-256[:16]) instead of `article_hash` (old MD5[:10]) to preserve STATE-02/03 rollback semantics across the `batch_ingest` ↔ `ingest_wechat` module boundary. The image directory namespace (`BASE_IMAGE_DIR/{article_hash}`) and the LightRAG doc_id namespace (`wechat_{article_hash}`) are UNCHANGED — only the in-memory tracker registry KEY was unified.

Rollback tests (`tests/unit/test_rollback_on_timeout.py` — 4 tests) all GREEN on the dev box. If these fail on Hermes, do NOT proceed to cron cutover — investigate first.

## Rollback

If Phase 19 must be reverted:

```bash
cd ~/OmniGraph-Vault
git revert <phase-19-merge-commit>
pip install -r requirements.txt   # reverts to pre-trafilatura deps
python scripts/checkpoint_reset.py --all --confirm   # wipe both old + new hash dirs
```

No data loss — checkpoints are a performance cache, not a source of truth.

**Previous good HEAD (pre-Phase-19 baseline):** `4965522` (commit right before Phase-19 first commit `784f740`).

## Phase 19 success criteria (operator checklist)

- [ ] `git pull` brought in Phase 19 commits
- [ ] `pip install -r requirements.txt` exits 0
- [ ] `python -c "import trafilatura"` exits 0 and prints 2.x version
- [ ] `python scripts/checkpoint_reset.py --all --confirm` exits 0
- [ ] `ls ~/.hermes/omonigraph-vault/checkpoints/` shows only 16-char names (or empty)
- [ ] `python -m pytest tests/ -q` completes (≤13 pre-existing failures; 0 Phase-19 test failures)
- [ ] Dry-run of 1 KOL article in step 5 parses without crash
- [ ] Next scheduled cron run's log shows `method: apify` / `cdp` / `mcp` (not pure `ua`) for at least the first 3 articles

---

*Written 2026-05-04 as part of Phase 19 plan 19-03.*
