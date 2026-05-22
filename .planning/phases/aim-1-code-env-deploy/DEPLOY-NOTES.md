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
