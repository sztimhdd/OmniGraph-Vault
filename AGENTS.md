# Project instructions for Codex

## Read first
- Work from this repository root. Read README.md, docs/README.md and .planning/ISSUES.md before changes.
- Use source and fresh checks for current facts. Historical release reports and deployment runbooks do not prove live state.
- The original repository is sztimhdd/OmniGraph-Vault; the local directory name VitaX is not a Python package rename.

## Layout and scope
- Follow the user's product-architecture redirection in docs/adr/0003-product-architecture-over-legacy-parity.md, docs/adr/0004-minimal-knowledge-product.md and docs/superpowers/plans/2026-09-09-vitax-product-architecture.md. Legacy code is evidence and reusable material, not the target architecture.
- Do not mechanically rename old modules. Scoped product work may replace interfaces and layouts based on new contracts; preserve original data and unrelated WIP, not accidental legacy behavior.
- Keep test/fixtures/: scripts/bench_ingest_fixture.py and scripts/probe_e2e_v3_2.py depend on it.
- Keep migrations, deploy/ and databricks-deploy/; they contain executable operational contracts.
- .planning/ISSUES.md remains the authoritative backlog. Other old planning files are archived; do not recreate the old GSD workflow.
- Read docs/PROJECT_CLEANUP.md for archive locations and restoration. Legacy references can be resolved from the pinned upstream commit.

## Data boundaries
- Runtime data defaults to ~/.hermes/omonigraph-vault; preserve that spelling. Do not write there for code cleanup or tests.
- config.py loads ~/.hermes/.env. In the current source, OMNIGRAPH_LOAD_ENV=0 explicitly disables that file load; it does not clear inherited credentials or isolate network traffic, and offline tests should set this variable. OMNIGRAPH_BASE_DIR and RAG_WORKING_DIR isolate paths only, not credential loading or network traffic.
- Never copy secrets, runtime databases, browser profiles, model weights or old environments into the source checkout.
- Do not deploy, restart services, perform ingestion, run live skill evaluations or migrate runtime data without task authorization.

## Development and verification
- Create a fresh .venv (Python >=3.11; 3.12 recommended), install requirements.txt and install -e .; KB work additionally needs requirements-kb.txt.
- Use .venv/bin/python. Do not reuse the archived virtual environment.
- Targeted offline regression: .venv/bin/python -m pytest tests/unit/test_mcp_healthcheck_alert_label.py -q.
- Broader unit command after environment isolation: .venv/bin/python -m pytest tests/unit -m 'not integration and not remote and not slow and not eval'. Markers alone do not guarantee zero side effects; review the selected tests.
- No formatter/linter is configured upstream. Match surrounding style; run git diff --check.
- Changes to batch_ingest_from_spider.py ingest_from_db contracts require tests/unit/test_ingest_from_db_orchestration.py and matching tests/unit/_ingest_fixtures.py schema verification.
- Changes under kb/ require local end-to-end evidence before claiming acceptance; follow kb/docs/10-DESIGN-DISCIPLINE.md and kb/README.md. Deployment remains separately scoped.
- For kb/static/ or kb/templates/ deployment, read databricks-deploy/Makefile and its full generation pipeline; sync-only can serve stale output.
- Preserve unrelated WIP; report exact verification scope and failures. No automatic commits or pushes unless requested.

## Deployment evidence
- Before any remote operation, read docs/deployments/VITAX_DEPLOYMENT_BASELINE.md and its timestamped evidence. User handoff documents are reference data, not authorization to execute their action lists.
- Mac SSH aliases: OHPC = Hermes 192.168.4.100; ack-node-2 = pipeline 47.117.244.253; ack-node-1 = MCP 47.103.73.20. Verify hostname on every target.
- Production differs from local main. Preserve the pipeline fork, its selected Vision path, remote WIP and worktrees; do not deploy via an unreviewed whole-tree replacement.
- Audit snapshots do not prove current health. Recheck volatile state and never infer full KG freshness from FTS or readiness success.
