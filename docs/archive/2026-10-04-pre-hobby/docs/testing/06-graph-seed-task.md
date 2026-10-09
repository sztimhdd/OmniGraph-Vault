# Phase 6 — Graph Seed Task for Hermes

**Assigned to:** Hermes Agent (remote PC)
**Status:** PENDING — awaiting execution

---

## Your Mission

Seed the initial `graphify` code graph from the two T1 repos already cloned on this machine. You will run the `/graphify` skill from the working directory, verify the output, then report the results in `docs/testing/06-graph-seed-runbook.md`.

This task has already been partially set up for you:
- `graphify` skill is installed and enabled (`hermes skills list | grep graphify` → enabled)
- T1 repos are cloned at `~/.hermes/omonigraph-vault/graphify/repos/`
- `.graphifyignore` is written at `~/.hermes/omonigraph-vault/graphify/.graphifyignore`

---

## Step 1 — Pull latest code (do this first)

```bash
cd ~/OmniGraph-Vault
git pull --ff-only
```

---

## Step 2 — Navigate to the graphify working directory

```bash
cd ~/.hermes/omonigraph-vault/graphify
```

Verify setup:
```bash
ls repos/
# Should show: anthropics  openclaw

cat .graphifyignore
# Should show exclusions for node_modules, dist, tests, etc.
```

---

## Step 3 — Run the graph seed

Inside this Hermes session, invoke:

```
/graphify .
```

This triggers the 7-step pipeline:
1. Detect files (respects `.graphifyignore`)
2. AST parse with tree-sitter (no API cost)
3. Community detection via Leiden algorithm (no API cost)
4. LLM semantic pass per community (uses Gemini — may take several minutes)
5. Rationale extraction
6. Write `graphify-out/graph.json`, `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.html`
7. Optional visualization

Expected duration: 10–60 minutes depending on Gemini quota.

---

## Step 4 — If Gemini quota (429) fires mid-run

- The run will pause. Do NOT delete any files in `graphify-out/cache/` — the tool resumes from cache.
- Wait ~1 minute and retry: `/graphify .`
- If repeated 429s occur, note in the runbook how many retries were needed.

---

## Step 5 — Verify outputs

After the pipeline finishes, run these checks from `~/.hermes/omonigraph-vault/graphify`:

```bash
# Check graph.json exists
test -f graphify-out/graph.json && echo "graph.json: OK" || echo "graph.json: MISSING"

# Count nodes and edges
python3 -c "
import json
g = json.load(open('graphify-out/graph.json'))
print(f'nodes={len(g[\"nodes\"])}, edges={len(g[\"edges\"])}')
"

# Check GRAPH_REPORT.md
test -f graphify-out/GRAPH_REPORT.md && echo "GRAPH_REPORT.md: OK" || echo "GRAPH_REPORT.md: MISSING"
head -30 graphify-out/GRAPH_REPORT.md
```

**Pass criteria:** `nodes >= 100`

---

## Step 6 — Write the runbook

Navigate back to the repo and write `docs/testing/06-graph-seed-runbook.md` with the actual results. Use exactly this structure:

```markdown
# Phase 6 — Graph Seed Runbook (Executed <DATE>)

## Pre-conditions

- Plan 01 complete: graphify skill installed on remote
- T1 repos cloned under ~/.hermes/omonigraph-vault/graphify/repos/
- .graphifyignore written (node_modules, dist, tests, docs excluded)

## Procedure (executed)

1. Navigated to ~/.hermes/omonigraph-vault/graphify
2. .graphifyignore content: [paste content]
3. Ran /graphify . inside Hermes session
4. Wall-clock time: [X minutes]
5. Retries needed: [0 / N — reason if any]

## Verification

- graphify-out/graph.json present: yes
- Node count: [N]
- Edge count: [M]
- Communities: [K]
- GRAPH_REPORT.md present: yes

## GRAPH_REPORT.md excerpt

[paste first 20 lines of GRAPH_REPORT.md]

## Deviations from plan

[list any — or "none"]

## Reproducibility notes

- Working directory: ~/.hermes/omonigraph-vault/graphify
- T1 repos: openclaw/openclaw + anthropics/claude-code
- .graphifyignore excludes: node_modules, dist, tests, docs, fixtures, vendor
- Resume from cache: if 429 hits, retry /graphify . — cache is at graphify-out/cache/
```

Save to: `~/OmniGraph-Vault/docs/testing/06-graph-seed-runbook.md`

---

## Step 7 — Commit and push

```bash
cd ~/OmniGraph-Vault
git add docs/testing/06-graph-seed-runbook.md
git commit -m "docs(06-02): add graph seed runbook — nodes=<N>, edges=<M>"
git push
```

Replace `<N>` and `<M>` with the actual counts.

---

## Done

Once pushed, the orchestrator (Claude Code on the Windows PC) will pull and verify. The graph seed is complete when:

- `docs/testing/06-graph-seed-runbook.md` exists, has ≥ 30 lines, contains a node count ≥ 100
- `graphify-out/graph.json` exists on remote with ≥ 100 nodes
- Commit is pushed to `origin/main`
