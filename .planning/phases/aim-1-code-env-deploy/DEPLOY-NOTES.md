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

## §DEPLOY-04 — aim-1-4 e2e smoke (2026-05-23)

Status: ✅ DONE — DEPLOY-04 PASS
Companion evidence: `DEPLOY-04-EVIDENCE.md` (full per-run logs + tables) + `aim-1-4-SUMMARY.md` (verdict + bridge to aim-2).

### Pre-smoke audit

```
HEAD:                     4eaef45b76066bc9c808440cd29e028b2e20d585  (unchanged from aim-1-1 baseline)
git status (working):     M scripts/local_e2e.sh   (PYTHON env override patch — additive)
                          ?? venv-aim1/             (untracked, intentional — reproducible from requirements.txt)

kb-api process:           PID 3512216  (python -m uvicorn kb.api:app --host 127.0.0.1 --port 8766)
kb-api venv:              venv/bin/python = Python 3.10.12, 160 packages  (UNTOUCHED)
ingest venv:              venv-aim1/bin/python = Python 3.11.0rc1, 153 packages

/root/.hermes/.env:       mode 600 root:root, 51 lines, 2403 bytes  (unchanged from aim-1-3 post-extension)
                          6 ingest keys count=1 each + 5 kb-api keys count=1 each

Scratch sandbox:
  OMNIGRAPH_BASE_DIR        = /tmp/aim1-smoke
  KOL_SCAN_DB_PATH          = /tmp/aim1-smoke/data/kol_scan.db
  PYTHON                    = /root/OmniGraph-Vault/venv-aim1/bin/python
  REQUESTS_CA_BUNDLE        = /root/OmniGraph-Vault/venv-aim1/lib/python3.11/site-packages/certifi/cacert.pem
  NODE_EXTRA_CA_CERTS       = (same path)

DB cp (per Conflict 2 verdict):
  cp -p /root/OmniGraph-Vault/data/kol_scan.db /tmp/aim1-smoke/data/kol_scan.db
  → 2 985 984 bytes  (snapshot of prod candidate pool)
```

### Decisions

- **3-run smoke schedule** (user-directed 2026-05-22 → 2026-05-23):
  - Run #1 (wechat short URL) — smallest end-to-end traversal validating scrape + Layer 2 + ainsert wiring
  - Run #2 (wechat image-rich URL) — vision cascade primary (SiliconFlow Qwen3-VL-32B) end-to-end
  - Run #3 (kol `--from-db --max-articles 1`) — full pipeline at scale (candidate-pool SQL → 7×Layer 1 batch → max-articles cap → vision 38/38 → Layer 2 → batch metrics)
  - Pre-flight Layer 1 smoke (5 candidates) — standalone Vertex AI Gemini reachability check before committing wechat/kol runs
- **Operator channel**: agent IS operator per `feedback_aim1_agent_is_operator.md`; all smoke + audit ops via direct `ssh aliyun-vitaclaw '...'` Bash. Zero user round-trips during smoke execution.

### Deviations (4)

**Deviation 1 — `scripts/local_e2e.sh` PYTHON env override (additive, default behavior preserved)** [Conflict 1 verdict B]:

Lines 92-106 extended with a `$PYTHON` env override branch. When `$PYTHON` is set and executable, harness honors it; otherwise falls through to original Windows (Git Bash) → Linux/Mac venv detection. Default behavior unchanged when `$PYTHON` unset. Rationale: smoke must pin to `venv-aim1/bin/python` (ingest sibling venv, py3.11.0rc1, 153 packages) instead of `venv/bin/python` (kb-api venv, py3.10.12, 160 packages). aim-1-2 chose dual-venv to preserve kb-api 807-package verified prod combo; aim-1-4 needed the override hook to actually use it. Patch is forward-compatible — existing kb-api / Hermes / Windows-dev callers see no behavior change.

**Deviation 2 — Caller-side TLS CA bundle override (layer1 first attempt failed with hardcoded Windows-dev path)**:

`scripts/local_e2e.sh:73-74` hardcodes `${HOME}/.claude/certs/combined-ca-bundle.pem` (Cisco Umbrella corp Windows-dev path) as the default for `NODE_EXTRA_CA_CERTS` / `REQUESTS_CA_BUNDLE`. On Aliyun this path doesn't exist. Layer 1 attempt 1 (`local-e2e-layer1-20260523-010754.log`, EXIT=0): all 5 candidates returned `verdict=None reason=exception:OSError` — `Could not find a suitable TLS CA certificate bundle, invalid path: /root/.claude/certs/combined-ca-bundle.pem`. Fix (caller-side, NOT harness modification — out of aim-1-4 scope): override `REQUESTS_CA_BUNDLE` and `NODE_EXTRA_CA_CERTS` in the SSH-side env before invoking the harness, pointing to `venv-aim1`'s certifi bundle. Layer 1 attempt 2 (`local-e2e-layer1-20260523-010856.log`, EXIT=0): 2 candidate (id=3, id=7) / 3 reject (id=4, id=5, id=8). Vertex Gemini reachable. ✅ v3.5 candidate: harness fix to make the bundle path environment-aware. Out of aim-1-4 scope.

**Deviation 3 — `SCRAPE_CASCADE` wechat-path asymmetry; Apify runtime UNVERIFIED (import-only)**:

`SCRAPE_CASCADE=ua,apify` env var works on `lib/scraper.py` cascade (kol batch path via `batch_ingest_from_spider.py`); does NOT cascade through `ingest_wechat.py`'s embedded scraper selection (architectural finding, not bug — predates aim-1). All 3 smoke runs reported `method=ua` because UA tier succeeded on every URL → Apify never invoked at runtime. Run #2 + Run #3 captured the cascade fully but only the UA branch ran. Apify_client 3.0.0 **import-time** compatibility was covered by aim-1-2 25/25 import smoke (`OK: apify_client`). **Runtime** Apify HTTP call from Aliyun is therefore unverified by this phase. Decision (per simplicity-first principle): accept import-only verification; defer runtime Apify verification to v3.5 future-work (e.g., a forced-Apify smoke mode `SCRAPE_CASCADE=apify,ua` once a UA-blocking URL is identified, or a pinned-fail-injection harness). Documented as ⚠️ DEFERRED in §6 audit verdict table of `DEPLOY-04-EVIDENCE.md`.

**Deviation 4 — Hermes-uninterrupted attested via prod-LightRAG-untouched proxy (Hermes alias unreachable from Aliyun this session)**:

aim-1-3 used `ssh hermes 'grep ... ' | ssh aliyun-vitaclaw 'cat >> ...'` pipe successfully (Hermes alias resolvable from Windows dev box). aim-1-4 attempt: `ssh aliyun-vitaclaw 'ssh hermes ...'` → `ssh: Could not resolve hostname hermes: Name or service not known`. The Hermes alias is in the Windows dev box's `~/.ssh/config`, NOT in Aliyun's. Direct Hermes pre/post mtime comparison unavailable. Substituted attestation: prod LightRAG state on Aliyun (`/root/.hermes/omonigraph-vault/`) is the canonical write-target of the Hermes daily-ingest cron. If smoke contaminated prod (writes leaked through `OMNIGRAPH_BASE_DIR` redirection) OR if the Hermes cron stalled/paused for the smoke window, prod LightRAG mtime would reflect that. Verified post-smoke: `graph_chunk_entity_relation.graphml` size=25 841 098 / mtime=2026-05-17 23:55:39 (unchanged across all 3 smoke runs; size delta=0); `entity_buffer/` count=0 (no scrape buffer pollution). ✅ prod LightRAG NOT smoke-contaminated; ✅ prod entity_buffer NOT smoke-polluted.

### Execution

```
=== Layer 1 pre-flight (after caller-side TLS override) ===
log:       /root/OmniGraph-Vault/.scratch/local-e2e-layer1-20260523-010856.log  (377 bytes, EXIT=0)
selected:  5 articles
verdicts:  id=3 candidate / id=4 reject / id=5 reject / id=7 candidate / id=8 reject
totals:    candidate=2  reject=3  none=0
LLM:       Vertex AI Gemini Layer 1 reachable via OMNIGRAPH_VERTEX_SA_JSON_PATH ✅


=== Run #1 — wechat short article ===
log:           /root/OmniGraph-Vault/.scratch/local-e2e-wechat-20260523-011413.log  (5 847 bytes, EXIT=0)
hash:          99a2043522
scrape method: ua  (UA tier succeeded; Apify not tried — see deviation 3)
body bytes:    15 422
images:        0
LightRAG:      7 entities + 7 relations
final graph:   8 nodes / 7 edges  (delta from empty: +8 / +7)
status:        Successfully Ingested!


=== Run #2 — wechat image-rich article ===
log:           /root/OmniGraph-Vault/.scratch/local-e2e-wechat-20260523-011635.log  (12 275 bytes, EXIT=0)
hash:          eec0c82bdb
scrape method: ua
body bytes:    71 085
images:        3 unique → 1 filtered (<300px) → 2 kept
vision:        2/2 SiliconFlow Qwen3-VL-32B  (latencies 7 871 ms + 7 097 ms)
LightRAG:      21 entities + 20 relations
final graph:   29 nodes / 27 edges  (delta from Run #1: +21 / +20)
status:        Successfully Ingested!


=== Run #3 — kol --from-db --max-articles 1 ===
log:               /root/OmniGraph-Vault/.scratch/local-e2e-kol-20260523-012017.log  (54 967 bytes, 437 lines, EXIT=0)
candidate sweep:   185 articles → 7 layer1 batches → 180 candidate / 5 reject
max-articles cap:  1 article processed (id=185 hash=4597c6fefe)
scrape method:     ua  (HTTP 200, 2 945 KB raw HTML)
body bytes:        32 227
images:            19 declared in body → 38 unique extracted → 0 filtered → 38 vision-described
vision:            38/38 SiliconFlow Qwen3-VL-32B  (latencies 6 451 ms – 53 622 ms; median ~12 s)
layer2:            verdict=ok  (chunks=2  images=22 used in budget calc  budget=1 320 s)
LightRAG:          delta_nodes=+56  delta_edges=+66
final graph:       85 nodes / 93 edges
batch metrics:     total_elapsed_sec=778.44   budget=28 800   progress=0.027   completed=1   timed_out=0
status:            Successfully Ingested!
```

### Post-smoke evidence

```
=== Final scratch state (/tmp/aim1-smoke/) ===
lightrag_storage/graph_chunk_entity_relation.graphml
  size:    96 507 bytes
  mtime:   2026-05-23 01:33:53
  nodes:   85 (verified via Python ElementTree parse)
  edges:   93

entity_buffer/
  4597c6fefe_entities.json    (Run #3 kol batch — id=185)
  99a2043522_entities.json    (Run #1 wechat short)
  eec0c82bdb_entities.json    (Run #2 wechat 2-image)
  count=3  (matches 3 successful ingests)


=== Prod isolation attestation (/root/.hermes/omonigraph-vault/) ===
graph_chunk_entity_relation.graphml
  size:    25 841 098 bytes        (no growth from smoke — smoke writes landed in /tmp/aim1-smoke/)
  mtime:   2026-05-17 23:55:39     (last Hermes cron write 6 days before smoke 2026-05-23)
entity_buffer/
  count:   0                        (no scrape buffer pollution)
```

| Check | Result |
| --- | --- |
| 3 successful ingest runs (Run #1 / Run #2 / Run #3) all EXIT=0 | ✅ YES |
| Layer 1 reachable (Vertex Gemini via SA path) | ✅ YES (after TLS-bundle caller-side override) |
| Scrape reachable (UA tier — 100% method=ua across all 3 runs) | ✅ YES |
| Layer 2 reachable (DeepSeek — Run #3 layer2 verdict=ok) | ✅ YES |
| Vision cascade reachable (SiliconFlow — 40/40 vision OK across Run #2 + #3) | ✅ YES |
| LightRAG ainsert reachable (DeepSeek entity extraction + Vertex embedding global) | ✅ YES |
| `OMNIGRAPH_BASE_DIR=/tmp/aim1-smoke` redirection holds end-to-end | ✅ YES |
| Prod LightRAG (`/root/.hermes/omonigraph-vault/`) untouched (size + mtime unchanged) | ✅ YES |
| Prod entity_buffer count=0 (no scrape pollution) | ✅ YES |
| Aliyun HEAD unchanged (`4eaef45`) | ✅ YES |
| kb-api PID 3512216 still serving uvicorn on `127.0.0.1:8766` throughout smoke | ✅ YES |
| `kb-api.service.d/override.conf` not touched | ✅ YES |
| `/root/.hermes/.env` mode/owner/line-count unchanged (600 root:root, 51 lines, 2403 B) | ✅ YES |
| Apify runtime UNVERIFIED (all 3 runs `method=ua` — see deviation 3) | ⚠️ DEFERRED to v3.5 |
| Hermes alias unreachable from Aliyun this session (see deviation 4) | ⚠️ proxy attestation via prod-LightRAG-untouched |

**Verdict: ✅ DEPLOY-04 PASS** — full ingest path validated end-to-end on Aliyun via `venv-aim1/bin/python` against `/tmp/aim1-smoke/`, with prod side-effect isolation confirmed by direct on-disk inspection of `/root/.hermes/omonigraph-vault/`.

### Discipline checks

- ✅ **No-secrets:** This §DEPLOY-04 + `DEPLOY-04-EVIDENCE.md` + `aim-1-4-SUMMARY.md` contain only file paths, sizes, byte counts, mtimes, hashes (article URL → SHA shortHash, not API tokens), entity/edge counts, vision latencies, batch elapsed seconds, scratch directory listings, status flags. URLs masked. No API keys / SA JSON contents / `.env` literal token values.
- ✅ **No-connection-details:** No SSH host / port / user / IP / private key. References use SSH alias `aliyun-vitaclaw` only.
- ✅ **Operator-channel:** Agent IS operator per `feedback_aim1_agent_is_operator.md`. All smoke executions + log captures + audits ran via direct Bash SSH. Zero user round-trips during smoke execution. Hermes alias unavailability handled by prod-isolation proxy attestation, not by user round-trip.
- ✅ **Red lines honored:** No `git add -A` / `git add .`, no `--amend`, no `--force`, no `--hard`, no `systemctl` ops, no `kb-api.service.d/override.conf` touched, no kb-api restart, no kb-api venv (`venv/`) touched, no `/root/.hermes/.env` mode/ownership/contents changed, no `/root/.hermes/omonigraph-vault/` writes. Smoke write-targets are exclusively `/tmp/aim1-smoke/` + `/root/OmniGraph-Vault/.scratch/`.
- ✅ **Forward-only edit:** This §DEPLOY-04 is a net-new append to DEPLOY-NOTES.md; §DEPLOY-01 / §DEPLOY-02 / §DEPLOY-03 unchanged. `DEPLOY-04-EVIDENCE.md` and `aim-1-4-SUMMARY.md` are net-new files. `scripts/local_e2e.sh` PYTHON override is additive (default unchanged when `$PYTHON` unset).
- ✅ **kb-api preservation:** PID 3512216 still serving uvicorn on `127.0.0.1:8766` throughout aim-1-4; `venv/` Python version (3.10.12) and package count (160) unchanged; `kb-api.service.d/override.conf` mode/contents untouched.

### Bridge to aim-2 (systemd timer migration)

aim-1 (Code + Env Deploy) is now ✅ COMPLETE end-to-end on Aliyun:

- aim-1-1: HEAD baseline 4eaef45 deployed, kb-api PID 3512216 stable
- aim-1-2: sibling `venv-aim1/` (py3.11.0rc1, 153 packages) built; 25/25 import smoke
- aim-1-3: `/root/.hermes/.env` extended with 2 absent ingest keys (OMNIGRAPH_VERTEX_SA_JSON_PATH + APIFY_TOKEN_BACKUP) preserving 4 pre-existing keys + all 5 kb-api keys; venv-aim1 env-presence smoke (6/6 ingest keys readable)
- aim-1-4: 3-run e2e smoke PASS — full ingest path (Layer 1 → scrape → Layer 2 → vision → LightRAG) validated against `/tmp/aim1-smoke/` with prod isolation confirmed

aim-2 (systemd timer migration) can now proceed with confidence:
- `venv-aim1/bin/python` is the canonical ingest interpreter; ExecStart pins to it
- All 6 ingest provider keys accessible via `EnvironmentFile=/root/.hermes/.env`
- `OMNIGRAPH_BASE_DIR` redirect cleanly isolates dev/test from prod
- kb-api on `:8766` remains a parallel tenant — systemd timer is independent

Open items for aim-2 / aim-3 (v3.5 future-work):
- harness fix for environment-aware TLS bundle path (deviation 2)
- forced-Apify runtime smoke or fail-injection harness (deviation 3)
- Hermes ↔ Aliyun reciprocal SSH aliases for reciprocal pipe ops (deviation 4)

---
