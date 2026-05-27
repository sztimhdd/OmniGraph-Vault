# Aliyun ECS deploy — operator runbook (post-fix 260514-d3p)

This runbook is for the human operator deploying the kb-2 fixes to Aliyun ECS at `http://101.133.154.49/kb/` after pulling commit `<260514-d3p hash>` from origin/main.

---

## 1. After `git pull` on Aliyun ECS

```bash
ssh root@101.133.154.49
cd /root/OmniGraph-Vault
git pull --ff-only
```

Verify the fix landed (HEAD should be the 260514-d3p commit):

```bash
git log --oneline -1
# expect: <hash> fix(kb-2): align SQL to prod schema + KB_BASE_PATH + index pages + reload-pattern
```

---

## 2. Re-export the SSG with subdirectory prefix

The Aliyun deploy serves under `/kb/` (Caddy reverse-proxy). Set `KB_BASE_PATH=/kb` at export time so all generated HTML uses `/kb/...` absolute paths:

```bash
cd /root/OmniGraph-Vault
KB_BASE_PATH=/kb \
KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db \
KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images \
python3 kb/export_knowledge_base.py
```

Expected output (last few lines):

```
[kb-2] qualifying entities (>= 5 articles): 91   # depends on data
[kb-2] topic pages rendered: 5
[kb-2] entity pages rendered: 91
[260514-d3p] Rendering topics + entities index pages...
Rendering sitemap.xml + robots.txt...
Done. Output: kb/output
```

If you see SQL `OperationalError`, the database schema does not match production. Check that `/root/OmniGraph-Vault/data/kol_scan.db` actually has the `entity_name` column, no `source` column on classifications, etc. (See Issue 2 below if classifications table is empty.)

---

## 3. Rsync to Caddy doc root

```bash
rsync -av --delete /root/OmniGraph-Vault/kb/output/ /var/www/kb/
```

---

## 4. Verify

```bash
# CSS must return text/css with HTTP 200
curl -I http://101.133.154.49/kb/static/style.css
# expect: HTTP/1.1 200 OK ; Content-Type: text/css

# Topics directory listing
curl -I http://101.133.154.49/kb/topics/
# expect: HTTP/1.1 200 OK ; Content-Type: text/html
# (no longer 404)

# Topics page
curl -I http://101.133.154.49/kb/topics/agent.html
# expect: HTTP/1.1 200 OK

# Entities directory listing
curl -I http://101.133.154.49/kb/entities/
# expect: HTTP/1.1 200 OK
```

Browser-side: load `http://101.133.154.49/kb/` and verify:

- Page is styled (CSS loaded, not raw HTML)
- Nav links go to `/kb/articles/` etc (not `/articles/`)
- Homepage "查看全部 →" links work without circling back
- Topic chip clicks navigate to `/kb/topics/agent.html` etc

---

## 5. Fix Issue 2 — populate `classifications` table on Aliyun

This is **operator-side**, not code. Pick ONE of the two options.

### Option A — `scp` Hermes `kol_scan.db` (FASTEST, includes all data)

Copies Hermes's entire pre-classified corpus (3945 classifications + 5285 extracted entities) onto Aliyun. Takes ~30s for ~50MB DB depending on bandwidth.

```bash
# From your dev box (which has SSH access to both Hermes and Aliyun):
ssh -p 49221 sztimhdd@ohca.ddns.net "cat ~/OmniGraph-Vault/data/kol_scan.db" \
  > /tmp/kol_scan.db.fresh
scp /tmp/kol_scan.db.fresh root@101.133.154.49:/root/OmniGraph-Vault/data/kol_scan.db.fresh

# Then on Aliyun:
ssh root@101.133.154.49
cd /root/OmniGraph-Vault
mv data/kol_scan.db data/kol_scan.db.bak
mv data/kol_scan.db.fresh data/kol_scan.db
# Re-run export per Step 2 above + rsync per Step 3.
```

### Option B — Run classify cron locally on Aliyun

Requires `DEEPSEEK_API_KEY` (or `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` configured) in `~/.hermes/.env` on Aliyun.

```bash
ssh root@101.133.154.49
cd /root/OmniGraph-Vault
python3 batch_classify_kol.py  # ~10 min for 789 articles
# Re-run export per Step 2 + rsync per Step 3.
```

**Recommendation:** Option A unless Aliyun should run an independent classify cron from Hermes. Hermes is the authoritative classify source; Aliyun should mirror.

---

## 6. Smoke test full UAT

```bash
# Default Latest section renders article cards
curl -sf http://101.133.154.49/kb/ | grep -c "article-card"
# expect: ≥ 1

# Topic pillar page has articles (only true after Step 5 fix)
curl -sf http://101.133.154.49/kb/topics/agent.html | grep -c "article-card"
# expect: ≥ 1 (after classifications populated)

# Entity page has articles
curl -sf http://101.133.154.49/kb/entities/openai.html | grep -c "article-card"
# expect: ≥ 1
```

---

## 7. Rollback (if needed)

If the new export produces broken pages:

```bash
ssh root@101.133.154.49
cd /var/www/kb
# Restore the pre-260514-d3p output (assuming you backed it up before Step 3)
# OR revert to the prior git tag and re-export
cd /root/OmniGraph-Vault
git log --oneline -10  # find the prior good commit
git checkout <prior-hash>
KB_BASE_PATH=/kb KB_DB_PATH=... python3 kb/export_knowledge_base.py
rsync -av --delete kb/output/ /var/www/kb/
```

---

## Open issues (operator-side, future work)

- **Aliyun classify cron schedule** — should Aliyun run its own daily classify cron (Option B), or always mirror from Hermes via scp (Option A)? Decision affects long-term ops cost and divergence risk.
- **DB schema migration on Aliyun** — verify `articles.lang` + `rss_articles.lang` columns exist on Aliyun's DB. The export driver pre-flight check `_ensure_lang_column` will fail loudly with the migration command if either is missing.
- **Caddy config for `/kb/` prefix** — verify Caddy strips `/kb/` correctly and serves static files; otherwise `KB_BASE_PATH=/kb` produces correct HTML but the URLs still 404.
