# lib/research — Agentic-RAG-v1 research library

## What this is

`lib/research/` is the Agentic-RAG-v1 research library. It backs the
`omnigraph_research` skill, the `python -m omnigraph.research` CLI (lands in
ar-1-03), and the future HTTP wrapper. The orchestrator runs 5 stages strictly
in order over the LightRAG KG plus optional web search:

```
WebBaseline -> Retriever -> Reasoner -> Verifier -> Synthesizer
```

## Naming (LIB-09 = option a)

Physical path is `lib/research/`. The declared package name in `pyproject.toml`
is `omnigraph.research`, mapped via `[tool.setuptools.package-dir]`. After
`pip install -e .` (lands in ar-1-03 Task 0), both of these resolve to the
same module:

```python
from lib.research import research          # physical path
from omnigraph.research import research    # declared name
```

Rationale: keep all implementation libs at `lib/` (project convention); avoid a
one-off rename that would touch every existing `lib/*.py` import site. The
namespace mapping gives external consumers (skills, CLI, HTTP) the public-
sounding name without forcing the codebase to move.

> Note: `omonigraph-vault` (typo, no second "n") is the canonical runtime data
> directory name. Do **not** "fix" it — see `CLAUDE.md` § "Project Summary".

## Quickstart

```bash
# Smoke import
venv/Scripts/python.exe -c "from lib.research import research, from_env; cfg = from_env(); print(cfg.rag_working_dir)"

# Run unit tests (types + config)
venv/Scripts/python.exe -m pytest tests/unit/research/ -v
```

The `python -m omnigraph.research "<query>"` CLI lands in ar-1-03.

## CONTRACT checklist (manual; pre-commit infra deferred to v1.1)

Before committing any change to `lib/research/`:

- [ ] `bash scripts/check_contract.sh` exits 0 (CONTRACT-01 + CONTRACT-02 clean)
- [ ] Only `omnigraph_search.query.search` is imported from the KG side
      (CONTRACT-01)
- [ ] Hardcoded `~/.hermes` / `omonigraph-vault` paths exist ONLY in
      `lib/research/config.py` (CONTRACT-02)
- [ ] All 7 dataclasses in `types.py` match `CONTEXT.md` verbatim shapes —
      diff before any commit touching `types.py`

## Stage status (ar-1)

| Stage | ar-1 status | Future phase |
|---|---|---|
| WebBaseline | stub (`status="skipped"` if `web_search` returns `[]`) | real Tavily in ar-3 |
| Retriever | wraps `omnigraph_search.query.search()` directly | refinements ar-2 |
| Reasoner | stub (`status="skipped"`, `iter_count=0`) | agent loop ar-2 |
| Verifier | stub (`status="skipped"`, `iter_count=0`) | tools loop ar-3 |
| Synthesizer | minimal markdown synth + CJK heuristic | prompt iteration ar-2/4 |

ar-1-01 (this plan) lands ONLY the package skeleton: types, config, orchestrator
async signatures, namespace mapping, contract grep hook, README. Stage stubs
with the actual `status="skipped"` returns land in ar-1-02.

## Out of scope for ar-1

See `.planning/phases/ar-1-mvp-vertical-slice/ar-1-CONTEXT.md` § "Out of Scope"
for the full deferral table (real Tavily wiring, agent reasoning loop, verifier
tools, telemetry JSONL, HTTP wrapper, image embed in synthesis output, etc.).
