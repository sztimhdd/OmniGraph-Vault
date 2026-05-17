# CONFIG-EXEMPTIONS — kb-databricks-v1

> Initial empty exemption ledger. Created in kdb-1.5; populated in kdb-2 when LLM-DBX-01 + LLM-DBX-02 modify `lib/llm_complete.py` and `kg_synthesize.py`.

## Allowed kb/ + lib/ + top-level *.py edits in this milestone

Per REQUIREMENTS-kb-databricks-v1.md rev 3 constraint #5 ("zero kb/ edits" relaxed):

| File | REQ | Phase | Status |
|------|-----|-------|--------|
| `lib/llm_complete.py` | LLM-DBX-01 + LLM-DBX-04 (translation per Decision 1) | kdb-2 | MODIFIED (kdb-2-02 — see commit 50a7386) |
| `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | MODIFIED (quick-260509-s29 W3 — dispatcher route already in place; kdb-2-03 confirms via integration test in commit f3670b0) |

## Verification command (run at kdb-3 close per CONFIG-DBX-01)

```bash
git log <milestone-base>..HEAD --grep '(kdb-' --name-only -- \
  kb/ \
  lib/ \
  | grep -v -E '^lib/llm_complete\.py$|^kg_synthesize\.py$' \
  | sort -u
```

Returns empty when CONFIG-DBX-01 is satisfied. `<milestone-base>` is `cfe47b4` per STATE-kb-databricks-v1.md.

## Phase kdb-1.5 contribution

Phase kdb-1.5 modifies ZERO files under `kb/`, `lib/`, or top-level `*.py`. All deliverables are NEW files under `databricks-deploy/`. CONFIG-DBX-01 verification for this phase's commits MUST return empty.

## Phase kdb-2-02 contribution

Plan kdb-2-02 modifies `lib/llm_complete.py` (allowed per CONFIG-EXEMPTIONS rev 1)
to add the `databricks_serving` provider branch (LLM-DBX-01) plus an exception-
translation shim that satisfies LLM-DBX-04 entirely inside the dispatcher per
phase Decision 1 — `kb/services/synthesize.py` is NOT modified, CONFIG-EXEMPTIONS
is NOT extended. Translation re-raises Databricks SDK 503/429/timeout/connection
errors unchanged so the existing `except Exception as e` handler in
`kb/services/synthesize.py:448` routes to the `kg_unavailable` reason-code
bucket (kb-v2.1-1 KG MODE HARDENING contract).

## Phase kdb-2-03 contribution

Plan kdb-2-03 contributes ZERO net code changes to `kg_synthesize.py` (the
dispatcher integration at line 19 + line 106 was historical, shipped in
quick-260509-s29 W3). The plan adds `tests/integration/test_kg_synthesize_dispatcher.py`
(NEW) with 2 tests verifying:

  1. `OMNIGRAPH_LLM_PROVIDER=databricks_serving` actually exercises the
     kdb-2-02 dispatcher branch through `synthesize_response` (LLM-DBX-02
     env-var-exercise contract from REQ line 39).
  2. The dispatcher's translation shim re-raises Databricks SDK 503/429/
     timeout errors unchanged so `kb/services/synthesize.py`'s existing
     `except Exception as e` handler routes to the existing `kg_unavailable`
     reason-code bucket (LLM-DBX-04 via phase Decision 1 — no new reason
     code, no `kb/services/synthesize.py` modification, no CONFIG-EXEMPTIONS
     extension).

`kg_synthesize.py` row in this ledger is flipped from NOT YET MODIFIED to
MODIFIED so the audit at kdb-3 close (`git log cfe47b4..HEAD --grep '(kdb-'
--name-only -- kb/ lib/`) cleanly excludes the historical change via the
CONFIG-EXEMPTIONS allowed-edit list.
