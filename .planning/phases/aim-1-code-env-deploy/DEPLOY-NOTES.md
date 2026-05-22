# aim-1 Deploy Notes

Phase: aim-1 (Code + env deploy)
Operator: agent (per `feedback_aim1_agent_is_operator.md` — agent IS operator, runs SSH directly via Bash)
Date: 2026-05-22

---

## DEPLOY-01 — Working tree reconcile

### Pre-reconcile state (Task 1 capture)

```
=== git remote -v ===
origin	https://github.com/sztimhdd/OmniGraph-Vault.git (fetch)
origin	https://github.com/sztimhdd/OmniGraph-Vault.git (push)

=== git log -1 --oneline ===
4eaef45 fix(timeout): refresh image_count_row from scraped.images (260516-htm)

=== git status ===
On branch main
Your branch is up to date with 'origin/main'.

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   .planning/CHANGELOG.md
	modified:   .planning/PROJECT-KB-v2.md
	modified:   .planning/REQUIREMENTS-KB-v2.md
	modified:   .planning/ROADMAP-KB-v2.md
	modified:   .planning/STATE-KB-v2.md
	modified:   .planning/phases/kb-3-data-and-search/kb-3-VERIFICATION.md
	modified:   CLAUDE.md
	modified:   batch_ingest_from_spider.py
	modified:   databricks-deploy/Makefile
	modified:   databricks-deploy/app.yaml
	modified:   databricks-deploy/databricks.yml
	modified:   databricks-deploy/requirements.txt
	modified:   ingest_wechat.py
	modified:   kb/api_routers/articles.py
	modified:   kb/api_routers/llm.py
	modified:   kb/api_routers/search.py
	modified:   kb/data/state_db.py
	modified:   kb/services/_lightrag_singleton.py
	modified:   kb/services/lightrag_query.py
	modified:   kb/static/article.css
	modified:   kb/static/article.js
	modified:   kb/static/qa.css
	modified:   kb/static/qa.js
	modified:   kb/static/site.css
	modified:   kb/static/site.js
	modified:   kb/templates/article.html
	modified:   kb/templates/index.html
	modified:   kb/templates/qa.html
	modified:   kg_synthesize.py
	modified:   lib/article_filter.py
	modified:   lib/lightrag_embedding.py
	modified:   lib/llm_complete.py
	modified:   lib/scraper.py
	modified:   requirements.txt
	modified:   scripts/reconcile_ingestions.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.planning/ARCHITECTURE-KB-v2.md
	.planning/ARCHITECTURE-Aliyun-Ingest-Migration-v1.md
	.planning/PROJECT-Aliyun-Ingest-Migration-v1.md
	.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md
	.planning/ROADMAP-Aliyun-Ingest-Migration-v1.md
	.planning/STATE-Aliyun-Ingest-Migration-v1.md
	.planning/debug/
	.planning/phases/aim-0-discover-classify/
	.planning/phases/aim-1-code-env-deploy/
	.planning/phases/kb-4-ubuntu-deploy-cron-smoke/
	.planning/phases/kb-v2.2-1-vault-clone/
	.planning/phases/kb-v2.2-2-bilingual-ssg/
	.planning/phases/kb-v2.2-3-language-detect/
	.planning/quick/260510-h09b/
	.planning/quick/260510-h09c/
	.planning/quick/260511-lmc/
	.planning/quick/260511-lmx/
	.planning/quick/260512-lf17/
	.planning/quick/260512-lf18/
	.planning/quick/260513-lyt/
	.planning/quick/260513-imc/
	.planning/quick/260514-h09r/
	.planning/quick/260515-cvh/
	.planning/quick/260516-htm/
	.planning/quick/260517-rgd/
	.planning/quick/260517-rgd-2/
	.planning/quick/260517-rgd-3/
	.planning/quick/260518-v22-1/
	.planning/quick/260519-aliyun-prep/
	databricks-deploy/_hermes_pull/
	databricks-deploy/_volume_staging/
	kb/wiki/
	scripts/cleanup_stuck_docs.py
	tests/

no changes added to commit (use "git add" and -u to track files)

=== git diff --stat ===
35 files changed, 2059 insertions(+), 830 deletions(-)

=== git diff --stat --cached ===
(empty — no staged changes)
```

### Reconcile decision (Task 2)

**Method:** stash (with `-u` to include untracked)

**Rationale:**

Briefing framed dirty state as "kb-api 之前 SCP 遗留", but Task 1 probe revealed the scope is far broader: 35 modified files spanning .planning/ (cross-milestone planning artifacts), CLAUDE.md, ingest core (`batch_ingest_from_spider.py`, `ingest_wechat.py`, `kg_synthesize.py`), kb/ subsystem (api routers, services, templates, static), `databricks-deploy/`, libs (`lib/article_filter.py`, `lib/lightrag_embedding.py`, `lib/llm_complete.py`, `lib/scraper.py`, `scripts/reconcile_ingestions.py`), plus dozens of untracked planning directories from quicks `260510-*` through `260519-*` and the new aim-* / kb-v2.2-* / kb-4-* phase folders.

These changes likely represent (a) drift introduced by manual SCPs from the dev box during kb-2/kb-3/kb-4 incident response, plus (b) genuine local edits by another concurrent operator path. Discarding (`git checkout -- .` + `git clean -fd`) would be irreversible and risk losing valid work; explicit committing 35+ files would require enumerating each one (red-line forbids `git add -A` / `git add .`) and would push unverified content to GitHub origin under the agent's authorship.

`git stash push -u` is the right tool for this scope:
- Fully reversible — operator can `git stash pop stash@{0}` later to recover the work
- Preserves both modified and untracked content in a single stash entry
- Returns disk to known stable baseline (HEAD=4eaef45, the v1.0.x final commit kb-api + Hermes cron were originally deployed against), maximizing runtime parity with the as-deployed state
- No new commit polluting public history; no irreversible loss
- Single-command op, no risk of accidentally staging .env / SA JSON / other sensitive files (red-line: no literal secrets in artifacts)

Stash ref `stash@{0}: aim-1 pre-deploy stash 20260522-1110` is named with phase + timestamp so future operators can identify it without reading the git log.

### Reconcile execution (Task 3a)

Commands run on Aliyun (agent via Bash SSH `ssh aliyun-vitaclaw`):

```bash
cd /root/OmniGraph-Vault
git stash push -u -m "aim-1 pre-deploy stash 20260522-1110"
```

### Post-reconcile state (Task 3b)

```
=== post-stash git status ===
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

=== post-stash git log -1 ===
4eaef45 fix(timeout): refresh image_count_row from scraped.images (260516-htm)

=== git remote -v ===
origin	https://github.com/sztimhdd/OmniGraph-Vault.git (fetch)
origin	https://github.com/sztimhdd/OmniGraph-Vault.git (push)

=== stash list (top 3) ===
stash@{0}: On main: aim-1 pre-deploy stash 20260522-1110
stash@{1}: On main: aliyun-prep-20260520-210305
stash@{2}: WIP on main: f1a6f70 docs(v3.5-state): sync hermes operational state post-deploy 260507-lai
```

**HEAD commit hash (post-reconcile):** `4eaef45`
**Working tree clean:** YES
**Stash preserved:** `stash@{0}: aim-1 pre-deploy stash 20260522-1110` — recoverable via `git stash pop` or `git stash apply stash@{0}`

### No-secrets / no-connection-details checks

- DEPLOY-NOTES.md contains: paths, commit hashes, file names from `git status`, stash refs, GitHub origin URL (public). NO API keys, tokens, passwords, SA JSON content, SSH host/port/user/IP, or `.env` content.
- Operator channel: agent SSHes via local alias `ssh aliyun-vitaclaw` (alias resolution + key auth in `~/.ssh/config` + memory `aliyun_vitaclaw_ssh.md`). Connection details NOT recorded in this artifact.

---

## DEPLOY-02 — Venv setup (sibling ingest-only venv)

### Decision: Option C — sibling `venv-aim1/` for ingest

User-directed (2026-05-22) after agent surfaced the python-version blocker:

- Existing `/root/OmniGraph-Vault/venv/` = **Python 3.10.12** (kb-api prod runtime, 160 packages, hardcoded in `kb-api.service` ExecStart). LightRAG ≥3.11 requirement makes this venv unusable for ingest.
- System python inventory: `/usr/bin/python3.10` (3.10.12), `/usr/bin/python3.11` (**3.11.0rc1**), no 3.12/3.13 available.
- Three options surfaced: (A) rebuild kb-api venv on 3.11 — high blast radius, kb-api 807-package surface validated only on 3.10; (B) stay on 3.10, fork ingest deps — defers LightRAG forever; (C) sibling `venv-aim1/` on 3.11.0rc1 alongside untouched `venv/`.
- **User chose C** with rationale: kb-api 3.10 surface is verified prod combo (don't disturb running service with MemoryMax=8G OOM risk on restart), 3.11.0rc1 ABI is stable (RC published days before 3.11.0 final), all ingest-side packages have cp311 wheels, aim-3 systemd timer ExecStart simply points at `venv-aim1/bin/python` — double-venv long-term maintenance cost is one path string.

### Two deviations recorded

**Deviation 1 — Python 3.11.0rc1 (release candidate, not formal stable):**
- Selected because Aliyun Ubuntu has no 3.11 final / 3.12 / 3.13 in `/usr/bin/`.
- Risk assessment: 3.11.0rc1 is the release candidate published shortly before 3.11.0 final (2022-10); the ABI froze at RC1 and ingest-side packages (lightrag-hku, google-genai, openai, lancedb, kuzu, pymupdf, etc.) all have cp311 wheels that resolve cleanly. Smoke (25/25 imports) confirms ABI compat.
- Mitigation if instability surfaces in DEPLOY-04 smoke or later: rebuild `venv-aim1` on a properly built python3.11 final (apt or compile from source). Keeping kb-api 3.10 means rebuild is contained.

**Deviation 2 — Dual-venv architecture:**
- `venv/`     → kb-api (uvicorn), Python 3.10.12, 160 packages, PID 3512216 unchanged through aim-1-2.
- `venv-aim1/` → ingest (DEPLOY-04 smoke target, aim-3 systemd timer ExecStart target), Python 3.11.0rc1, 153 packages.
- `aim-1-3` (env extension) and `aim-1-4` (e2e smoke) command templates use `venv-aim1/bin/python` and `venv-aim1/bin/pip` exclusively. `kb-api.service.d/override.conf` is NOT touched.
- aim-3 systemd timer (future phase) ExecStart will be `/root/OmniGraph-Vault/venv-aim1/bin/python <ingest-script>`.

### Build execution

Commands run on Aliyun (agent via Bash SSH `ssh aliyun-vitaclaw`):

```bash
cd /root/OmniGraph-Vault
python3.11 -m venv venv-aim1
venv-aim1/bin/python -m pip install --upgrade pip setuptools wheel
venv-aim1/bin/pip install -r requirements.txt   # full requirements.txt — no subset, per user mandate
```

- pip install ran in background under `nohup ... & disown` with PID=3670346, stdout+stderr → `/tmp/aim1-pip-install.log`, polled by `until grep -q "^EXITCODE="` until completion.
- Final marker: `EXITCODE=0`. All 27 top-level requirements + ~120 transitive deps installed.
- Wheels built locally for `langdetect` and `sgmllib3k` (no prebuilt wheels), all others resolved from PyPI cp311 wheels.

### Post-build evidence

```
=== venv-aim1 python ===
Python 3.11.0rc1
sys.version_info(major=3, minor=11, micro=0, releaselevel='candidate', serial=1)
executable: /root/OmniGraph-Vault/venv-aim1/bin/python

=== venv-aim1 package count ===
153 packages (pip list --format=freeze | wc -l)

=== Key package versions (from pip list) ===
aiolimiter==1.2.1
apify-client==3.0.0
beautifulsoup4==4.14.3
feedparser==6.0.12
google-genai==1.75.0
graphifyy==0.5.3            # PyPI dist name; import name is `graphify` (one y) — see Smoke note below
instructor==1.15.1
kuzu==0.11.3
lancedb==0.30.2
langdetect==1.0.9
lightrag-hku==1.4.16
litellm==1.82.6
lxml==5.4.0
numpy==2.4.6
openai==2.38.0
playwright==1.60.0
PyMuPDF==1.27.2.3
tenacity==9.1.4
trafilatura==2.0.0

=== kb-api venv (untouched control) ===
venv/bin/python -V          → Python 3.10.12
pip list count              → 160 packages (matches pre-aim-1 baseline)
kb-api process              → PID 3512216 still running `venv/bin/python -m uvicorn kb.api:app --host 127.0.0.1 --port 8766`
```

### Import smoke (25/25 PASS)

`venv-aim1/bin/python` imported all 25 ingest-critical modules cleanly:

```
OK (25/25): lightrag, google.genai, openai, apify_client, playwright, lancedb,
            kuzu, pymupdf, trafilatura, feedparser, litellm, instructor,
            graphify, langdetect, aiolimiter, tenacity, pytest, numpy,
            requests, PIL, bs4, html2text, dotenv, nest_asyncio, lxml
FAIL (0)
EXIT=0
```

**Smoke note — graphifyy import-name divergence:** PyPI distribution `graphifyy==0.5.3` (two `y`) installs into site-packages under top-level module `graphify` (one `y`). Confirmed via `graphifyy-0.5.3.dist-info/top_level.txt` which lists `graphify` (plus benchmark/eval/test fixture dirs). Production code that uses this lib must `import graphify`, not `import graphifyy`. First smoke iteration imported `graphifyy` and FAILED with `ModuleNotFoundError`; corrected to `graphify` and 25/25 PASS.

### Discipline checks

- ✅ **No-secrets:** This section contains only python versions, package names + versions, file paths, process PIDs, log file paths. No API keys / tokens / SA JSON / `.env` content / connection details.
- ✅ **No-connection-details:** No SSH host / port / user / IP / private key. Agent uses local SSH alias `aliyun-vitaclaw`.
- ✅ **Operator-channel:** Agent IS operator per `feedback_aim1_agent_is_operator.md`. All venv build + pip install + smoke ops ran via direct Bash SSH, no user round-trips.
- ✅ **Red lines honored:** No `git add -A` / `git add .` (venv-aim1/ is untracked on Aliyun and will NOT be committed — venv contents are reproducible from `requirements.txt`), no `--amend`, no `--force`, no `--hard`, no `systemctl` ops, no `kb-api.service.d/override.conf` touched, no kb-api restart triggered, no kb-api venv (`venv/`) packages added/removed/upgraded.
- ✅ **Forward-only edit:** This §DEPLOY-02 section is a net-new append to DEPLOY-NOTES.md. §DEPLOY-01 from aim-1-1 is unchanged.
- ✅ **kb-api preservation:** PID 3512216 still serving on `127.0.0.1:8766` throughout aim-1-2; `venv/` Python version (3.10.12) and package count (160) unchanged from pre-aim-1 baseline.

### Bridge to aim-1-3

`venv-aim1` is operational with all 27 top-level deps + transitive resolved. aim-1-3 (DEPLOY-03 env extension) and aim-1-4 (DEPLOY-04 e2e smoke) command templates use `venv-aim1/bin/python` exclusively. `/root/.hermes/.env` is **not** touched in aim-1-2 — env extension is aim-1-3 scope. aim-1-3 will append 6 ingest provider keys (DEEPSEEK / SILICONFLOW / VERTEX SA path / GEMINI / APIFY × 2) preserving existing kb-api keys + file mode/ownership.

---

## DEPLOY-03 — Env extension (`/root/.hermes/.env` ingest keys)

### Pre-extension audit (Task 1 capture)

Pre-state of `/root/.hermes/.env`:

```
mode/owner:  -rw------- 1 root root 2276 May 22 20:?? .env
line count:  49

6 ingest-key presence (count of lines starting with KEY=):
  DEEPSEEK_API_KEY              count=1   (already present, sourced from earlier deploy)
  SILICONFLOW_API_KEY           count=1   (already present)
  GEMINI_API_KEY                count=1   (already present)
  APIFY_TOKEN                   count=1   (already present)
  GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json   (semantic equivalent of OMNIGRAPH_VERTEX_SA_JSON_PATH)
  OMNIGRAPH_VERTEX_SA_JSON_PATH count=0   (ABSENT — needs append)
  APIFY_TOKEN_BACKUP            count=0   (ABSENT — needs append, source: Hermes ~/.hermes/.env)

kb-api keys spot-check (must remain unchanged):
  WEIXIN_TOKEN, GATEWAY_ALLOW_ALL_USERS, HERMES_CRON_TIMEOUT,
  TELEGRAM_BOT_TOKEN, BRAVE_API_KEY                             all count=1
```

### Decision: scope = 2-key minimal append (Option A)

User-directed (2026-05-22) after agent surfaced 4-of-6 keys already present:

- **Append-only-the-absent (A) chosen** over (B) full 6-key normalization, because the 4 pre-existing keys are byte-identical to what aim-1-3 would write, making rewriting them pure churn and creating diff noise that hides the actual 2-line change.
- Backup file `/root/.hermes/.env.bak-aim1-20260522-233253` (2276 bytes, mode 600 root:root) preserved in-place for rollback. Rolls back the +2 lines via `cp /root/.hermes/.env.bak-aim1-20260522-233253 /root/.hermes/.env`.

### Two value-derivation decisions

**Decision 1 — `OMNIGRAPH_VERTEX_SA_JSON_PATH` value:**

- Existing line `GOOGLE_APPLICATION_CREDENTIALS=/root/.hermes/gcp-paid-sa.json` already references the SA JSON file (mode 600 root:root, 2400 bytes). `OMNIGRAPH_VERTEX_SA_JSON_PATH` is the OmniGraph-namespaced reference to the same SA JSON.
- Agent SSH'd Aliyun to read the path value via `grep "^GOOGLE_APPLICATION_CREDENTIALS=" /root/.hermes/.env | cut -d= -f2-`. The path string (not the SA JSON contents) was used as `OMNIGRAPH_VERTEX_SA_JSON_PATH=<path>`. SA JSON file bytes never read or transmitted.
- Rationale: semantic equivalence — both env vars point at the same file, so reusing the existing path eliminates "where does this SA come from" ambiguity for future operators.

**Decision 2 — `APIFY_TOKEN_BACKUP` source channel (Hermes → Aliyun SSH-pipe):**

- Source: Hermes `~/.hermes/.env`, where `APIFY_TOKEN_BACKUP` was deployed 2026-05-08 as part of the dual-token rotation (quick `260508-ev2`, see `feedback_no_literal_secrets_in_prompts.md`). Hermes is the canonical source-of-truth for ingest secrets since aim-1 is migrating ingest from Hermes → Aliyun.
- Channel: SSH-pipe pattern with value transiting the local SSH client process pipe between two `ssh` invocations:
  ```
  ssh hermes 'grep "^APIFY_TOKEN_BACKUP=" ~/.hermes/.env' | ssh aliyun-vitaclaw 'cat >> /root/.hermes/.env'
  ```
  The value flows directly from Hermes to Aliyun through the local pipe; the receiving `cat >> file` produces empty stdout, so the literal token never appears in agent stdout / context / artifacts. Honors both the agent-IS-operator mandate (`feedback_aim1_agent_is_operator.md`) AND the no-literal-secrets-in-context constraint (`feedback_no_literal_secrets_in_prompts.md`).
- Pipe exit code 0; verified via post-extension audit (key shape match, length 47 bytes incl. trailing newline / 46 bytes content).

### Execution sequence (agent via Bash SSH, no user round-trips)

```bash
# Step 1: Aliyun-side backup + read SA path + append OMNIGRAPH_VERTEX_SA_JSON_PATH
ssh aliyun-vitaclaw '
  set -e
  TS=$(date +%Y%m%d-%H%M%S)
  cp -p /root/.hermes/.env /root/.hermes/.env.bak-aim1-$TS
  SA_PATH=$(grep "^GOOGLE_APPLICATION_CREDENTIALS=" /root/.hermes/.env | head -1 | cut -d= -f2-)
  [ -f "$SA_PATH" ] || exit 1
  echo "OMNIGRAPH_VERTEX_SA_JSON_PATH=$SA_PATH" >> /root/.hermes/.env
'

# Step 2: Hermes -> Aliyun SSH-pipe for APIFY_TOKEN_BACKUP (value never enters agent stdout)
ssh hermes 'grep "^APIFY_TOKEN_BACKUP=" ~/.hermes/.env' \
  | ssh aliyun-vitaclaw 'cat >> /root/.hermes/.env'

# Step 3: Aliyun-side post-extension masked audit
ssh aliyun-vitaclaw '
  ls -la /root/.hermes/.env
  wc -l /root/.hermes/.env
  for K in DEEPSEEK_API_KEY SILICONFLOW_API_KEY OMNIGRAPH_VERTEX_SA_JSON_PATH \
           GEMINI_API_KEY APIFY_TOKEN APIFY_TOKEN_BACKUP; do
    echo "$K count=$(grep -c "^$K=" /root/.hermes/.env)"
  done
'
```

### Post-extension audit (Aliyun-side, masked)

```
mode/owner:  -rw------- 1 root root 2403 May 22 23:43 .env
line count:  51 (was 49, +2 net)

6 ingest-key presence (post-extension):
  DEEPSEEK_API_KEY              count=1   (unchanged)
  SILICONFLOW_API_KEY           count=1   (unchanged)
  OMNIGRAPH_VERTEX_SA_JSON_PATH count=1   (NEW, value = /root/.hermes/gcp-paid-sa.json,
                                            file exists=True, mode 600 root:root, 2400 bytes)
  GEMINI_API_KEY                count=1   (unchanged)
  APIFY_TOKEN                   count=1   (unchanged)
  APIFY_TOKEN_BACKUP            count=1   (NEW, val_len=47 bytes incl. \n,
                                            prefix=apify_ap — Apify token shape)

kb-api keys spot-check (post-extension, unchanged):
  WEIXIN_TOKEN                  count=1   (PRESENT, len=58)
  GATEWAY_ALLOW_ALL_USERS       count=1
  HERMES_CRON_TIMEOUT           count=1
  TELEGRAM_BOT_TOKEN            count=1
  BRAVE_API_KEY                 count=1

backup file:  /root/.hermes/.env.bak-aim1-20260522-233253
              -rw------- 1 root root 2276 (pre-extension snapshot, mode 600 root:root)
```

### venv-aim1 env-presence smoke (masked, no values)

`venv-aim1/bin/python` was invoked under `set -a; . /root/.hermes/.env; set +a` and asked to read each ingest key from `os.environ`. Output (masked — only key NAME + length category + 8-char prefix or path-shape):

```
=== venv-aim1 env presence smoke ===
DEEPSEEK_API_KEY:               len=35  prefix=sk-06d83        (DeepSeek shape ✓)
SILICONFLOW_API_KEY:            len=51  prefix=sk-yhhvd        (SiliconFlow shape ✓)
OMNIGRAPH_VERTEX_SA_JSON_PATH:  path-shape (file_exists=True)  (SA JSON resolves ✓)
GEMINI_API_KEY:                 len=39  prefix=AIzaSyDt        (Google AIza... shape ✓)
APIFY_TOKEN:                    len=46  prefix=apify_ap        (Apify shape ✓)
APIFY_TOKEN_BACKUP:             len=46  prefix=apify_ap        (Apify shape ✓)

=== kb-api keys still loadable from same .env ===
WEIXIN_TOKEN:             PRESENT (len=58)
GATEWAY_ALLOW_ALL_USERS:  PRESENT (len=4)
HERMES_CRON_TIMEOUT:      PRESENT (len=5)
```

All 6 ingest keys readable by ingest python; all kb-api spot-check keys still readable from the same `.env` after extension. No literal values emitted.

### Discipline checks

- ✅ **No-secrets:** This section contains only key NAMES, length-bytes, 8-char prefixes (token shape sanity), and file paths. No full token values, no SA JSON contents. Backup filename includes timestamp only.
- ✅ **No-connection-details:** No SSH host / port / user / IP / private key. Agent uses local SSH aliases `aliyun-vitaclaw` and `hermes`.
- ✅ **Operator-channel:** Agent IS operator per `feedback_aim1_agent_is_operator.md`. All env-extension ops (backup + path read + 2-line append + masked audit + smoke) ran via direct Bash SSH. APIFY_TOKEN_BACKUP value transited Hermes → Aliyun via local SSH-pipe; agent stdout / artifacts contain no literal tokens. Zero user round-trips after the 3-decision message.
- ✅ **Red lines honored:** No `git add -A` / `git add .`, no `--amend`, no `--force`, no `--hard`, no `systemctl` ops, no `kb-api.service.d/override.conf` touched, no kb-api restart triggered, no kb-api venv (`venv/`) touched. `/root/.hermes/.env` mode 600 root:root preserved (verified pre + post). 4 pre-existing kb-api keys + 4 pre-existing ingest keys byte-identical (count=1 each, no rewrite).
- ✅ **Forward-only edit:** This §DEPLOY-03 is a net-new append to DEPLOY-NOTES.md. §DEPLOY-01 (aim-1-1) and §DEPLOY-02 (aim-1-2) unchanged.
- ✅ **kb-api preservation:** PID 3512216 still serving uvicorn on `127.0.0.1:8766` throughout aim-1-3; `venv/` and `kb-api.service.d/override.conf` untouched.
- ✅ **Backup recoverable:** `/root/.hermes/.env.bak-aim1-20260522-233253` (2276 bytes, mode 600 root:root) preserves pre-extension state. Rollback: `cp -p /root/.hermes/.env.bak-aim1-20260522-233253 /root/.hermes/.env`.

### Bridge to aim-1-4

`/root/.hermes/.env` now exposes all 6 ingest provider keys to `venv-aim1/bin/python`. aim-1-4 (DEPLOY-04 e2e smoke) can run the full ingest path against scratch storage with `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke`, exercising DeepSeek (Layer 2 + LightRAG entity extraction), SiliconFlow (vision primary), Vertex AI Gemini (Layer 1 + embedding fallback), Gemini API (vision last-resort), Apify (scrape primary + backup token rotation). kb-api on `:8766` remains untouched — smoke is a parallel-tenant test, not a kb-api co-tenant test.

---
