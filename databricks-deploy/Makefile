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

# Standard deploy: delegates to databricks-deploy/deploy.sh (primary entry point).
# The 4-pass recipe (Pass 0 SSG bake → 0b lang flip → 0c dep stage → 0d brand
# flip → Pass 1 sync → Pass 2 sync → apps deploy) lives in deploy.sh so Windows
# hosts (no GNU make) and Linux hosts (with make) share one code path.
deploy:
	@echo ">>> Delegating to databricks-deploy/deploy.sh (primary entry point)"
	bash $(CURDIR)/deploy.sh

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
