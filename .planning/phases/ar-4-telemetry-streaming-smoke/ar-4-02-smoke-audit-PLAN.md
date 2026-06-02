---
phase: ar-4-telemetry-streaming-smoke
plan: 02
type: execute
wave: 2
depends_on:
  - ar-4-01
files_modified:
  - scripts/smoke_milestone.py
  - .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md
  - lib/research/stages/synthesizer.py
autonomous: false
status: planned
last_updated: "2026-05-23"
requirements:
  - TEST-05
  - TEST-06

must_haves:
  truths:
    - "scripts/smoke_milestone.py exists, is executable as `python scripts/smoke_milestone.py` (no positional args), uses the hardcoded query string `Hermes Harness 深度解析`, and writes telemetry JSONL to `.scratch/smoke-telemetry-<unix-ts>.jsonl`"
    - "smoke driver computes condition (a) via regex `re.findall(r\"!\\[[^\\]]*\\]\\(http://localhost:8765/\", result.markdown)` and asserts count ≥ 3 inline images"
    - "smoke driver reads condition (b) directly from `result.state.verified.confidence` and asserts `>= 60.0` (float)"
    - "smoke driver measures condition (c) wall time as `time.time() - t0` around the `await research(...)` call and asserts `<= 240.0` seconds"
    - "smoke driver verifies condition (d) by parsing the telemetry JSONL line-by-line, collecting any `event_type==stage_end` entries with `status==failed`, and asserting the resulting list is empty"
    - "smoke driver computes condition (e) Chinese-language ratio after stripping inline-image markdown and bare URLs, counting CJK chars (range `一-鿿`) over total non-whitespace chars, and asserts `>= 0.5`"
    - "smoke driver emits a JSON verdict on stdout containing all 10 fields (a_image_count + a_pass, b_confidence + b_pass, c_elapsed_s + c_pass, d_failed_stages + d_pass, e_cjk_ratio + e_pass) and exits 0 if and only if every `*_pass` is True"
    - "TEST-05 milestone-close smoke runs on the Hermes deployment target (orchestrator SSHes via Bash per memory `hermes_ssh.md`; never asks user to copy-paste SSH commands per global principle #5)"
    - "If any of the 5 TEST-05 conditions fails on first run, ar-4 enters a remediation sub-cycle: diagnose → patch (prefer Synthesizer prompt iteration in `lib/research/stages/synthesizer.py` per ROADMAP § Cross-phase touches ORCH-05 blessing) → re-run smoke; max 3 iterations before user escalation"
    - "After smoke passes, the orchestrator authors `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` with verbatim header (date + smoke command + telemetry path + dump-state path), agentic-RAG markdown excerpt or `cat` reference, Telegram session JSON excerpts from `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`, per-dimension table (5 rows: name, score 1-5, narrative 2-4 sentences), final PASS/FAIL verdict, and operator signoff line"
    - "TEST-06 audit verdict is PASS only when every one of the 5 dimensions (Coverage breadth, Technical depth, Philosophical framing, Source attribution, Image relevance) scores ≥ 3/5; any single dimension < 3 marks the audit INCOMPLETE and triggers a follow-on iteration within ar-4"
    - "Milestone-close commit covers `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` + `STATE-Agentic-RAG-v1.md` + `ROADMAP-Agentic-RAG-v1.md` (Phase ar-4 row marked Complete + milestone tally checkbox marked); commit uses forward-only `git add <explicit-files>` — no `-A`, no `--amend`, no `git reset` per memory `feedback_no_amend_in_concurrent_quicks.md` and `feedback_git_add_explicit_in_parallel_quicks.md`"
  artifacts:
    - path: "scripts/smoke_milestone.py"
      provides: "TEST-05 milestone smoke driver — runs `research()` against hardcoded Chinese query with telemetry sink configured; computes 5 pass conditions; emits JSON verdict; exits 0/1"
      contains: "QUERY constant, async main(), 5 pass-condition computations, JSON verdict emission, sys.exit gating"
    - path: ".planning/MILESTONE_Agentic-RAG-v1_AUDIT.md"
      provides: "TEST-06 manual audit doc — orchestrator-authored side-by-side comparison of agentic-RAG output vs Telegram ground truth; per-dimension table + final PASS/FAIL verdict; the milestone-close gate"
      contains: "Header (date, smoke command, telemetry path, dump-state path), agentic-RAG markdown excerpt, Telegram excerpts, 5-row dimension table, final verdict, signoff"
  key_links:
    - from: "scripts/smoke_milestone.py"
      to: "lib/research/orchestrator.py:research"
      via: "from omnigraph.research import research, from_env"
      pattern: "from omnigraph.research import research"
    - from: "scripts/smoke_milestone.py"
      to: "cfg.telemetry_jsonl (Wave 1 sink)"
      via: "dataclasses.replace(from_env(), telemetry_jsonl=Path('.scratch/smoke-telemetry-...jsonl'))"
      pattern: "telemetry_jsonl"
    - from: "scripts/smoke_milestone.py"
      to: "result.state.verified.confidence"
      via: "result.state.verified.confidence (VerifierOutput dataclass field)"
      pattern: "state.verified.confidence"
    - from: ".planning/MILESTONE_Agentic-RAG-v1_AUDIT.md"
      to: "docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json"
      via: "verbatim Telegram excerpts pasted into the audit doc"
      pattern: "session_20260506_105324_b7b9f4"
    - from: ".planning/MILESTONE_Agentic-RAG-v1_AUDIT.md"
      to: "agentic-RAG markdown saved to ~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md"
      via: "verbatim quote or `cat` reference in the audit doc"
      pattern: "synthesis_archive"
---

<objective>
Wave 2 closes the entire Agentic-RAG-v1 milestone. Two deliverables, both mostly observation + minimal driver code:

1. **TEST-05 milestone smoke** — A new driver script `scripts/smoke_milestone.py` runs the canonical Chinese-language deep-dive query (`"Hermes Harness 深度解析"`) against the live Hermes pipeline (Tavily + Brave + optionally Vertex Grounding), with Wave 1's telemetry JSONL sink configured. The driver consumes the JSONL file emitted during the run to verify condition (d) (no stage with `status="failed"`) and computes the other 4 conditions from the returned `ResearchResult`. Verdict is a JSON object on stdout; exit code 0 iff all 5 conditions pass.

2. **TEST-06 manual side-by-side audit** — After smoke passes, the orchestrator (acting as the human-stand-in audit reviewer) authors `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` comparing the agentic-RAG markdown against the Telegram ground-truth session at `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`. The audit scores 5 dimensions (Coverage breadth, Technical depth, Philosophical framing, Source attribution, Image relevance) on a 1-5 scale; PASS verdict requires ≥ 3 on EACH. User reviews the audit doc before milestone is declared closed.

This plan does NOT touch Wave 1 deliverables (`lib/research/telemetry.py`, `lib/research/orchestrator.py`, `lib/research/__main__.py`, the new tests). It does NOT introduce new env vars. It MAY conditionally touch `lib/research/stages/synthesizer.py` if and only if condition (a) (≥3 images) or (e) (Chinese language) fails on first run — ROADMAP § Cross-phase touches explicitly blesses ORCH-05 (Synthesizer prompt) iteration in ar-4 to satisfy smoke conditions.

**Failure handling within Wave 2:** if any of the 5 smoke conditions or any of the 5 audit dimensions fails on first run, ar-4 is allowed to iterate inside the phase. Diagnose → minimal surgical patch → re-run. Max 3 smoke iterations + 1 audit re-run before user escalation. Milestone close is gated on simultaneous smoke pass + audit PASS.

Output:

- One new file: `scripts/smoke_milestone.py` (~80-120 LOC).
- One new file: `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (authored DURING the audit run, NOT during planning execution; not a code artifact).
- Conditional touch: `lib/research/stages/synthesizer.py` (only if smoke fails condition (a) or (e); minimal prompt-only diff).
- STATE-Agentic-RAG-v1.md + ROADMAP-Agentic-RAG-v1.md updated to mark ar-4 complete and milestone CLOSED.
- Forward-only commit chain culminating in milestone-close commit.

After Wave 2 lands, all 41 REQs of Agentic-RAG-v1 are delivered, both phase-close gates have fired (TEST-05 pass + TEST-06 PASS), and the milestone is closed.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-CONTEXT.md
@.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-01-telemetry-dump-state-PLAN.md
@.planning/REQUIREMENTS-Agentic-RAG-v1.md
@.planning/ROADMAP-Agentic-RAG-v1.md
@.planning/PROJECT-Agentic-RAG-v1.md
@.planning/STATE-Agentic-RAG-v1.md
@docs/design/agentic_rag_internal_api.md
@docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json
@lib/research/orchestrator.py
@lib/research/__main__.py
@lib/research/telemetry.py
@lib/research/types.py
@lib/research/config.py
@lib/research/stages/synthesizer.py

<interfaces>
**`scripts/smoke_milestone.py` driver — invocation contract:**

```bash
# Run on Hermes target (orchestrator SSH per memory hermes_ssh.md):
python scripts/smoke_milestone.py
# expected:
#  - exit 0 (iff all 5 conditions pass)
#  - JSON verdict on stdout with 10 fields (5 measurements + 5 _pass booleans)
#  - .scratch/smoke-telemetry-<unix-ts>.jsonl created
#  - markdown saved to ~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md
```

No positional args, no flags. Hardcoded `QUERY = "Hermes Harness 深度解析"` constant.

**5 TEST-05 pass conditions (verbatim from ar-4-CONTEXT.md § TEST-05):**

| # | Condition | Verification |
|---|---|---|
| (a) | Markdown contains ≥ 3 inline `![desc](http://localhost:8765/...)` images | `len(re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", result.markdown)) >= 3` |
| (b) | `state.verified.confidence >= 60` | Read `result.state.verified.confidence` (VerifierOutput field; float) |
| (c) | Total wall time ≤ 240 s (calibrated 2026-05-24 from pre-empirical 120 s) | `time.time() - t0 <= 240.0` measured around `await research(...)` |
| (d) | No stage with `status="failed"` in JSONL telemetry | Parse `<telemetry_jsonl>` line-by-line; collect any `event_type==stage_end` event with `status==failed`; assert empty |
| (e) | Answer language is Chinese | Strip inline-image markdown + bare URLs, count CJK chars (`一-鿿`) over total non-whitespace, assert ratio `>= 0.5` |

**5 TEST-06 audit dimensions (verbatim from ar-4-CONTEXT.md § TEST-06; each 1-5; ≥ 3 required on each):**

| # | Dimension | "≥ 3" rubric |
|---|---|---|
| 1 | Coverage breadth | The agentic-RAG output mentions at least 60% of the distinct topics (architecture pieces, design choices, examples) the Telegram answer mentions |
| 2 | Technical depth | For at least 3 topics, the agentic-RAG answer goes beyond surface-level — names internal modules, cites specific files / classes / data shapes, or describes interaction logic |
| 3 | Philosophical framing | The answer captures the "why" behind Hermes Harness's design choices, not just the "what" — at least one paragraph or section discusses motivation or trade-offs |
| 4 | Source attribution | Inline citations or a sources section maps claims to KG chunks (kg_chunk URIs) and/or external URLs (Tavily/Brave/grounding) — readers can verify ≥ 50% of factual claims |
| 5 | Image relevance | The ≥ 3 embedded images are anchored to captions describing the system being explained — not generic placeholder images. At least 2 of 3 images add visible information to the answer |

**Verdict format:**

The smoke driver emits a JSON verdict with exactly these 10 fields:

```json
{
  "a_image_count": <int>,
  "a_pass": <bool>,
  "b_confidence": <float>,
  "b_pass": <bool>,
  "c_elapsed_s": <float>,
  "c_pass": <bool>,
  "d_failed_stages": [<str>...],
  "d_pass": <bool>,
  "e_cjk_ratio": <float>,
  "e_pass": <bool>
}
```

Exit code = 0 iff `all(v for k, v in verdict.items() if k.endswith("_pass"))`; else 1.

**Audit doc structure (`.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`):**

```markdown
# Agentic-RAG-v1 Milestone Audit (TEST-06)

**Date**: <YYYY-MM-DD HH:MM ADT>
**Smoke command**: `python scripts/smoke_milestone.py` (run on Hermes)
**Telemetry path**: `.scratch/smoke-telemetry-<ts>.jsonl`
**Dump-state path**: `<optional, if --dump-state was also captured for cross-reference>`
**Markdown archive**: `~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md`

## Smoke verdict (TEST-05)

```json
<paste full JSON verdict>
```

All 5 conditions pass: ✓

## Agentic-RAG output (verbatim or `cat` reference)

```markdown
<paste markdown OR: `cat ~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md`>
```

## Telegram ground-truth excerpts

Source: `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`

<paste 3-5 representative excerpts from the Telegram session — the topics, claims, and framing that comprise the "deep-dive" yardstick>

## Per-dimension scoring

| # | Dimension | Score (1-5) | Justification (2-4 sentences) |
|---|---|---|---|
| 1 | Coverage breadth | <int> | <narrative comparing topic coverage of agentic-RAG vs Telegram> |
| 2 | Technical depth | <int> | <narrative on internal-module / file / class / data-shape naming> |
| 3 | Philosophical framing | <int> | <narrative on whether the "why" is captured, not just "what"> |
| 4 | Source attribution | <int> | <narrative on citation quality and verifiability> |
| 5 | Image relevance | <int> | <narrative on whether the ≥3 images add visible information> |

## Final verdict

**PASS** (all 5 dimensions ≥ 3) — milestone Agentic-RAG-v1 closed.

OR

**INCOMPLETE** — dimension(s) <list> scored below 3; remediation: <specific deficits drive a follow-on iteration to Synthesizer/Reasoner prompts>.

## Operator signoff

- Date: <YYYY-MM-DD>
- Agent identifier: <Claude Code session id or model+timestamp>
- User review: <pending / approved on YYYY-MM-DD>

```

**Layer 2b live-key requirement (the milestone smoke runs on Hermes, NOT local-dev workstation):**

The local-dev workstation cannot run TEST-05 because:
1. The local KG has the 3072/768 embedding-dim mismatch (pre-existing v1.0.y operator-side issue) → Retriever returns `status="failed"` → condition (d) auto-fails.
2. Corp Cisco Umbrella proxy blocks Tavily + Brave egress → WebBaseline + Verifier external citation paths fail.
3. `BASE_IMAGE_DIR` and the local image HTTP server (port 8765) populated with real ingested article images live only on Hermes.
4. Wallclock ≤ 240 s requires real network concurrency from Hermes's egress, not the corp-proxy-routed dev box.

Required env vars on the Hermes target's `~/.hermes/.env` BEFORE smoke can run:
- `TAVILY_API_KEY` — primary web-search path (mandatory for condition d non-failure)
- `BRAVE_SEARCH_API_KEY` — fallback web-search path (mandatory)
- `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` + Vertex creds (`GOOGLE_APPLICATION_CREDENTIALS` SA JSON, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=global`) — required iff smoke is to exercise the Grounding path (CONFIG-03 Wave-3 auto-detect from ar-3 wires `cfg.google_search_grounding = vertex_gemini_grounding` when this provider is selected). If LLM provider is `deepseek`, Vertex creds are optional and Grounding tool is unavailable.
- `OMNIGRAPH_RESEARCH_TELEMETRY_JSONL` — NOT set (the smoke driver overrides this via `dataclasses.replace(cfg, telemetry_jsonl=...)` to a `.scratch/` path of its choosing; setting the env var also is harmless but redundant).
- Local image HTTP server running on port 8765 (Hermes systemd / cron-managed) so that the inline image URLs in the synthesizer output resolve when a human reviewer opens the markdown.

**Smoke driver source skeleton (verbatim from ar-4-CONTEXT.md § TEST-05):**

```python
# scripts/smoke_milestone.py
import asyncio, dataclasses, json, re, sys, time
from pathlib import Path
from omnigraph.research import research, from_env

QUERY = "Hermes Harness 深度解析"

async def main():
    telemetry_path = Path(".scratch") / f"smoke-telemetry-{int(time.time())}.jsonl"
    telemetry_path.parent.mkdir(exist_ok=True)
    cfg = dataclasses.replace(from_env(), telemetry_jsonl=telemetry_path)
    t0 = time.time()
    result = await research(QUERY, cfg)
    elapsed = time.time() - t0

    # condition (a) — inline image count
    image_count = len(re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", result.markdown))
    # condition (b) — verifier confidence
    confidence = result.state.verified.confidence if result.state.verified else 0.0
    # condition (c) — wall time (already measured)
    # condition (d) — no stage_end with status="failed" in telemetry
    failed_stages = []
    for line in telemetry_path.read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("event_type") == "stage_end" and ev.get("status") == "failed":
            failed_stages.append(ev["stage"])
    # condition (e) — Chinese-language ratio
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)|https?://\S+", "", result.markdown)
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    non_ws = sum(1 for c in text if not c.isspace())
    cjk_ratio = cjk / max(non_ws, 1)

    verdict = {
        "a_image_count": image_count, "a_pass": image_count >= 3,
        "b_confidence": confidence, "b_pass": confidence >= 60.0,
        "c_elapsed_s": elapsed, "c_pass": elapsed <= 240.0,
        "d_failed_stages": failed_stages, "d_pass": len(failed_stages) == 0,
        "e_cjk_ratio": cjk_ratio, "e_pass": cjk_ratio >= 0.5,
    }
    all_pass = all(v for k, v in verdict.items() if k.endswith("_pass"))
    print(json.dumps(verdict, indent=2, ensure_ascii=False))
    sys.exit(0 if all_pass else 1)

if __name__ == "__main__":
    asyncio.run(main())
```

The driver also saves the markdown for audit: extend the body with one `Path.write_text` after the verdict computation, BEFORE `sys.exit`:

```python
archive_dir = Path("~/.hermes/omonigraph-vault/synthesis_archive").expanduser()
archive_dir.mkdir(parents=True, exist_ok=True)
archive_path = archive_dir / f"{int(time.time())}_hermes-harness.md"
archive_path.write_text(result.markdown, encoding="utf-8")
```

This is the ONE place a `~/.hermes` literal is acceptable in Wave 2 code: `scripts/smoke_milestone.py` lives OUTSIDE `lib/research/` and is NOT subject to CONTRACT-02 (which applies to library code only).

**Cross-references to Wave 1 (ar-4-01) artifacts the driver depends on:**

- `lib.research.telemetry.write_event` / `make_event` — invoked transitively by `research()` once Wave 1 lands; the driver does NOT import telemetry.py directly.
- `lib.research.orchestrator.research` — Wave 1 refactored this to share the emit sequence with `research_stream()`; either form works for the driver (the driver uses the blocking entrypoint).
- `cfg.telemetry_jsonl` — Wave 1 honors this slot; the driver overrides via `dataclasses.replace`.

If Wave 1 has not landed at smoke time, the driver fails at the JSONL parse step (file empty / non-existent). This is the expected dependency-chain ordering: ar-4-01 must be complete and committed before ar-4-02 smoke can be meaningful.

**Hermes SSH invocation pattern (orchestrator runs SSH directly, never asks user):**

```bash
# Per memory hermes_ssh.md, SSH details are loaded into every session for this project.
# Orchestrator runs the smoke directly via the Bash tool — does NOT outsource SSH to user (principle #5).
ssh hermes "cd ~/OmniGraph-Vault && \
  source venv/bin/activate && \
  python scripts/smoke_milestone.py"
```

The orchestrator captures stdout (the JSON verdict), the telemetry path (echoed in the verdict via the Path.name in the smoke driver — see Implementation step 1), the markdown archive path, and the exit code.

**Audit-doc reviewer protocol (TEST-06):**

The audit is performed by the orchestrator (Claude Code session) acting as the human-stand-in agent. "Manual" here means "not automated in pytest". The orchestrator:

1. Reads the agentic-RAG markdown at the archive path returned by the smoke driver.
2. Reads the Telegram session JSON at `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json` (259 KB, confirmed exists per ar-4-CONTEXT.md § TEST-06).
3. Compares topic-by-topic, scoring the 5 dimensions per the rubric.
4. Authors `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` with verbatim excerpts + per-dimension narrative + final verdict.
5. Submits the audit doc for user review BEFORE marking milestone closed.

User holds the final say on the audit verdict. If user disagrees with any dimension score, the orchestrator iterates: adjusts narrative, lowers/raises score, possibly triggers a smoke + prompt-iteration sub-cycle if a score < 3 emerges.
</interfaces>
</context>

<files>

| Path | Status | Notes |
|---|---|---|
| `scripts/smoke_milestone.py` | **NEW** | TEST-05 milestone smoke driver — async main, 5 condition computations, JSON verdict, exit gating, markdown archive write |
| `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` | **NEW** (authored DURING audit run, not during PLAN execution scaffolding) | TEST-06 audit doc — header + verbatim excerpts + per-dimension table + final verdict + signoff |
| `lib/research/stages/synthesizer.py` | **CONDITIONAL modify** | Only if smoke condition (a) ≥3 images OR (e) Chinese language fails on first run — prompt-only diff per ROADMAP § Cross-phase touches ORCH-05 blessing; subject to CONTRACT-01 + CONTRACT-02 |
| `.planning/STATE-Agentic-RAG-v1.md` | **modify** (status update only) | Mark ar-4 complete + milestone closed |
| `.planning/ROADMAP-Agentic-RAG-v1.md` | **modify** (status update only) | Mark Phase ar-4 row Complete in Phase Status table; mark milestone tally checkbox |

</files>

<tasks>

<task type="auto">
  <name>Task 1: Author scripts/smoke_milestone.py (TEST-05 driver — 5 conditions, JSON verdict, archive write)</name>
  <read_first>
    - .planning/phases/ar-4-telemetry-streaming-smoke/ar-4-CONTEXT.md § "TEST-05: Milestone smoke (Wave 2)" — verbatim driver skeleton + 5 pass conditions
    - .planning/phases/ar-4-telemetry-streaming-smoke/ar-4-01-telemetry-dump-state-PLAN.md — Wave 1 telemetry sink contract; confirm `cfg.telemetry_jsonl` is honored by `research()` and emits `stage_end` events with `status` field
    - lib/research/telemetry.py (Wave 1) — `make_event` + `write_event` shape; confirm `event_type=="stage_end"` and `status` field present in payload
    - lib/research/orchestrator.py (Wave 1 form) — `research()` consumes `research_stream()` internally OR shares emit sequence; either way `cfg.telemetry_jsonl` writes JSONL
    - lib/research/types.py — `ResearchResult`, `ResearchState`, `VerifierOutput.confidence` (float)
    - lib/research/config.py — `from_env()` returns a fully-wired `ResearchConfig` from `~/.hermes/.env`
    - .planning/PROJECT-Agentic-RAG-v1.md — milestone charter (image-server-on-port-8765 invariant)
  </read_first>
  <files>scripts/smoke_milestone.py</files>
  <behavior>
    `scripts/smoke_milestone.py` MUST satisfy after this task:

    - Single file, ~80-120 LOC; no positional args; no CLI flags.
    - `QUERY = "Hermes Harness 深度解析"` defined as a module-level constant (NOT taken from argv).
    - `async def main()` body invokes `research(QUERY, cfg)` exactly once where `cfg` is `dataclasses.replace(from_env(), telemetry_jsonl=Path('.scratch') / f'smoke-telemetry-{int(time.time())}.jsonl')`.
    - The 5 condition computations occur in order (a → e), each producing two fields in the verdict dict (`<letter>_<measurement>` + `<letter>_pass`).
    - Verdict is `print(json.dumps(verdict, indent=2, ensure_ascii=False))` — pretty-printed, Chinese-safe.
    - Exit code: `sys.exit(0 if all_pass else 1)`.
    - Saves markdown to `~/.hermes/omonigraph-vault/synthesis_archive/<unix-ts>_hermes-harness.md` (creates dir with `parents=True, exist_ok=True`); the archive path is printed to stderr (NOT stdout — keeps stdout JSON-clean).
    - The telemetry path is also printed to stderr (so orchestrator SSH capture sees both paths even when stdout is JSON-only).
    - Top-of-file comments document the 5-condition pre-flight checklist (lines 1-15 approx):
      1. `~/.hermes/.env` populated with `TAVILY_API_KEY` + `BRAVE_SEARCH_API_KEY`
      2. Local image HTTP server running on port 8765 (`python -m http.server 8765 --directory ~/.hermes/omonigraph-vault/images`)
      3. `lightrag_storage/` populated with relevant articles (Hermes-side ingestion is fresh)
      4. (Optional) Vertex creds for Grounding (`OMNIGRAPH_LLM_PROVIDER=vertex_gemini` + SA JSON)
      5. `.scratch/` directory writable (driver creates it with `parents=True`)
    - File MUST NOT import from `lib.research.tools.web_search` directly; goes through `from_env()` only.
    - File IS allowed to use `~/.hermes/omonigraph-vault` literal — `scripts/` is OUTSIDE `lib/research/` and NOT subject to CONTRACT-02.
  </behavior>
  <action>
    1. Create `scripts/smoke_milestone.py`. Top-of-file structure:
       ```python
       """TEST-05 milestone smoke driver for Agentic-RAG-v1 close.

       Pre-flight (operator must satisfy on Hermes target before running):
         1. ~/.hermes/.env has TAVILY_API_KEY + BRAVE_SEARCH_API_KEY
         2. Local image HTTP server running on port 8765 (serves
            ~/.hermes/omonigraph-vault/images/)
         3. lightrag_storage/ populated with the relevant ingested articles
            (run a fresh ingest if KG has been re-deployed)
         4. (Optional) For Grounding path: OMNIGRAPH_LLM_PROVIDER=vertex_gemini
            + GOOGLE_APPLICATION_CREDENTIALS pointing to SA JSON
         5. .scratch/ in CWD must be writable (driver creates it)

       Usage: python scripts/smoke_milestone.py
       Exit code 0 iff all 5 TEST-05 conditions pass; else 1.
       Verdict (JSON) goes to stdout; telemetry + markdown archive paths to stderr.
       """
       import asyncio
       import dataclasses
       import json
       import re
       import sys
       import time
       from pathlib import Path

       from omnigraph.research import from_env, research

       QUERY = "Hermes Harness 深度解析"
       ```

    2. Implement `async def main()` per the ar-4-CONTEXT skeleton. Augment with the markdown-archive write + stderr path echoes:
       ```python
       async def main() -> int:
           telemetry_path = Path(".scratch") / f"smoke-telemetry-{int(time.time())}.jsonl"
           telemetry_path.parent.mkdir(parents=True, exist_ok=True)
           cfg = dataclasses.replace(from_env(), telemetry_jsonl=telemetry_path)

           t0 = time.time()
           result = await research(QUERY, cfg)
           elapsed = time.time() - t0

           # condition (a) — inline image count
           image_count = len(
               re.findall(r"!\[[^\]]*\]\(http://localhost:8765/", result.markdown)
           )
           # condition (b) — verifier confidence
           confidence = (
               result.state.verified.confidence
               if result.state.verified is not None
               else 0.0
           )
           # condition (c) — wall time (already measured)
           # condition (d) — no stage_end with status="failed" in telemetry
           failed_stages = []
           if telemetry_path.exists():
               for line in telemetry_path.read_text(encoding="utf-8").splitlines():
                   try:
                       ev = json.loads(line)
                   except json.JSONDecodeError:
                       continue
                   if (
                       ev.get("event_type") == "stage_end"
                       and ev.get("status") == "failed"
                   ):
                       failed_stages.append(ev.get("stage", "<unknown>"))
           # condition (e) — Chinese-language ratio
           text = re.sub(r"!\[[^\]]*\]\([^)]+\)|https?://\S+", "", result.markdown)
           cjk = sum(1 for c in text if "一" <= c <= "鿿")
           non_ws = sum(1 for c in text if not c.isspace())
           cjk_ratio = cjk / max(non_ws, 1)

           verdict = {
               "a_image_count": image_count,
               "a_pass": image_count >= 3,
               "b_confidence": confidence,
               "b_pass": confidence >= 60.0,
               "c_elapsed_s": elapsed,
               "c_pass": elapsed <= 240.0,
               "d_failed_stages": failed_stages,
               "d_pass": len(failed_stages) == 0,
               "e_cjk_ratio": cjk_ratio,
               "e_pass": cjk_ratio >= 0.5,
           }
           all_pass = all(v for k, v in verdict.items() if k.endswith("_pass"))

           # Save markdown for audit
           archive_dir = Path("~/.hermes/omonigraph-vault/synthesis_archive").expanduser()
           archive_dir.mkdir(parents=True, exist_ok=True)
           archive_path = archive_dir / f"{int(time.time())}_hermes-harness.md"
           archive_path.write_text(result.markdown, encoding="utf-8")

           # Path echoes to stderr (keep stdout JSON-clean)
           print(f"telemetry_path: {telemetry_path}", file=sys.stderr)
           print(f"archive_path: {archive_path}", file=sys.stderr)

           # Verdict to stdout
           print(json.dumps(verdict, indent=2, ensure_ascii=False))
           return 0 if all_pass else 1


       if __name__ == "__main__":
           sys.exit(asyncio.run(main()))
       ```

    3. Verify importability + signature without invoking the live pipeline (which requires Hermes-only Tavily/Brave keys):
       ```bash
       cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
       venv/Scripts/python.exe -c "
       import importlib.util, pathlib
       spec = importlib.util.spec_from_file_location('smoke_milestone', 'scripts/smoke_milestone.py')
       mod = importlib.util.module_from_spec(spec)
       spec.loader.exec_module(mod)
       assert mod.QUERY == 'Hermes Harness 深度解析'
       import inspect
       assert inspect.iscoroutinefunction(mod.main)
       print('smoke_milestone.py importable + main is coroutine + QUERY constant correct')
       "
       ```

    4. CONTRACT-01 grep on `scripts/`: not subject to the contract (contract applies to `lib/research/` only). Document this in SUMMARY.md.

    5. Commit with explicit `git add scripts/smoke_milestone.py` (NEVER `-A` per memory `feedback_git_add_explicit_in_parallel_quicks.md`):
       ```bash
       git add scripts/smoke_milestone.py
       git commit -m "feat(ar-4-02): add scripts/smoke_milestone.py — TEST-05 milestone smoke driver"
       ```
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; venv/Scripts/python.exe -c "import importlib.util, inspect; spec = importlib.util.spec_from_file_location('smoke_milestone', 'scripts/smoke_milestone.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); assert mod.QUERY == 'Hermes Harness 深度解析'; assert inspect.iscoroutinefunction(mod.main); print('OK')"</automated>
  </verify>
  <acceptance_criteria>
    - `scripts/smoke_milestone.py` exists, ~80-120 LOC.
    - Module-level `QUERY` constant equals `"Hermes Harness 深度解析"`.
    - `main` is a coroutine (`inspect.iscoroutinefunction(main) is True`).
    - Imports `research, from_env` from `omnigraph.research` (Wave 1 surface).
    - Body uses `dataclasses.replace(from_env(), telemetry_jsonl=...)` to override the sink slot.
    - All 5 condition computations present (regex for a, attribute access for b, time delta for c, JSONL parse for d, CJK ratio for e).
    - Verdict dict has exactly the 10 fields specified in `<interfaces>`.
    - Verdict pretty-printed via `json.dumps(verdict, indent=2, ensure_ascii=False)` (Chinese-safe).
    - Markdown archive path printed to stderr; telemetry path printed to stderr; verdict printed to stdout.
    - Exit code: 0 iff all `*_pass` truthy; else 1.
    - Forward-only commit with explicit `git add scripts/smoke_milestone.py`.
    - No imports from `lib.research.tools.web_search` (consumer goes through `from_env()`).
  </acceptance_criteria>
  <done>scripts/smoke_milestone.py committed; importable; main is coroutine; verdict structure matches spec.</done>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 2: Run TEST-05 milestone smoke on Hermes target (orchestrator-driven SSH; remediation sub-cycle if any condition fails)</name>
  <what-built>
    Wave 1 (`lib/research/telemetry.py`, `research_stream()` body, `--dump-state` flag) + Task 1's `scripts/smoke_milestone.py` driver. The driver runs the canonical Chinese-language deep-dive query against the live Hermes pipeline and emits a JSON verdict.
  </what-built>
  <how-to-verify>
    The orchestrator MUST run this verification — NOT the user. Per principle #5 (do not outsource mechanical SSH work to user) and project memory `hermes_ssh.md` (SSH connection details auto-loaded into the session), the orchestrator runs SSH directly via the Bash tool.

    1. Confirm Hermes pre-flight (orchestrator runs each remotely; do NOT ask user to copy-paste):
       ```bash
       # Per memory hermes_ssh.md, the SSH alias `hermes` resolves automatically.
       ssh hermes "test -f ~/.hermes/.env && grep -E '^TAVILY_API_KEY=|^BRAVE_SEARCH_API_KEY=' ~/.hermes/.env | cut -d= -f1"
       # expected: both keys present (values not echoed for security)
       ```
       If a key is missing, EITHER the orchestrator writes a Hermes operator prompt asking the user to inject the key (NEVER paste literal secret in the prompt — placeholder `<retrieve from password manager>`) OR the smoke is deferred. Per memory `feedback_no_literal_secrets_in_prompts.md`, NEVER include the actual key value in the prompt.

    2. Confirm image server + lightrag storage on Hermes:
       ```bash
       ssh hermes "curl -sf http://localhost:8765/ -o /dev/null && echo 'image_server_ok' || echo 'image_server_DOWN'"
       ssh hermes "ls ~/.hermes/omonigraph-vault/lightrag_storage/ | head -5"
       ```
       If image server is down: `ssh hermes "cd ~/.hermes/omonigraph-vault && nohup python -m http.server 8765 --directory images >/dev/null 2>&1 &"`

    3. Reconcile git state on Hermes BEFORE running smoke (per CLAUDE.md "Remote Hermes Deployment" guidance — remote may be ahead of GitHub):
       ```bash
       ssh hermes "cd ~/OmniGraph-Vault && git status -sb && git log --oneline -5"
       # If remote ahead: ssh hermes "cd ~/OmniGraph-Vault && git pull --ff-only"
       # If local ahead: orchestrator pushes to GitHub locally, then `ssh hermes "cd ~/OmniGraph-Vault && git pull --ff-only"`
       ```

    4. Run the smoke:
       ```bash
       ssh hermes "cd ~/OmniGraph-Vault && \
         source venv/bin/activate && \
         python scripts/smoke_milestone.py 2>/tmp/smoke-stderr.log; \
         echo '--- STDERR ---'; cat /tmp/smoke-stderr.log"
       ```
       Capture stdout (JSON verdict), stderr (telemetry_path + archive_path lines), and exit code.

    5. Parse verdict. Three outcomes:

       **Outcome A — all 5 conditions pass:** verdict shows every `*_pass: true`, exit code 0. Proceed to Task 3 (audit).

       **Outcome B — one or more conditions fail:** enter remediation sub-cycle. Diagnose:
       - **(a) `image_count < 3`**: Synthesizer prompt may not be selecting/embedding enough caption-anchored images, OR Reasoner image-selection (ar-2-01) didn't analyze ≥3 images. Inspect `result.state.reasoned.analyzed_images` count via dump-state (Wave 1's `--dump-state .scratch/dump.jsonl` flag). If `analyzed_images >= 3` but markdown has < 3 inline images: Synthesizer prompt iteration in `lib/research/stages/synthesizer.py` (ROADMAP § Cross-phase touches ORCH-05 blessing). If `analyzed_images < 3`: Reasoner prompt iteration in `lib/research/stages/reasoner.py` (also ROADMAP-blessed cross-phase touch).
       - **(b) `confidence < 60.0`**: Verifier external citations are weak. Inspect `result.state.verified.external_citations` count. If 0 citations, web tools may have `status="skipped"` (no API key in `~/.hermes/.env`). Re-run with TAVILY+BRAVE keys present. If citations exist but confidence still low: Verifier prompt iteration may be needed (`lib/research/stages/verifier.py`) — ROADMAP-blessed cross-phase touch.
       - **(c) `elapsed > 240.0 s`**: pipeline too slow. Likely culprits: Reasoner cap (default 5) or Verifier cap (default 3) too high; serialized image-vision calls; Tavily/Brave latency. Mitigation: lower caps via env (`OMNIGRAPH_RESEARCH_MAX_ITER_REASONER=3`, `..._VERIFIER=2`), OR investigate Vision parallelism inside Reasoner.
       - **(d) `failed_stages` non-empty**: a stage's outer try/except surfaced a failure. Inspect telemetry JSONL `reason` field for that stage. Common causes: Retriever embedding-dim mismatch (Hermes KG re-ingest needed); Verifier grounding tool credential failure (drop with `--no-grounding`); WebBaseline Tavily timeout (raise timeout or accept skipped status).
       - **(e) `cjk_ratio < 0.5`**: model picked English mid-stream. Synthesizer prompt iteration (ROADMAP-blessed) — strengthen the "respond in Chinese matching the query language" instruction.

       For each diagnosis: minimal surgical patch (prefer Synthesizer prompt > Reasoner prompt > Verifier prompt > deeper surgery), commit with explicit `git add <file>`, push, sync to Hermes, re-run smoke. Max 3 iterations. Document each iteration in SUMMARY.md.

       **Outcome C — pipeline crashes (exception during `research()`)**: this is NOT a smoke failure — this is a Wave 1 regression. Halt; do not proceed to audit. File a separate ar-4-01 bug; do NOT patch under Wave 2.

    6. Once Outcome A is reached, save the verdict + paths + exit code to `.scratch/ar-4-02-smoke-result.txt` for the audit doc to reference.
  </how-to-verify>
  <resume-signal>
    "smoke passed" — orchestrator-confirmed all 5 conditions pass; proceed to Task 3 audit.
    "smoke iteration {N} starting" — orchestrator about to apply patch and re-run; user may pause here to review the patch.
    "smoke failed N times" — exhausted 3 iterations; user escalation required.
  </resume-signal>
</task>

<task type="checkpoint:human-action" gate="blocking">
  <name>Task 3: Author .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md (TEST-06 manual side-by-side audit; orchestrator-as-reviewer)</name>
  <what-built>
    The agentic-RAG markdown output from Task 2 (saved at `~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md`) and the Telegram ground-truth session JSON at `docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json`. TEST-06 is the milestone-close gate; the orchestrator performs the audit acting as the human-stand-in reviewer.
  </what-built>
  <how-to-verify>
    The orchestrator authors `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` per the structure in `<interfaces>` § "Audit doc structure". User reviews the doc and signs off (or requests adjustments).

    1. Fetch the agentic-RAG markdown from Hermes:
       ```bash
       ssh hermes "cat ~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md" > .scratch/audit-agentic-rag-output.md
       # OR scp:
       scp hermes:~/.hermes/omonigraph-vault/synthesis_archive/<ts>_hermes-harness.md .scratch/audit-agentic-rag-output.md
       ```

    2. Read the Telegram session JSON locally:
       ```bash
       venv/Scripts/python.exe -c "
       import json
       with open('docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json', 'r', encoding='utf-8') as f:
           data = json.load(f)
       # Print top-level structure and first ~3000 chars of the answer to scan for excerpts
       print(json.dumps({k: type(v).__name__ for k, v in data.items()}, indent=2))
       "
       ```
       Identify the field containing the answer text (likely `answer`, `response`, or nested under `messages`). Extract 3-5 representative excerpts covering the topics, claims, and framing the deep-dive answer covers.

    3. Score each of the 5 dimensions per the rubric in `<interfaces>` § "5 TEST-06 audit dimensions":

       **Dimension 1 — Coverage breadth (target: ≥ 60% of distinct topics from Telegram answer)**: enumerate the distinct topics in the Telegram answer (architecture pieces, design choices, examples). Tally how many appear in the agentic-RAG output. Score 5 if ≥ 80%; 4 if 70-79%; 3 if 60-69%; 2 if 40-59%; 1 if < 40%.

       **Dimension 2 — Technical depth (target: ≥ 3 topics with internal-module-level depth)**: identify topics where the agentic-RAG output names internal modules / files / classes / data shapes (e.g., names `lib/research/orchestrator.py:research`, or describes the `ResearchState` dataclass shape, or explains how `Reasoner._LLMDecision` works). Score 5 if ≥ 5 such topics; 4 if 4; 3 if 3; 2 if 2; 1 if ≤ 1.

       **Dimension 3 — Philosophical framing (target: ≥ 1 paragraph on motivation or trade-offs)**: scan for paragraphs or sections discussing "why" choices were made — design rationale, trade-offs, alternatives considered. Score 5 if multiple substantial sections; 4 if one substantial section; 3 if one paragraph; 2 if scattered sentences; 1 if pure "what" with no "why".

       **Dimension 4 — Source attribution (target: ≥ 50% of factual claims verifiable via inline citations)**: enumerate factual claims in the agentic-RAG output. Tally how many have inline citations (kg_chunk URIs, external URLs from Tavily/Brave/grounding) or appear in a sources section. Score 5 if ≥ 80%; 4 if 65-79%; 3 if 50-64%; 2 if 30-49%; 1 if < 30%.

       **Dimension 5 — Image relevance (target: ≥ 2 of 3 images add visible information)**: inspect the inline images. Each image has alt text (caption) and a `localhost:8765/...` URL. Score by judging: does the alt-text caption describe the system being explained at that point in the answer? At least 2 of the ≥3 images should be substantive. Score 5 if all images are highly relevant; 4 if all but one; 3 if 2 of 3 (or 2 of N for N>3) are relevant; 2 if 1 of 3; 1 if 0 of 3.

    4. Author `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` per the structure in `<interfaces>`. The body MUST include:
       - Header (date in ADT timezone, smoke command verbatim, telemetry path absolute, dump-state path if Wave 1's `--dump-state` was also captured for cross-reference, markdown archive path absolute)
       - Smoke verdict JSON pasted verbatim from Task 2's `.scratch/ar-4-02-smoke-result.txt`
       - Agentic-RAG markdown excerpt (full or `cat` reference if too long; if pasting full, prefer fenced code block)
       - Telegram ground-truth excerpts (3-5 paragraphs verbatim; clearly labeled "Source: docs/queries/hermes_session_2026_05_06/session_20260506_105324_b7b9f4.json")
       - 5-row dimension table per `<interfaces>`
       - Final verdict line: bold **PASS** or **INCOMPLETE**
       - Operator signoff: date + agent identifier (Claude Code session model + timestamp); user review pending until user explicitly approves

    5. Three outcomes after authoring:

       **Outcome A — verdict PASS (every dimension ≥ 3):** proceed to Task 4 (milestone close).

       **Outcome B — verdict INCOMPLETE (any dimension < 3):** identify the deficit. Examples:
       - Dimension 1 score 2: agentic-RAG missed ≥ 40% of Telegram topics — Retriever may be returning insufficient KG chunks; Reasoner not asking enough sub-queries. Mitigation: raise Reasoner cap (`--max-iter-reasoner 7`) for next smoke run; OR Reasoner prompt iteration to explicitly enumerate sub-topics.
       - Dimension 3 score 2: pure "what" output. Mitigation: Synthesizer prompt iteration to require a "Design rationale" or "Trade-offs" section.
       - Dimension 4 score 2: weak attribution. Mitigation: Synthesizer prompt iteration to require inline citations after every factual claim; OR Verifier prompt iteration to ensure external citations are surfaced into final state.

       Apply minimal patch, re-run Task 2 smoke, re-run Task 3 audit. Max 1 audit re-run before user escalation.

       **Outcome C — disagree-with-self ambiguity (score is ≥ 3 but feels marginal):** flag the dimension in the narrative as "marginal pass — score 3 with caveats: ...". User reviews and may request a re-score.

    6. Submit the audit doc for user review. Wait for explicit "approved" / "looks good" / "milestone closed" signal before proceeding to Task 4. If user requests changes, iterate on the doc only (no code changes); Task 4 cannot run until user explicitly approves the audit verdict.
  </how-to-verify>
  <resume-signal>
    "audit approved" — user confirms the verdict; orchestrator proceeds to Task 4 milestone-close commit.
    "audit needs revision: <specific dimension>" — orchestrator re-scores or re-narrates that dimension only, NOT the full doc.
    "audit failed; remediate <prompt>" — orchestrator iterates the named prompt, re-runs Task 2 smoke, re-runs Task 3 audit (max once).
  </resume-signal>
</task>

<task type="auto">
  <name>Task 4: Milestone-close — update STATE-Agentic-RAG-v1.md + ROADMAP-Agentic-RAG-v1.md and commit forward-only</name>
  <read_first>
    - .planning/STATE-Agentic-RAG-v1.md (current — locate the ar-4 row + the "Position" / "Current Phase" header)
    - .planning/ROADMAP-Agentic-RAG-v1.md (current — locate the Phase Status table, ar-4 row, and the milestone tally section)
    - .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md (Task 3 output — the audit doc must be PASS)
    - .scratch/ar-4-02-smoke-result.txt (Task 2 output — verdict JSON for verbatim citation in commit message)
    - CLAUDE.md § Lessons Learned for memory pointers (`feedback_no_amend_in_concurrent_quicks.md`, `feedback_git_add_explicit_in_parallel_quicks.md`)
  </read_first>
  <files>.planning/STATE-Agentic-RAG-v1.md, .planning/ROADMAP-Agentic-RAG-v1.md</files>
  <behavior>
    After this task:
    - `.planning/STATE-Agentic-RAG-v1.md` shows ar-4 phase complete + milestone closed (specific markings depend on the file's existing format — match it surgically; do NOT rewrite the whole file).
    - `.planning/ROADMAP-Agentic-RAG-v1.md` Phase Status table row for ar-4 changes from `0/?` / `Not started` to `2/2` / `Complete` with the closure-date + commit-hash citation; the milestone tally checkbox (if present) is marked.
    - Forward-only commit covers exactly: `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`, `.planning/STATE-Agentic-RAG-v1.md`, `.planning/ROADMAP-Agentic-RAG-v1.md` (and `lib/research/stages/synthesizer.py` IF it was conditionally modified during Task 2 remediation).
    - Commit message uses HEREDOC; explicit `git add` of each file by name; NO `-A`, NO `--amend`, NO `git reset` per memory `feedback_no_amend_in_concurrent_quicks.md`.
  </behavior>
  <action>
    1. Open `.planning/STATE-Agentic-RAG-v1.md`. Locate the ar-4 phase entry. Update fields to reflect closure (match the file's existing format; typical pattern from sibling milestone STATEs):
       - Phase status: `Not started` → `Complete`
       - Closure date: today's date (`2026-05-23` or whatever the actual run-date is)
       - Commit hash: leave a placeholder like `<commit hash will be added in this same commit>` — do NOT pre-populate; the milestone-close commit hash isn't known until after `git commit`.
       - Forward-only addendum (preferred over editing-in-place, per `feedback_git_add_explicit_in_parallel_quicks.md` audit pattern): append a note like "ar-4 closed YYYY-MM-DD via TEST-05 5/5 pass + TEST-06 PASS verdict; see .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md" to the bottom of the file.

    2. Open `.planning/ROADMAP-Agentic-RAG-v1.md`. Locate the Phase Status table. Update the ar-4 row:
       - `Plans` column: `0/?` → `2/2`
       - `Status` column: `Not started` → `Complete`
       - `Notes` column: `—` → `2026-05-23 — TEST-05 5/5 pass; TEST-06 PASS; commit <hash>; see .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (use today's actual date)

    3. Locate the milestone tally section (if the ROADMAP has a "Milestone closed" checkbox or a "Phase tally: 0/4 → ?/4" line). Update it to reflect 4/4 phases complete + milestone CLOSED.

    4. Stage explicitly (NEVER `-A` or `.`):
       ```bash
       git add .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md
       git add .planning/STATE-Agentic-RAG-v1.md
       git add .planning/ROADMAP-Agentic-RAG-v1.md
       # IF Task 2 conditionally modified Synthesizer:
       git add lib/research/stages/synthesizer.py
       # Verify only intended files staged:
       git status -sb
       ```
       Inspect `git status -sb` output. If any unintended file appears (e.g., a parallel `.scratch/` artifact, an unrelated edit), STOP — un-stage with `git reset HEAD <file>` (NOT `git reset --soft` or `--mixed` per memory) and re-inspect. Only proceed when staged files match the expected list exactly.

    5. Commit with HEREDOC message (NEVER `--amend`):
       ```bash
       git commit -m "$(cat <<'EOF'
       docs(agentic-rag-v1): milestone CLOSED — TEST-05 5/5 pass, TEST-06 PASS verdict, all 41 REQs delivered

       Wave 2 of ar-4 closes the Agentic-RAG-v1 milestone.

       TEST-05 milestone smoke (scripts/smoke_milestone.py on Hermes target):
         - Query: "Hermes Harness 深度解析"
         - Verdict: see .planning/MILESTONE_Agentic-RAG-v1_AUDIT.md § Smoke verdict
         - All 5 conditions pass: image_count >= 3, confidence >= 60.0,
           elapsed <= 240s, no failed stages, cjk_ratio >= 0.5

       TEST-06 manual audit (.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md):
         - Coverage breadth: <score>/5
         - Technical depth: <score>/5
         - Philosophical framing: <score>/5
         - Source attribution: <score>/5
         - Image relevance: <score>/5
         - Final verdict: PASS

       All 41 REQs of Agentic-RAG-v1 delivered across ar-1..ar-4.
       Phase Status: ar-1 ✓ ar-2 ✓ ar-3 ✓ ar-4 ✓ → milestone CLOSED.
       EOF
       )"
       ```
       Replace the `<score>` placeholders with actual scores from the audit doc before running. The orchestrator MUST author the actual commit message — do NOT submit with literal `<score>` placeholders.

    6. After commit succeeds, capture the commit hash:
       ```bash
       git log -1 --format='%H'
       ```

    7. **Post-commit forward-only correction** (per `feedback_git_add_explicit_in_parallel_quicks.md`): if the STATE / ROADMAP files referenced a `<commit hash will be added>` placeholder, the placeholder is now stale. Apply a follow-up tiny commit that backfills the hash — do NOT amend:
       ```bash
       # Edit STATE.md and ROADMAP.md to replace <commit hash> with the captured hash
       git add .planning/STATE-Agentic-RAG-v1.md .planning/ROADMAP-Agentic-RAG-v1.md
       git commit -m "docs(agentic-rag-v1): backfill milestone-close commit hash"
       ```
       This forward-only correction is the same pattern used in v1.0.x closure (memory `project_v1_0_x_closure_260516.md`). Two commits is correct; one amended commit is forbidden.

    8. Push:
       ```bash
       git push
       # If remote rejects (Hermes ahead), reconcile per CLAUDE.md "Remote Hermes Deployment":
       #   git pull --rebase
       #   git push
       ```

    9. Sync to Hermes (so the Hermes runtime sees the milestone-closed state):
       ```bash
       ssh hermes "cd ~/OmniGraph-Vault && git pull --ff-only"
       ```

    10. Verify the chain:
        ```bash
        git log --oneline -5
        # expected (approximately):
        #   <hash>  docs(agentic-rag-v1): backfill milestone-close commit hash
        #   <hash>  docs(agentic-rag-v1): milestone CLOSED — ...
        #   <hash>  feat(ar-4-02): add scripts/smoke_milestone.py — ...
        #   <hash>  <Wave 1 ar-4-01 commits — telemetry + dump-state>
        #   ...
        ```
  </action>
  <verify>
    <automated>cd c:/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; git log -1 --format='%s' | grep -q "milestone CLOSED" &amp;&amp; git status -sb | grep -E "^(M|A|D)" | head -1 | { read line; if [ -z "$line" ]; then echo "OK — clean working tree"; else echo "FAIL — unstaged changes after milestone-close commit"; exit 1; fi; }</automated>
  </verify>
  <acceptance_criteria>
    - `.planning/STATE-Agentic-RAG-v1.md` reflects ar-4 complete + milestone closed.
    - `.planning/ROADMAP-Agentic-RAG-v1.md` Phase Status table shows ar-4 as Complete with closure date + commit hash.
    - Milestone tally (if present in ROADMAP) shows 4/4 phases complete.
    - Forward-only commit chain: smoke driver commit (Task 1) → optional Synthesizer prompt-iteration commits (Task 2 remediation, if any) → milestone-close commit (this Task) → optional hash-backfill commit (this Task step 7, if needed).
    - Zero `git --amend` usage; zero `git reset --soft / --mixed / --hard` usage.
    - `git add` always explicit-by-name; never `-A` or `.`.
    - `git status -sb` is clean after the chain (no unstaged or untracked changes from this PLAN).
    - Push successful; Hermes synced via `git pull --ff-only`.
  </acceptance_criteria>
  <done>Milestone Agentic-RAG-v1 declared CLOSED in STATE + ROADMAP; commit chain forward-only; Hermes synced; ready for user review of `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`.</done>
</task>

</tasks>

<verification>
- All four tasks pass automated checks.
- `scripts/smoke_milestone.py` is importable; `main` is a coroutine; `QUERY` constant matches the canonical Chinese query.
- TEST-05 smoke run on Hermes target produced a verdict with all 5 `*_pass` fields true; exit code 0.
- `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` exists with all 6 required sections (header, smoke verdict, agentic-RAG excerpt, Telegram excerpts, dimension table, verdict + signoff); every dimension scored ≥ 3; final verdict line is **PASS**.
- `.planning/STATE-Agentic-RAG-v1.md` + `.planning/ROADMAP-Agentic-RAG-v1.md` reflect ar-4 complete + milestone CLOSED.
- Forward-only commit chain (Task 1 + optional Task 2 remediation + Task 4 close + optional Task 4 step 7 hash-backfill) — no `--amend`, no `git reset`.
- Pytest regression suite still ≥123 green (Wave 1 baseline + Wave 1 new tests; Wave 2 adds NO new pytest tests because `scripts/smoke_milestone.py` is an observability driver exempt from unit-test coverage by precedent — same exemption ar-3-03 Task 5's Layer 2a smoke received):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe -m pytest tests/unit/research/ -v
  # expected: ≥123 green; the 1 known flake (test_subprocess_smoke_with_max_iter_zero) tolerated
  ```
- skill_runner regression still green:
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  venv/Scripts/python.exe skill_runner.py skills/omnigraph_research \
    --test-file tests/skills/test_omnigraph_research.json
  # expected: exit 0
  ```
- CONTRACT-01 grep across `lib/research/` (Wave 2 must NOT introduce any new `omnigraph_search.*` import; if Synthesizer was conditionally modified, audit the diff):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  hits=$(grep -rE "from omnigraph_search" lib/research/ --include='*.py' \
    | grep -vE "from omnigraph_search\.query " \
    | grep -vE "from omnigraph_search\.query$" \
    | grep -vE "import omnigraph_search\.query" \
    || true) && \
  if [ -n "$hits" ]; then echo "CONTRACT-01 violation:"; echo "$hits"; exit 1; fi
  ```
  Expected: 0 violations.
- CONTRACT-02 grep across `lib/research/` (allow-listed exceptions: `config.py`, `README.md`):
  ```bash
  cd c:/Users/huxxha/Desktop/OmniGraph-Vault && \
  grep -rE "/.hermes|omonigraph-vault" lib/research/ --include='*.py' \
    | grep -vE "config\.py|README\.md|^Binary"
  ```
  Expected: 0 hits. NOTE: `scripts/smoke_milestone.py` legitimately uses `~/.hermes/omonigraph-vault/synthesis_archive` and is OUTSIDE `lib/research/` — NOT subject to CONTRACT-02.
- `bash scripts/check_contract.sh` exits 0.
- Hermes runtime synced: `ssh hermes "cd ~/OmniGraph-Vault && git log --oneline -1"` shows the milestone-close commit hash.
</verification>

<success_criteria>

- ROADMAP Phase ar-4 Success Criterion #1 (`research_stream()` body emits stage events; same emit sequence shared with `research()`): ✓ delivered by Wave 1 (ar-4-01).
- ROADMAP Phase ar-4 Success Criterion #2 (`cfg.telemetry_jsonl` honored — JSONL append on each stage event when sink set): ✓ delivered by Wave 1.
- ROADMAP Phase ar-4 Success Criterion #3 (`--dump-state <path>` CLI flag dumps `ResearchState` as JSONL; `_amain` ≤ 18 LOC): ✓ delivered by Wave 1.
- ROADMAP Phase ar-4 Success Criterion #4 (TEST-05 milestone smoke passes all 5 conditions): ✓ delivered by Task 2.
- ROADMAP Phase ar-4 Success Criterion #5 (TEST-06 manual audit verdict ≥ 3/5 on each of 5 dimensions, doc at `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md`): ✓ delivered by Task 3.
- REQ TEST-05 (Hermes Harness 深度解析 smoke; 5 pass conditions): ✓ delivered by Task 2.
- REQ TEST-06 (manual side-by-side audit; 5 dimensions; PASS verdict): ✓ delivered by Task 3.
- All 41 REQs of Agentic-RAG-v1 delivered across ar-1 (16 REQs), ar-2 (5 REQs), ar-3 (3 REQs), ar-4 (4 REQs total: LIB-08, CLI-02 in Wave 1; TEST-05, TEST-06 in Wave 2). Note: 41-REQ tally per ROADMAP § "Requirements distribution by phase".
- Pytest baseline ≥123 green; skill_runner regression green; CONTRACT-01 + CONTRACT-02 still clean.
- Forward-only commit discipline preserved across the entire chain (no `--amend`, no `git reset`, explicit `git add` by name throughout).
- Hermes runtime synced; milestone-close commit hash captured in STATE + ROADMAP.

After Wave 2 lands and user approves the audit doc, the **Agentic-RAG-v1 milestone is CLOSED**. No further ar-N phase exists; post-milestone work (HTTP-01..03 endpoints, telemetry retention/rotation, per-tool-call events, deeper Synthesizer prompt tuning, LightRAG 1.5+ spike) is out-of-scope per ar-4-CONTEXT.md § "Out of Scope".
</success_criteria>

<output>
After completion, create `.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-02-SUMMARY.md` documenting:

- Files created + LOC count: `scripts/smoke_milestone.py` (~80-120 LOC); `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (LOC count of the actual audit doc).
- Files modified: `.planning/STATE-Agentic-RAG-v1.md`, `.planning/ROADMAP-Agentic-RAG-v1.md` (with line-diff counts).
- Conditional file modified: `lib/research/stages/synthesizer.py` IF Task 2 remediation triggered prompt iteration — list each iteration with one-line rationale.
- TEST-05 smoke verdict: full JSON pasted (the verdict from the FINAL passing run; if iterations occurred, prior-iteration verdicts can be summarized as a table).
- TEST-05 smoke command + Hermes invocation form: verbatim.
- TEST-05 telemetry path + markdown archive path: absolute paths on the Hermes filesystem.
- TEST-06 audit per-dimension scores: 5-row table; final verdict; user-approval timestamp.
- Iteration count: how many smoke runs were needed; how many audit re-runs (if any); each iteration's diagnosis + patch + verdict-delta.
- Commit chain: ordered list of commit hashes + subjects (Task 1 smoke driver → optional Task 2 remediation commits → Task 4 milestone-close → optional Task 4 step 7 hash-backfill).
- Pytest regression: total count + green/flake summary; confirm no new test failures introduced by Wave 2.
- skill_runner regression: exit code; tests-run count.
- CONTRACT-01 + CONTRACT-02 grep results: 0 hits each.
- Hermes sync confirmation: `git log --oneline -1` output from Hermes.
- Milestone closure declaration: "Agentic-RAG-v1 CLOSED YYYY-MM-DD; all 41 REQs delivered; user approval YYYY-MM-DD."
- Any deviations from plan with one-line rationale.

The SUMMARY.md is the formal closure document for the milestone — link from it back to:

- `.planning/MILESTONE_Agentic-RAG-v1_AUDIT.md` (the human-readable audit verdict)
- `.planning/STATE-Agentic-RAG-v1.md` (final state snapshot)
- `.planning/ROADMAP-Agentic-RAG-v1.md` (final roadmap with all 4 phases ✓)
- The Wave 1 SUMMARY (`.planning/phases/ar-4-telemetry-streaming-smoke/ar-4-01-SUMMARY.md`)
- All four ar-N phase-close commits (cite hashes)
</output>

## Planner-flagged ambiguities

1. **Smoke-driver markdown archive path uses a `~/.hermes/omonigraph-vault/...` literal.** This is the ONLY `~/.hermes` literal in any Wave 2 code. CONTRACT-02 applies to `lib/research/` only (the contract grep explicitly scopes to `lib/research/`); `scripts/` is NOT subject. Default: keep the literal in `scripts/smoke_milestone.py` for ergonomics. Alternative: read from `OMNIGRAPH_BASE_DIR` env var. Cost-benefit: the literal is read once at smoke time on Hermes only; env-var indirection adds noise without operator benefit. Default chosen.

2. **TEST-06 audit performed by orchestrator vs. user.** ar-4-CONTEXT.md § "TEST-06" specifies "the orchestrator (Claude Code session). User reviews the audit doc before milestone is declared closed." This makes the orchestrator the audit AUTHOR and the user the audit APPROVER. Default: orchestrator authors with explicit checkpoint:human-action gating in Task 3; user signoff required before Task 4 fires. Alternative: user authors the entire audit. Default chosen — matches CONTEXT verbatim.

3. **Synthesizer / Reasoner prompt iteration in Task 2 remediation.** ROADMAP § "Cross-phase touches" explicitly blesses ORCH-05 (Synthesizer prompt) iteration in ar-4 to satisfy smoke conditions; ar-4-CONTEXT.md § "Output language matches query language (Axis 10)" reaffirms this for condition (e). Reasoner prompt iteration is bracket-blessed by extension (same line of reasoning). Default: prefer Synthesizer over Reasoner over Verifier when applying remediation patches (least-blast-radius ordering). Document each iteration in SUMMARY.md.

4. **Max iteration count for smoke remediation sub-cycle.** ar-4-CONTEXT.md says "ar-4 IS allowed to iterate inside ar-4". Open question: how many iterations before user escalation? Default: 3 smoke iterations + 1 audit re-run, set in Task 2 + Task 3 resume-signals. User can override at any iteration by directing escalation. Alternative: unlimited iterations with progress-stalled detection. Default chosen — bounded budget keeps milestone-close attention focused.

5. **Pytest regression count target.** Wave 1 (ar-4-01) adds ≥10 new tests on top of ar-3's 113 baseline → ≥123 green target. Wave 2 (ar-4-02) adds ZERO new pytest tests because `scripts/smoke_milestone.py` is an observability driver. This matches ar-3-03's Layer 2a smoke exemption precedent. Default: target ≥123 green; the 1 known flake (`test_subprocess_smoke_with_max_iter_zero`) is tolerated. Alternative: write a unit test for the smoke driver's verdict-computation logic. Cost-benefit: the verdict logic is so trivial (regex count, attribute access, JSONL parse, ratio compute) that a unit test would essentially replicate the implementation; the value is in the live-pipeline run. Default: no unit tests for the driver — same call as ar-3-03 made for `test_caps_consolidated.py` Layer 2a smoke.

6. **Milestone-close commit message contains literal score placeholders.** Task 4 step 5 includes `<score>` placeholders that the orchestrator MUST replace with actual scores from the audit doc before invoking `git commit`. Risk: the orchestrator forgets to replace and ships a literal-placeholder commit message. Default: explicit guard rail in Task 4 step 5 ("The orchestrator MUST author the actual commit message — do NOT submit with literal `<score>` placeholders"). Verification: commit message readable on `git log -1 --format='%B'` does not contain literal `<score>`.

> **Operator note**: ar-4 Wave 2 milestone smoke (TEST-05) requires TAVILY_API_KEY + BRAVE_SEARCH_API_KEY in `~/.hermes/.env` on the Hermes deployment target (and Vertex creds if `OMNIGRAPH_LLM_PROVIDER=vertex_gemini` to exercise Grounding path). Local-dev workstation cannot run TEST-05 (3072/768 embedding-dim mismatch + corp-network blocked Tavily/Brave). Audit (TEST-06) is performed by the orchestrator after smoke passes; user reviews the audit doc before milestone is declared closed.
