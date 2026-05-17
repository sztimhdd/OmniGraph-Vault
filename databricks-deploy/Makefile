# databricks-deploy/Makefile — kdb-2-04 deploy + ops recipes.
# Targets: deploy / logs / stop / smoke / sp-grants
# Uses --profile dev throughout (matches kdb-1.5 dry-run pattern).
# Windows Git Bash safe: MSYS_NO_PATHCONV=1 only on path-bearing calls.
#
# CLI subcommand surface verified empirically (kdb-2-04 Task 4.2):
#   apps create / delete / deploy / get / get-deployment / list /
#   list-deployments / run-local / start / stop / update — all exist
#   apps logs — DOES NOT EXIST (must use Workspace UI Apps tab)
#   apps get-permissions — exists at App level (not endpoint level)

.PHONY: deploy logs stop smoke sp-grants

# Sync repo + deploy. --source-code-path points at databricks-deploy/ so
# app.yaml is at the source-code-path root (DEPLOY-DBX-02 constraint).
# The whole-repo workspace import is required so kb/ lands as a sibling
# of databricks-deploy/ (Wave-0 layout to be validated per kdb-2-04 Task 4.0).
deploy:
	MSYS_NO_PATHCONV=1 databricks --profile dev workspace import-dir \
	  . /Workspace/Users/hhu@edc.ca/omnigraph-kb --overwrite
	databricks --profile dev apps deploy omnigraph-kb \
	  --source-code-path /Workspace/Users/hhu@edc.ca/omnigraph-kb/databricks-deploy \
	  --timeout 20m
	databricks --profile dev apps get omnigraph-kb -o json

# Apps logs not exposed via CLI (verified empirically in kdb-2-04 Task 4.2:
# 'logs' missing from `databricks apps --help` Available Commands list).
# Recipe echoes Workspace UI URL + queries deploy state via 'apps get'.
logs:
	@echo "Apps logs only via Workspace UI Apps tab (databricks apps logs subcommand does not exist)."
	@echo "URL: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
	databricks --profile dev apps get omnigraph-kb -o json

# 'databricks apps stop' subcommand confirmed via empirical probe in
# kdb-2-04 Task 4.2 (`apps stop --help` returned full help text with
# --no-wait + --timeout flags).
stop:
	databricks --profile dev apps stop omnigraph-kb

# Smoke 1+2 manual UAT (Decision 4 — Private Link blocks external curl).
# Recipe just echoes the workspace UI URL + the kdb-2-04 plan checklist.
smoke:
	@echo "Smoke 1+2 manual UAT (browser-SSO interactive UAT)."
	@echo "Workspace UI: https://adb-2717931942638877.17.azuredatabricks.net/apps/omnigraph-kb"
	@echo "App URL (post-SSO): https://omnigraph-kb-2717931942638877.17.azure.databricksapps.com"
	@echo "Checklist: see .planning/phases/kdb-2-databricks-app-deploy/kdb-2-04-deploy-and-smoke-PLAN.md Tasks 4.5 + 4.6"
	@echo "Capture screenshots to .planning/phases/kdb-2-databricks-app-deploy/kdb-2-SMOKE-EVIDENCE.md."

# Informational — kdb-2-01 already executed AUTH-DBX-01..04 grants.
# Recipe documents the audit pattern (re-runnable; idempotent).
# App SP client_id is a stable GUID per the apps create response.
sp-grants:
	@CLIENT_ID=$$(databricks --profile dev apps get omnigraph-kb -o json | python -c "import json,sys; print(json.load(sys.stdin)['service_principal_client_id'])"); \
	  echo "App SP client_id: $$CLIENT_ID"; \
	  echo ""; \
	  echo "AUTH-DBX-01..03 grants (run via mcp__databricks-mcp-server execute_sql):"; \
	  echo "  GRANT USE CATALOG ON CATALOG mdlg_ai_shared TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT USE SCHEMA ON SCHEMA mdlg_ai_shared.kb_v2 TO \`$$CLIENT_ID\`;"; \
	  echo "  GRANT READ VOLUME ON VOLUME mdlg_ai_shared.kb_v2.omnigraph_vault TO \`$$CLIENT_ID\`;"; \
	  echo ""; \
	  echo "AUTH-DBX-04 verification (Path A inconclusive in v0.260+ for Foundation"; \
	  echo "Models — endpoint .id field absent; default permissive ACL applies):"; \
	  echo "  Path B = in-app probe via WorkspaceClient().serving_endpoints.query()"; \
	  echo "  during kdb-2-04 Wave 0 / first deploy."
