# CONFIG-EXEMPTIONS — kb-databricks-v1

> Initial empty exemption ledger. Created in kdb-1.5; populated in kdb-2 when LLM-DBX-01 + LLM-DBX-02 modify `lib/llm_complete.py` and `kg_synthesize.py`.

## Allowed kb/ + lib/ + top-level *.py edits in this milestone

Per REQUIREMENTS-kb-databricks-v1.md rev 3 constraint #5 ("zero kb/ edits" relaxed):

| File | REQ | Phase | Status |
|------|-----|-------|--------|
| `lib/llm_complete.py` | LLM-DBX-01 | kdb-2 | NOT YET MODIFIED |
| `kg_synthesize.py` | LLM-DBX-02 | kdb-2 | NOT YET MODIFIED |

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
