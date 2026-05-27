# databricks-deploy/Makefile — kdb-2-04 + kb-v2.2-7 deploy + ops recipes.
# Targets: deploy / deploy-clean / logs / stop / smoke / sp-grants
# Uses --profile dev throughout. Windows Git Bash safe (MSYS_NO_PATHCONV=1
# only on path-bearing calls).
#
# CLI subcommand surface verified empirically (kdb-2-04 Task 4.2,
# re-checked on CLI v0.260.0 2026-05-20):
#   apps create / delete / deploy / get / get-deployment / list /
#   list-deployments / run-local / start / stop / update — all exist
#   apps logs — DOES NOT EXIST as a CLI subcommand. The Workspace UI's
#   Apps "Logs" panel uses a token-authed WebSocket at /logz/stream;
#   `make logs` now reproduces that protocol via scripts/tail_app_logs.py
#   so logs can be fetched without copy-pasting from the browser.
#
# Sync architecture (kb-v2.2-7 update 2026-05-20):
#   Pass 1: project-root databricks-deploy/* → workspace databricks-deploy/
#           (carries app.yaml, requirements.txt, app helpers, startup_adapter)
#   Pass 2: project-root kb/*               → workspace databricks-deploy/kb/
#           (drops kb/ INSIDE the source-code-path so `import kb.api` resolves
#            natively at /app/python/source_code/kb/ — no PYTHONPATH gymnastics)
#
# Why 2 passes: source_code_path = databricks-deploy/, but kb/ lives at the
# project root. Without pass 2, /app/python/source_code/ has no kb/ subtree
# and `from kb.api import app` fails. The previous `workspace import-dir .`
# from project root flooded the workspace with lib/, batch_*.py, .planning/,
# etc. — see .databricksignore for the exclude list now enforced.

.PHONY: deploy deploy-clean logs logs-tail stop smoke sp-grants

WORKSPACE_ROOT := /Workspace/Users/hhu@edc.ca/omnigraph-kb
APP_NAME       := omnigraph-kb
PROFILE        := dev

# Standard deploy: incremental sync + apps deploy. Safe to re-run.
deploy:
	@echo ">>> Pass 0: refresh databricks-deploy/_ssg/ from kb/output/ (deploy-time SSG)"
	rm -rf ./databricks-deploy/_ssg
	cp -R ./kb/output ./databricks-deploy/_ssg
	@# Drop the inner .gitignore (`*` rule) that databricks sync would
	@# otherwise honor, excluding every file inside _ssg/ from upload.
	rm -f ./databricks-deploy/_ssg/.gitignore
	@echo ">>> Pass 0b: flip KB_DEFAULT_LANG zh-CN -> en for Databricks audience"
	@# kb/output/ is the shared SSG snapshot built with the Aliyun-default
	@# (zh-CN) Jinja env. The HTML carries BOTH languages inline as
	@# <span data-lang="zh">/<span data-lang="en"> pairs; lang.js shows one
	@# based on <html lang> + window.KB_DEFAULT_LANG. We only need to flip
	@# those two markers in-place — no full SSG rebuild required.
	find ./databricks-deploy/_ssg -name '*.html' -print0 | \
	  xargs -0 sed -i 's|<html lang="zh-CN">|<html lang="en">|g; s|window\.KB_DEFAULT_LANG = "zh-CN"|window.KB_DEFAULT_LANG = "en"|g'
	@echo ">>> Pass 0c: stage project-root synthesize deps (kdb-3)"
	@# kb/services/synthesize.py imports kg_synthesize → which imports
	@# config + lib.* . Those live at the project root, OUTSIDE the
	@# Pass-1 sync source (databricks-deploy/) and the Pass-2 sync source
	@# (kb/). Mirror the _ssg/ pattern: copy them into databricks-deploy/
	@# as deploy-time artifacts. They are NOT gitignored (Pass-1 sync
	@# would skip them); they are regenerated each deploy so any stale
	@# copy is overwritten.
	rm -rf ./databricks-deploy/kg_synthesize.py ./databricks-deploy/config.py ./databricks-deploy/lib
	cp ./kg_synthesize.py ./databricks-deploy/kg_synthesize.py
	cp ./config.py ./databricks-deploy/config.py
	cp -R ./lib ./databricks-deploy/lib
	@echo ">>> Pass 0d: rebrand _ssg for Databricks audience (Aliyun untouched)"
	@# Three Databricks-only mods, all confined to ./databricks-deploy/_ssg/:
	@#  1. Logo: overwrite VitaClaw-Logo-v0.png with kb/kb-logo.png. Filename
	@#     preserved so HTML <img src> references need no rewrite.
	@#  2. Brand strings: replace VitaClaw / 企小勤 (and combined forms) with
	@#     'EDC Agentic AI Knowledge Base'. Longer combined forms must be
	@#     replaced first to avoid double-substitution. The logo path
	@#     'VitaClaw-Logo-v0.png' contains 'VitaClaw' — shielded with a
	@#     placeholder swap so the bare 'VitaClaw' replacement does not
	@#     mangle the asset path.
	@#  3. lang.js detectFromBrowser: short-circuit to return DEFAULT_LANG.
	@#     KB_DEFAULT_LANG=en (app.yaml) alone is insufficient — for users
	@#     with navigator.languages=['zh-CN', ...], detectFromBrowser persists
	@#     'zh-CN' to cookie on first visit BEFORE the DEFAULT_LANG fallback
	@#     fires. Neutralizing the function makes English the true first-visit
	@#     default; the manual lang-toggle still works.
	@# kb/ source unchanged: Aliyun deploy reads kb/output/ directly and
	@# keeps its zh-CN-default + 企小勤/VitaClaw branding.
	cp ./kb/kb-logo.png ./databricks-deploy/_ssg/static/VitaClaw-Logo-v0.png
	find ./databricks-deploy/_ssg -name '*.html' -print0 | \
	  xargs -0 sed -i \
	    -e 's|VitaClaw-Logo-v0\.png|__KB_LOGO_FILE__|g' \
	    -e 's|企小勤 / VitaClaw — AI Agent 技术圈双语知识库|EDC Agentic AI Knowledge Base|g' \
	    -e 's|企小勤知识库 — AI Agent 技术内容站|EDC Agentic AI Knowledge Base|g' \
	    -e 's|企小勤 / VitaClaw|EDC Agentic AI Knowledge Base|g' \
	    -e 's|企小勤 VitaClaw|EDC Agentic AI Knowledge Base|g' \
	    -e 's|VitaClaw 企小勤|EDC Agentic AI Knowledge Base|g' \
	    -e 's|VitaClaw|EDC Agentic AI Knowledge Base|g' \
	    -e 's|企小勤|EDC Agentic AI Knowledge Base|g' \
	    -e 's|__KB_LOGO_FILE__|VitaClaw-Logo-v0.png|g'
	@# Force English-default by neutralizing detectFromBrowser's per-language
	@# returns. Replacing the two interior 'return zh-CN' / 'return en' lines
	@# with 'return DEFAULT_LANG' is safer than rewriting the whole function
	@# body via sed (sed cannot match balanced braces — the inner for-loop }
	@# would short-circuit and orphan the trailing return + closing brace).
	sed -i \
	  -e "s|if (l.indexOf('zh') === 0) return 'zh-CN';|if (l.indexOf('zh') === 0) return DEFAULT_LANG;|" \
	  -e "s|if (l.indexOf('en') === 0) return 'en';|if (l.indexOf('en') === 0) return DEFAULT_LANG;|" \
	  ./databricks-deploy/_ssg/static/lang.js
	@echo ">>> Pass 1: sync databricks-deploy/* → workspace/databricks-deploy/"
	@# --include overrides the project-root .gitignore rules (databricks sync
	@# honors .gitignore by default). Three families of staged artifacts must
	@# be force-included or sync silently skips them:
	@#   1. _ssg/**          — pre-rendered SSG output (.gitignore L91)
	@#   2. kg_synthesize.py — Pass-0c project-root LightRAG entry (L94)
	@#   3. config.py        — Pass-0c project-root config (L93)
	@#   4. lib/**           — Pass-0c project-root LLM/embed providers (L92)
	@# Verified 2026-05-21 (Issue #3 SSG empty after deploy) and 2026-05-27
	@# (arx-3 singleton REGRESSION: deployed kg_synthesize.py was an OLD
	@# pre-singleton copy because Pass-0c staged it but Pass-1 sync silently
	@# skipped it — graph reloaded on every synthesize call, ~28s wall-time
	@# per request. Without these explicit includes, every Pass-0c artifact
	@# is gitignored away. Sync reports "Initial Sync Complete" with zero
	@# errors regardless — the failure mode is silent skip, not error.
	MSYS_NO_PATHCONV=1 databricks --profile $(PROFILE) sync --full \
	  --include "_ssg/**" \
	  --include "kg_synthesize.py" \
	  --include "config.py" \
	  --include "lib/**" \
	  ./databricks-deploy $(WORKSPACE_ROOT)/databricks-deploy
	@echo ">>> Pass 2: sync kb/* → workspace/databricks-deploy/kb/"
	MSYS_NO_PATHCONV=1 databricks --profile $(PROFILE) sync --full \
	  ./kb $(WORKSPACE_ROOT)/databricks-deploy/kb
	@echo ">>> Deploy app from $(WORKSPACE_ROOT)/databricks-deploy"
	MSYS_NO_PATHCONV=1 databricks --profile $(PROFILE) apps deploy $(APP_NAME) \
	  --source-code-path $(WORKSPACE_ROOT)/databricks-deploy
	databricks --profile $(PROFILE) apps get $(APP_NAME) -o json

# Clean deploy: wipe workspace dir first, then sync + deploy. Use after
# .databricksignore changes or when workspace pollution is suspected.
deploy-clean:
	@echo ">>> WIPE $(WORKSPACE_ROOT) (recursive)"
	-MSYS_NO_PATHCONV=1 databricks --profile $(PROFILE) workspace delete \
	  --recursive $(WORKSPACE_ROOT)
	$(MAKE) deploy

# Snapshot recent logs (BUILD + APP frames) and exit. No copy-paste from
# the Workspace UI Apps tab. The /logz/stream WebSocket is the only logs
# channel the platform exposes; tail_app_logs.py speaks that protocol.
logs:
	../venv/Scripts/python.exe scripts/tail_app_logs.py --once --max-seconds 15

# Live tail until Ctrl-C. Optional FILTER=<term> for server-side substring
# filter (matches the Workspace UI search box).
logs-tail:
	../venv/Scripts/python.exe scripts/tail_app_logs.py $(if $(FILTER),--filter "$(FILTER)",)

stop:
	databricks --profile $(PROFILE) apps stop $(APP_NAME)

# Smoke 1+2 manual UAT (Decision 4 — Private Link blocks external curl).
smoke:
	@echo "Smoke 1+2 manual UAT (browser-SSO interactive UAT)."
	@echo "Workspace UI: https://adb-2717931942638877.17.azuredatabricks.net/apps/$(APP_NAME)"
	@echo "App URL (post-SSO): https://$(APP_NAME)-2717931942638877.17.azure.databricksapps.com"
	@echo "Verify: GET /health → {status: ok, kb_db_path, kb_images_dir, version}"
	@echo "Verify: GET /api/articles → list (KB_DB_PATH must point to populated FTS5 DB)"
	@echo "Verify: GET /api/search?mode=fts&q=agent → results"

# Informational — kdb-2-01 already executed AUTH-DBX-01..04 grants.
sp-grants:
	@CLIENT_ID=$$(databricks --profile $(PROFILE) apps get $(APP_NAME) -o json | python -c "import json,sys; print(json.load(sys.stdin)['service_principal_client_id'])"); \
	  echo "App SP client_id: $$CLIENT_ID"; \
	  echo ""; \
	  echo "AUTH-DBX-01..03 grants (run via mcp__databricks-mcp-server execute_sql):"; \
	  echo "  GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO \`$$CLIENT_ID\`;"
