---
phase: arx-2-finish
plan: 03
type: execute
wave: 4
depends_on: ["arx-2-finish-02"]
files_modified:
  - .planning/phases/arx-2-finish/arx-2-finish-03-VERIFICATION.md
autonomous: false   # contains a long-timeout SSH re-probe + a browser-UAT human-verify gate (Principle #5/#6)
requirements: [REQ-1.1-B-4]
must_haves:
  truths:
    - "The 5-stage research pipeline runs end-to-end on the live Aliyun deploy (5 stages execute, terminal report emitted, no crash)"
    - "The Aliyun /research/ UI stepper renders + completes a real query against the deployed KB"
    - "At least one successful Deep Research UI run is demonstrated on Aliyun (the phase goal: user CAN use Deep Research)"
    - "If retriever chunks > 0: the report is real LLM prose (not chunks[0] verbatim) with >= 1 source"
    - "If retriever chunks == 0: the #44 KG-starvation caveat is documented as a KNOWN-LIMITATION, not a phase failure"
  artifacts:
    - path: ".planning/phases/arx-2-finish/arx-2-finish-03-VERIFICATION.md"
      provides: "Aliyun E2E evidence — re-probe retrieved.status/chunks, branch chosen, UI UAT screenshots, #44 caveat if applicable"
      contains: "retrieved"
      min_lines: 40
  key_links:
    - from: "Aliyun research CLI (python -m lib.research)"
      to: "live Aliyun LightRAG KG"
      via: "set -a; source /root/.hermes/.env; set +a; python -m lib.research --dump-state"
      pattern: "dump-state"
    - from: "Aliyun /research/ page"
      to: "POST /api/research SSE"
      via: "Playwright MCP browser_navigate + stepper observation"
      pattern: "/research/"
---

<objective>
GAP E (Aliyun half) — prove a user CAN run Deep Research end-to-end on the LIVE Aliyun
deploy. This is OPS work: no code changes — only a long-timeout retriever re-probe, a
browser UI UAT, and a VERIFICATION.md writeup with CONDITIONAL acceptance branches.

Purpose: Wave 2 shipped the UI and Wave 1 shipped real synthesis, but neither has been
exercised against the real Aliyun KG over the real (slow, cross-border) DeepSeek pipeline.
The phase goal is "user CAN use Deep Research" — proven by at least ONE successful UI run,
NOT by every query succeeding. ISSUE #44 (graphml↔Qdrant divergence) is OUT of scope; if
the retriever starves on vector chunks, that is a documented KNOWN-LIMITATION, not a blocker.

Output: 1 VERIFICATION.md with the re-probe state dump, the branch chosen (A full / B downshift),
UI UAT screenshots, and (if applicable) the #44 caveat.

**Principle discipline:** #5 — the orchestrator/agent runs ALL SSH itself (no user copy-paste
of `ssh aliyun-vitaclaw ...`). #6 — VERIFICATION.md MUST cite real UAT evidence (launcher,
env, command output, screenshot paths), not assertions.

**SHARPENED ALIYUN INTEL (from a 580s re-probe, 2026-06-12):** a prior research CLI run on
the live Aliyun KG produced:
  `Raw search results: 16 entities, 20 relations, 0 vector chunks`
  `Vector similarity chunk selection: no vectors retrieved from chunks_vdb`
  `No entity-related chunks selected by vector similarity, falling back to WEIGHT method`
  `Selecting 20 from 20 entity-related chunks by weighted polling`
INTERPRETATION: #44 vector-chunk starvation (0 vector chunks from chunks_vdb) is REAL on
Aliyun — BUT the WEIGHT fallback STILL recovers 16 entities + 20 relations + 20 entity-related
chunks. So the RESEARCH retriever path is NOT necessarily empty on Aliyun (differs from the
`/api/synthesize long_form` path which returned hard sources=0). The 580s run was SIGKILLed
(OOM on the 3.4Gi box) — the resource/latency wall is REAL. Both facts drive the branches below.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md
@.planning/phases/arx-2-finish/arx-2-finish-00-SUMMARY.md
@CLAUDE.md
@.planning/ISSUES.md

<interfaces>
<!-- ALIYUN OPS FACTS (read before acting): -->
<!-- SSH alias: aliyun-vitaclaw (memory aliyun_vitaclaw_ssh). Caddy serves KB at /var/www/kb/ under /kb/ path prefix. -->
<!-- kb-api is the FastAPI service; /api/research is the SSE endpoint (GAP-D already CONFIRMED LIVE in Wave 0). -->
<!-- Research CLI: `python -m lib.research "<query>" --dump-state <path>` (entry point on the Aliyun checkout). -->
<!--   If --dump-state or the module path differ on Aliyun, FIRST `python -m lib.research --help` to confirm flags. -->
<!-- ENV SOURCING IS MANDATORY (memory aliyun_ssh_manual_trigger_env): -->
<!--   `ssh aliyun-vitaclaw "python ..."` does NOT inherit systemd EnvironmentFile=. -->
<!--   Wrap EVERY manual invocation: `set -a; source /root/.hermes/.env; set +a; <cmd>` -->
<!--   else DEEPSEEK_API_KEY=dummy -> silent 401 -> garbage/empty result that LOOKS like a code bug. -->
<!-- RESOURCE WALL: Aliyun box is 3.4Gi RAM; the full 5-stage DeepSeek cross-border pipeline is slow + memory-heavy. -->
<!--   The prior probe was OOM-SIGKILLed at ~580s. Use `timeout 900` + consider `--max-iterations 1` to shorten -->
<!--   the verifier loop (lowers wall-time AND peak memory). Cross-ref memory wave3_batch_budget_serial_starve. -->

<!-- dump-state JSON shape (read retrieved block): -->
<!--   retrieved.status: "ok" | "failed"; retrieved.chunks: list; retrieved.image_candidates: list -->
<!--   The decision pivot is len(retrieved.chunks): > 0 -> Branch A; == 0 -> Branch B. -->

<!-- ISSUE #44 (.planning/ISSUES.md row 44): graphml↔Qdrant 14-day divergence post-Hermes-transplant. -->
<!--   long_form synthesize returns sources=0 because hybrid retrieval finds Qdrant chunks but the entity/rel -->
<!--   nodes don't exist in graphml. The fix is Path X (cron rebuild) or Path Y (Hermes batch) — BOTH OUT of -->
<!--   this phase. If research retriever ALSO shows 0 chunks, cite this row as the root cause in VERIFICATION. -->

<!-- GAP-D is already CONFIRMED LIVE (Wave 0 SUMMARY): Aliyun HEAD has 38a7286 as ancestor, POST /api/research -->
<!--   returns 200 + streams. DO NOT re-pull, DO NOT restart kb-api. This plan is read + UAT only. -->
</interfaces>
</context>

<tasks>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 1: Long-timeout Aliyun retriever re-probe — capture dump-state, read retrieved.status + len(chunks) + len(image_candidates), CHOOSE the acceptance branch</name>
  <read_first>
    - CLAUDE.md Principle #5 (orchestrator/agent runs SSH itself — NO user copy-paste)
    - Memory aliyun_ssh_manual_trigger_env (env MUST be sourced or silent 401)
    - Memory aliyun_vitaclaw_ssh (SSH alias + Aliyun layout)
    - Memory wave3_batch_budget_serial_starve (resource/latency wall context)
    - .planning/ISSUES.md row #44 (the #44 caveat text to cite if chunks == 0)
    - .planning/phases/arx-2-finish/arx-2-finish-00-SUMMARY.md (GAP-D CONFIRMED-LIVE — no pull/restart)
  </read_first>
  <what-built>
    No code. A live retriever re-probe against the Aliyun KG to settle which acceptance branch
    applies. The orchestrator/agent runs the SSH itself (Principle #5). GAP-D is already live
    (Wave 0) so this does NOT pull or restart — it only READS the pipeline's retriever state.
  </what-built>
  <how-to-verify>
    The orchestrator/agent (NOT the user) runs the re-probe over SSH. Env MUST be sourced.
    Use a generous timeout and a short verifier loop to dodge the OOM/latency wall:
    ```bash
    ssh aliyun-vitaclaw 'cd ~/OmniGraph-Vault 2>/dev/null || cd /var/www/omnigraph-source; \
      set -a; source /root/.hermes/.env; set +a; \
      timeout 900 python -m lib.research "What is LightRAG?" \
        --max-iterations 1 --dump-state /tmp/arx-aliyun-dumpstate.json 2>&1 | tail -40; \
      echo "=== DUMP-STATE retrieved block ==="; \
      python -c "import json; d=json.load(open(\"/tmp/arx-aliyun-dumpstate.json\")); r=d.get(\"retrieved\") or {}; print(\"status=\",r.get(\"status\")); print(\"chunks=\",len(r.get(\"chunks\") or [])); print(\"image_candidates=\",len(r.get(\"image_candidates\") or []))"'
    ```
    (If `python -m lib.research --help` shows different flag names for --dump-state / --max-iterations,
    adapt — confirm flags FIRST. If the repo path differs, the Wave-0 probe recorded the real path.)

    READ the printed `status` / `chunks` / `image_candidates`, then CHOOSE the branch:
    - **len(chunks) > 0** -> Branch A (full E2E acceptance — proceed to Task 2 Branch A).
    - **len(chunks) == 0** -> Branch B (downshift acceptance — proceed to Task 2 Branch B + #44 caveat).
    - **SIGKILL / OOM / timeout 900 hit** (no clean dump): note it, RETRY once with `--max-iterations 1`
      (if not already) and/or a smaller query; if it still walls, document as a KNOWN Aliyun-perf
      constraint (cross-ref wave3_batch_budget_serial_starve) and fall back to Task 2 Branch B
      using the UI run as the end-to-end proof (the UI invocation may complete even when the CLI OOMs,
      since kb-api is a long-lived process not a one-shot CLI).

    Record VERBATIM in VERIFICATION.md: the exact command, the tail-40 stage log, the retrieved
    block (status/chunks/image_candidates), and the branch chosen with its trigger value.
  </how-to-verify>
  <acceptance_criteria>
    - VERIFICATION.md records the exact re-probe command (with `set -a; source /root/.hermes/.env; set +a` visible — proves env sourcing per Principle #5 + memory).
    - VERIFICATION.md records `retrieved.status`, `len(retrieved.chunks)`, `len(retrieved.image_candidates)` from the dump-state (or the SIGKILL/OOM observation if the run walled).
    - VERIFICATION.md states the branch chosen (A / B) and the trigger value (chunks > 0 vs == 0 vs walled).
    - No `git pull` / `kb-api restart` performed (GAP-D already live).
  </acceptance_criteria>
  <resume-signal>Report the retrieved block (status / chunks / image_candidates) and the branch chosen ("Branch A — chunks=N", "Branch B — chunks=0 / #44 starvation", or "Branch B — CLI walled, UI-only proof").</resume-signal>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 2: Aliyun /research/ browser UI UAT (Playwright MCP, main session) — stepper renders + completes; capture screenshots; write VERIFICATION with the conditional-acceptance result</name>
  <read_first>
    - CLAUDE.md Principle #6 (cite real UAT evidence in VERIFICATION — launcher, env, output, screenshots)
    - .planning/phases/arx-2-finish/arx-2-finish-RESEARCH.md §5-STAGE STEPPER (what the UI should show streaming)
    - Memory aliyun_kb_serve_dir_gap (Caddy serves /kb/ — the research page is at the /kb/research/ URL on Aliyun)
    - The Task 1 branch decision (A or B) — it sets the acceptance bar for THIS task
  </read_first>
  <what-built>
    No code. A real browser UAT against the LIVE Aliyun KB /research/ page using Playwright MCP
    (main session — NEVER a sub-agent; the Databricks proxy strips tool_reference from sub-agents
    so mcp__playwright__* calls fail there). Drives one real research query and observes the
    5-stage stepper streaming + the final report.
  </what-built>
  <how-to-verify>
    Playwright MCP loop (main session only, per CLAUDE.md MCP rule):
    1. `browser_navigate` to the Aliyun research page (the Caddy /kb/ prefix path — confirm the exact
       URL from the live deploy; the page is the SSG-baked `research/index.html` served under /kb/research/).
    2. `browser_snapshot` to get element refs; `browser_type` a real query ("What is LightRAG?"),
       set max_iterations to 1 (matches the Task-1 probe; keeps wall-time inside browser patience),
       `browser_click` submit.
    3. `browser_wait_for` the stepper to progress through all 5 stages then the final report
       (generous time budget — the cross-border DeepSeek pipeline is slow; allow up to OMNIGRAPH_LLM_TIMEOUT_SEC).
    4. `browser_take_screenshot` at: (a) stepper mid-stream (some steps running/done),
       (b) final report rendered. Save to `.playwright-mcp/arx-aliyun-uat-*.png`.
    5. `browser_console_messages(level="error")` + `browser_network_requests()` to confirm the
       POST /api/research returned 200 and SSE streamed (no 4xx/5xx).

    **ACCEPTANCE BRANCHES (write BOTH into VERIFICATION; apply the one Task 1 selected):**

    **Branch A — retriever chunks > 0 (weight-fallback works): FULL E2E acceptance.**
    - The research CLI (Task 1) produced a real markdown report with real LLM prose — NOT
      `chunks[0]` verbatim, NOT empty — with >= 1 source. Cite the report excerpt + source count.
    - The UI run shows the stepper completing AND a real rendered report (markdown + any images +
      Sources list). Cite both screenshots.
    - VERIFICATION marks Aliyun E2E = PASS (full).

    **Branch B — retriever chunks == 0 (full #44 starvation): DOWNSHIFT acceptance.**
    Prove the THREE downshift conditions (NOT a phase failure):
    1. The pipeline RUNS end-to-end on Aliyun: all 5 stages execute, a terminal report is emitted,
       no crash (cite the Task-1 tail-40 stage log or the UI stepper reaching synthesizer + done).
    2. The UI stepper RENDERS + COMPLETES against Aliyun (cite both screenshots — stepper + terminal state,
       even if the report body is the graceful-degrade fallback rather than rich prose).
    3. The #44 KG-starvation caveat is DOCUMENTED as a KNOWN-LIMITATION: cite the `0 vector chunks`
       evidence from Task 1 + cross-ref ISSUE #44 (graphml↔Qdrant divergence, fix = Path X / Path Y,
       OUT of this phase). Do NOT block the phase on the graphml rebuild.
    - VERIFICATION marks Aliyun E2E = PASS (downshifted) with the #44 caveat called out explicitly.

    **In BOTH branches:** if the run hits the resource/latency wall (SIGKILL / OOM / timeout), note it,
    retry once with `--max-iterations 1` and/or a smaller query, and document as a known Aliyun-perf
    constraint (cross-ref wave3_batch_budget_serial_starve). The phase goal is "user CAN use Deep
    Research", proven by AT LEAST ONE successful UI run — not by every query succeeding.

    Write `.planning/phases/arx-2-finish/arx-2-finish-03-VERIFICATION.md` with: launcher/SSH command,
    env sourcing line, Task-1 retrieved block, branch chosen, curl/CLI excerpt, screenshot paths,
    network 200 evidence, and (Branch B) the #44 caveat block.
  </how-to-verify>
  <acceptance_criteria>
    - `.planning/phases/arx-2-finish/arx-2-finish-03-VERIFICATION.md` exists; `grep -q "retrieved" ...` AND `grep -q "Branch" ...` succeed; `grep -Ei "screenshot|playwright-mcp" ...` succeeds (cites UI evidence per Principle #6).
    - At least 2 screenshots saved under `.playwright-mcp/arx-aliyun-uat-*.png` (stepper mid-stream + final report). `ls .playwright-mcp/arx-aliyun-uat-*.png | wc -l` returns >= 2.
    - VERIFICATION records network evidence that `POST /api/research` returned 200 + streamed SSE (from browser_network_requests).
    - Branch A: VERIFICATION shows the report is real prose (not chunks[0] verbatim) + >= 1 source AND the UI completed. Branch B: VERIFICATION proves the 3 downshift conditions AND cites the #44 caveat (`grep -q "#44" ...` or `grep -qi "graphml" ...` succeeds) cross-referencing ISSUES.md row 44.
    - At least ONE successful Deep Research UI run is demonstrated on Aliyun (stepper completed + terminal report rendered).
  </acceptance_criteria>
  <resume-signal>Type "Aliyun E2E PASS (Branch A)" or "Aliyun E2E PASS (Branch B — #44 downshift)" with the screenshot paths, or report the blocker if no UI run completed at all.</resume-signal>
</task>

</tasks>

<verification>
- VERIFICATION.md cites the Task-1 retrieved block (status / chunks / image_candidates) and the chosen branch.
- >= 2 Playwright screenshots under `.playwright-mcp/arx-aliyun-uat-*.png` showing the stepper + final report.
- Branch B (if taken): the #44 KG-starvation caveat is documented as a KNOWN-LIMITATION cross-referencing ISSUES.md row 44 — NOT logged as a phase failure.
- No `git pull` / kb-api restart performed (GAP-D already CONFIRMED-LIVE in Wave 0).
- All SSH run by the orchestrator/agent itself (Principle #5) with env sourced (no silent 401).
</verification>

<success_criteria>
- At least one successful Deep Research UI run is demonstrated on the LIVE Aliyun deploy (phase goal: user CAN use Deep Research).
- The acceptance branch matches the live retriever state: A (full, chunks > 0) or B (downshift, chunks == 0 with #44 caveat).
- REQ-1.1-B-4 Aliyun-equivalent E2E evidence is cited in VERIFICATION per Principle #6.
- ISSUE #44 (graphml rebuild) is NOT treated as a blocker — it stays an out-of-scope KNOWN-LIMITATION.
</success_criteria>

<output>
After completion, create `.planning/phases/arx-2-finish/arx-2-finish-03-SUMMARY.md`
</output>
