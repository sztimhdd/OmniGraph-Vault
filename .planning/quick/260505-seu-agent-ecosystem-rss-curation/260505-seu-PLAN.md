---
phase: quick
quick_id: 260505-seu
type: execute
autonomous: true
depends_on: []
files_modified:
  - data/agent_ecosystem_2026.opml
  - data/agent_ecosystem_2026.README.md
  - .planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md
  - .planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md
  - .planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md
---

<objective>
Replace the planned `data/karpathy_hn_2025.opml` (92 generic feeds) with a curated VitaClaw-relevant `data/agent_ecosystem_2026.opml` (60-80 feeds) that carries custom-namespaced attributes (`omg:dimension`, `omg:priority`, `omg:source_type`) so Phase 5's classifier and daily-digest grouping have meaningful structure.

Phase 5 has NOT executed yet (the 9 plans are sitting in `.planning/phases/05-pipeline-automation/` waiting); this task curates the source list AND surgically adjusts 3 of the 9 plans (05-01, 05-03, 05-05) to consume the new schema. Wave structure, dependency graph, frontmatter, plan count are all preserved.

Purpose: The previous Karpathy-bias source list is mismatched against VitaClaw's scope (agent runtimes, memory, MCP, sandbox, eval, browser automation). The new list adds 7-dimension taxonomy at OPML-level so the classifier can output `dimensions: list[str]` and the digest renderer can group articles by dimension for cleaner reading.

Output:
- 1 new OPML file (60-80 entries, all with `omg:*` attrs)
- 1 new README.md (curation rationale, blind spots, how-to-add-feeds)
- 3 surgically-edited Phase 5 PLAN.md files (no restructuring)
- 1 atomic git commit
</objective>

<context>
@.planning/STATE.md
@.planning/PROJECT.md
@./CLAUDE.md
@.planning/phases/05-pipeline-automation/05-CONTEXT.md
@.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md
@.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md
@.planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md

<key_constraints>
- Phase 5 has NOT executed — the OPML referenced in 05-01 doesn't exist on disk yet, so this is a clean swap (no migration needed).
- Locked decision D-07 (Phase 5 CONTEXT): RSS articles never enriched. The `rss_articles.enriched=2` filter does NOT apply to RSS in 05-05. Already correctly handled in 05-05; do NOT regress.
- D-08 (EN→CN in classifier prompt): preserve. Adding `dimensions` to the prompt does NOT change the EN→CN rule.
- D-15/D-18/D-19 (asymmetric UNION ALL, 7-dim taxonomy implied): the new OPML formalizes the 7-dim taxonomy at source level.
- The Phase 10 KOL `classifications` table does NOT have a `dimensions` column. Per task description: KOL articles get a flat depth-sorted "highlights" section; RSS gets dimension-grouped sections. This avoids touching Phase 10 schema.
- Working directory paths use forward slashes / Git Bash compatible (Windows env, `bash` shell).
</key_constraints>

<reference_files>
- `enrichment/rss_schema.py` — DOES NOT EXIST YET (Phase 5 not executed). The DDL is INLINE in 05-01 Task 1.1 lines 130-180.
- `enrichment/rss_classify.py` — DOES NOT EXIST YET. Code is INLINE in 05-03 Task 3.1 lines 130-295.
- `enrichment/daily_digest.py` — DOES NOT EXIST YET. Spec is INLINE in 05-05 Task 5.1 lines 122-147.
- All edits target the PLAN.md files only. Do NOT create or edit `enrichment/*.py` files in this quick task.
</reference_files>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Source research — assemble candidate feed list with star/access verification</name>
  <files>(scratch only — no files written this task; output is an in-memory candidate list passed to Task 2)</files>
  <read_first>
    - The `<full_task_description>` "Source candidates" section above.
    - Curation rules: ≥1000 stars on GitHub repos, no Twitter/X, agent/LLM/tooling/systems scope, prune Karpathy 92.
  </read_first>
  <action>
    **Goal:** Produce a working list of 60-80 candidate sources with all metadata required to write OPML in Task 2. No files written — keep working notes only.

    **Step 1.1 — Fetch + prune Karpathy 92 baseline.**
    ```bash
    # Fetch the upstream gist OPML once for reference
    gh api gists/e6d2bf860ccc367fe37ff953ba6de66b --jq '.files | keys'
    # Then for the actual file:
    gh api gists/e6d2bf860ccc367fe37ff953ba6de66b --jq '.files[].content' > /tmp/karpathy_hn_2025.opml
    grep -c '<outline ' /tmp/karpathy_hn_2025.opml  # expect 92
    ```
    Walk the 92 entries; KEEP only those agent/LLM/tooling/systems-relevant (target: ~30-45 surviving). DROP off-topic blogs (general philosophy, non-tech writing, dead feeds). Verify 5-10% sample of survivors still serve content in 2026 via `curl -sI <xmlUrl> | head -1` (expect HTTP/2 200 or 301 → 200).

    **Step 1.2 — GitHub releases.atom feeds with star verification.**
    For each candidate repo from the task description's list, run:
    ```bash
    gh api repos/<owner>/<repo> --jq '{stars: .stargazers_count, archived: .archived, default_branch: .default_branch}'
    ```
    KEEP only those with `stars >= 1000` AND `archived == false`. The atom URL is mechanically `https://github.com/<owner>/<repo>/releases.atom` — no need to fetch it; just verify it returns 200 with `curl -sI`.

    Categorize each kept repo with the OPML attributes (assign per the 7-dim taxonomy below):
    - `omg:dimension` ∈ {architecture, project, library, framework, skill, tool, idea}
    - `omg:priority` ∈ {core, peripheral} — `core` = directly relevant to VitaClaw (memory, MCP, agent runtimes, eval); `peripheral` = adjacent (general LLM serving, embeddings)
    - `omg:source_type` = `github_release` for releases.atom feeds

    Reference dimension assignments (use as guidance, not strict rule):
    - architecture: graphrag, neo4j, kuzu, langgraph (graph-of-state)
    - project: aider, open-interpreter, browser-use, e2b, daytona
    - library: pydantic-ai, outlines, instructor, lancedb
    - framework: langchain, autogen, crewAI, dspy, llama_index, letta
    - skill: SWE-bench, openai/evals (evaluation skills)
    - tool: litellm, gateway, playwright, mem0, zep, LightRAG
    - idea: MCP specification (protocol-as-idea), gvisor (sandbox idea)

    **Step 1.3 — Official engineering blogs.**
    Verify accessibility for each candidate (target ≥5):
    ```bash
    curl -sI https://huggingface.co/blog/feed.xml | head -1
    curl -sI https://www.anthropic.com/news/rss.xml 2>/dev/null | head -1  # try common paths
    ```
    For Anthropic specifically: try `https://www.anthropic.com/rss.xml`, `https://www.anthropic.com/news/feed`, `https://www.anthropic.com/news/rss.xml`. If none return 200, omit from final list (do NOT include broken feeds).

    OpenAI engineering blog feed paths shift; try `https://openai.com/blog/rss.xml`, `https://openai.com/news/rss.xml`. LangChain blog: `https://blog.langchain.dev/rss/`. Mistral, DeepMind, Cohere: search via Brave if direct paths 404.

    Tag each accessible blog with `omg:source_type="official_eng_blog"` and `omg:dimension="idea"` (engineering blogs are mostly research-direction signal).

    **Step 1.4 — Mandatory inclusions (user-named).**
    Add to the list (verify URLs only — these are user-mandated):
    - openclaw (find canonical repo: try `dench-ai/openclaw` or search "openclaw github" via `mcp__brave-search__brave_web_search`)
    - hermes (Hermes Agent — try `hermes-agent/hermes-agent` or similar)
    - vitaclaw (likely `<owner>/vitaclaw` — search if unknown)
    - gsd (search for "gsd github" — most likely `nteract/gsd` or similar; if no canonical repo found, omit and note in README)
    - MerkleTree (likely a generic concept — if no specific repo named MerkleTree applies to agent ecosystem, omit and note in README)

    For mandated repos: if found, include even if star count <1000 (user explicitly named overrides the star cap). Note their <1000-star status in the README's "Known blind spots" section.

    **Step 1.5 — Track count + dimension distribution.**
    Maintain a running tally:
    - Total entries (target 60-80; if <60, broaden Karpathy survivors; if >80, drop lowest-priority Karpathy entries)
    - Distribution across 7 `omg:dimension` values (acceptance requires ≥5 of 7 represented)
    - GitHub releases count (acceptance requires ≥20)
    - Official engineering blog count (acceptance requires ≥5)
    - Twitter/X URLs: 0 (acceptance requires zero)
  </action>
  <verify>
    <automated>echo "Manual research task — verification deferred to Task 2 OPML acceptance criteria"</automated>
  </verify>
  <acceptance_criteria>
    - Working candidate list assembled with all 4 attributes per entry: {name, xmlUrl, htmlUrl, omg:dimension, omg:priority, omg:source_type}.
    - Total candidates: 60-80.
    - At least 5 of 7 dimensions represented.
    - At least 20 entries with `omg:source_type="github_release"`.
    - At least 5 entries with `omg:source_type="official_eng_blog"`.
    - Zero Twitter/X URLs.
    - 100% of GitHub repo entries verified `stars >= 1000` (or flagged as user-mandated override).
    - Each non-GitHub feed URL probed with `curl -sI` and returned a 2xx or 3xx response.
  </acceptance_criteria>
  <done>Candidate list ready for OPML serialization in Task 2.</done>
</task>

<task type="auto">
  <name>Task 2: Write `data/agent_ecosystem_2026.opml` + `data/agent_ecosystem_2026.README.md`</name>
  <files>data/agent_ecosystem_2026.opml, data/agent_ecosystem_2026.README.md</files>
  <read_first>
    - Output of Task 1 (the working candidate list).
    - OPML 2.0 spec basics (custom namespace declaration, `<outline>` attributes).
  </read_first>
  <action>
    **Step 2.1 — Write `data/agent_ecosystem_2026.opml`.**

    Use this template structure (single body, 2-level nesting optional, ≥60 outlines):
    ```xml
    <?xml version="1.0" encoding="UTF-8"?>
    <opml version="2.0" xmlns:omg="https://omnigraph-vault/ns">
      <head>
        <title>Agent Ecosystem 2026 — VitaClaw Architecture Intelligence</title>
        <dateCreated>2026-05-05</dateCreated>
        <ownerName>OmniGraph-Vault</ownerName>
      </head>
      <body>
        <outline text="Memory Systems" title="Memory Systems">
          <outline type="rss"
                   text="mem0 releases"
                   xmlUrl="https://github.com/mem0ai/mem0/releases.atom"
                   htmlUrl="https://github.com/mem0ai/mem0"
                   omg:dimension="tool"
                   omg:priority="core"
                   omg:source_type="github_release"/>
          <!-- ... more entries ... -->
        </outline>
        <outline text="Agent Frameworks" title="Agent Frameworks">
          <!-- ... -->
        </outline>
        <!-- categories: Memory Systems, Graph/KG-RAG, Agent Frameworks, Tool Runtimes,
                         Browser Automation, MCP, Coding Agents, LLM Routing, Validation,
                         Evaluation, Sandbox/Security, Search/Research, Engineering Blogs,
                         Curated Karpathy Survivors -->
      </body>
    </opml>
    ```

    Strict rules:
    - Every leaf `<outline>` MUST be self-closing `/>` with attributes `type="rss"`, `text`, `xmlUrl`, `htmlUrl`, `omg:dimension`, `omg:priority`, `omg:source_type`. Five required attrs + namespace declaration.
    - Group folders (non-leaf outlines without `type="rss"`) carry only `text` and optionally `title`. They do NOT need `omg:*` attrs.
    - 60-80 leaf outlines total.
    - File MUST parse with `python -c "import xml.etree.ElementTree as ET; ET.parse('data/agent_ecosystem_2026.opml')"` — no syntax errors.

    **Step 2.2 — Write `data/agent_ecosystem_2026.README.md`.**

    Required sections (markdown):
    1. **Purpose** — One paragraph: what this OPML is, why it replaced Karpathy 92, who consumes it (Phase 5 RSS pipeline → daily digest grouped by dimension).
    2. **Custom namespace** — Document `xmlns:omg="https://omnigraph-vault/ns"`, the 3 attributes (`omg:dimension`, `omg:priority`, `omg:source_type`), and their value enums.
    3. **Curation rationale (per category)** — Bullet list of categories with 1-2 lines explaining what's IN scope and notable additions/cuts. Mention the Karpathy 92 → ~30-45 survivors decision rule.
    4. **How to add a new feed** — 5-step procedure: (1) verify ≥1000 stars (`gh api repos/x/y --jq .stargazers_count`); (2) verify atom URL returns 200 (`curl -sI`); (3) assign 3 omg attributes; (4) place under correct category folder in OPML; (5) re-run `tests/verify_rss_opml.py` to confirm parse + minimum count.
    5. **Known blind spots** — Explicitly enumerate:
       - Twitter/X excluded (no public RSS, value/noise ratio negative)
       - Closed-source-only tools (Devin, Cursor IDE) excluded
       - <1000-star user-named repos: list any (`openclaw`, `hermes`, `vitaclaw`, `gsd`, `MerkleTree` if found below threshold)
       - Engineering blogs without RSS endpoint: list any tried-but-skipped (e.g., DeepMind if no feed found)
    6. **Cron compatibility note** — One line: this OPML is consumed by `scripts/seed_rss_feeds.py` (Phase 5 Plan 05-01); see that plan for parser implementation.

    Length target: 80-150 lines. Plain markdown, no frontmatter required.
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "import xml.etree.ElementTree as ET; t=ET.parse('data/agent_ecosystem_2026.opml'); leaves=t.getroot().findall(\".//outline[@type='rss']\"); print(f'leaves={len(leaves)}'); assert 60 &lt;= len(leaves) &lt;= 80, f'expected 60-80 got {len(leaves)}'; ns={'omg':'https://omnigraph-vault/ns'}; missing=[l.get('text') for l in leaves if not all(l.get(f'{{{ns[\"omg\"]}}}{k}') for k in ('dimension','priority','source_type'))]; assert not missing, f'missing omg attrs: {missing[:5]}'; dims=set(l.get(f'{{{ns[\"omg\"]}}}dimension') for l in leaves); assert len(dims) &gt;= 5, f'only {len(dims)} dimensions: {dims}'; gh=sum(1 for l in leaves if l.get(f'{{{ns[\"omg\"]}}}source_type')=='github_release'); assert gh &gt;= 20, f'only {gh} github_release'; blogs=sum(1 for l in leaves if l.get(f'{{{ns[\"omg\"]}}}source_type')=='official_eng_blog'); assert blogs &gt;= 5, f'only {blogs} blogs'; tw=[l for l in leaves if 'twitter.com' in (l.get('xmlUrl') or '') or 'x.com' in (l.get('xmlUrl') or '')]; assert not tw, f'twitter found: {[l.get(\"text\") for l in tw]}'; print('OK')" &amp;&amp; test -f data/agent_ecosystem_2026.README.md</automated>
  </verify>
  <acceptance_criteria>
    - `data/agent_ecosystem_2026.opml` exists and parses with `xml.etree.ElementTree.parse()`.
    - 60-80 `<outline type="rss">` entries (verified via the consolidated python check above).
    - Every leaf has all 3 `omg:*` attributes set non-empty.
    - At least 5 of the 7 `omg:dimension` values appear.
    - At least 20 entries with `omg:source_type="github_release"`.
    - At least 5 entries with `omg:source_type="official_eng_blog"`.
    - Zero Twitter/X URLs (`grep -E 'twitter\.com|//x\.com' data/agent_ecosystem_2026.opml` returns no matches).
    - `data/agent_ecosystem_2026.README.md` exists with all 6 required sections (Purpose, Custom namespace, Curation rationale, How to add a new feed, Known blind spots, Cron compatibility).
    - 10% sampling check: pick 10% of GitHub repo entries randomly and verify `gh api repos/<owner>/<repo> --jq .stargazers_count` returns ≥1000 (or repo is in user-mandated override list documented in README).
  </acceptance_criteria>
  <done>OPML + README on disk, parseable, schema-correct.</done>
</task>

<task type="auto">
  <name>Task 3: Surgically edit 05-01-PLAN.md, 05-03-PLAN.md, 05-05-PLAN.md</name>
  <files>
    .planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md,
    .planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md,
    .planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md
  </files>
  <read_first>
    - Each of the 3 PLAN.md files (already read by orchestrator into context, but re-confirm exact line numbers before each Edit tool call).
    - The `<surgical_edits>` block below — these are the EXACT old_string→new_string pairs.
  </read_first>
  <action>
    **CRITICAL:** Use the `Edit` tool only. No file rewrites. Each edit below has been pre-specified by the planner; the executor's job is to apply them mechanically.

    Each `Edit` call uses `old_string` (verbatim from current PLAN.md) → `new_string` (planner-supplied). If the executor finds the old_string does NOT match (file drifted), STOP and report mismatch — do NOT improvise.

    **All edits to all 3 files BELOW. Apply in order.**

    ---

    ### File 1: `.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md`

    **Edit 1.A — `files_modified` block (frontmatter line 9):**
    - old_string: `  - data/karpathy_hn_2025.opml`
    - new_string: `  - data/agent_ecosystem_2026.opml`

    **Edit 1.B — `must_haves.truths` line 22 (OPML filename + count):**
    - old_string: `    - "OPML file `data/karpathy_hn_2025.opml` is bundled in-repo and contains exactly 92 RSS outline entries"`
    - new_string: `    - "OPML file `data/agent_ecosystem_2026.opml` is bundled in-repo and contains 60-80 RSS outline entries, each with `omg:dimension`, `omg:priority`, `omg:source_type` attributes (custom namespace `xmlns:omg=\"https://omnigraph-vault/ns\"`)"`

    **Edit 1.C — `must_haves.truths` line 23 (seed count):**
    - old_string: `    - "`scripts/seed_rss_feeds.py` parses the OPML and inserts 92 rows into `rss_feeds` (idempotent via UNIQUE xml_url)"`
    - new_string: `    - "`scripts/seed_rss_feeds.py` parses the OPML, extracts the 3 omg:* attributes, and inserts 60-80 rows into `rss_feeds` populating `dimension`, `priority`, `source_type` columns (idempotent via UNIQUE xml_url)"`

    **Edit 1.D — `must_haves.truths` line 25 (verify count):**
    - old_string: `    - "`tests/verify_rss_opml.py` asserts ≥ 90 feeds parse from the bundled OPML"`
    - new_string: `    - "`tests/verify_rss_opml.py` asserts ≥ 60 feeds parse from the bundled OPML and every leaf carries all 3 omg:* attributes"`

    **Edit 1.E — `must_haves.artifacts[0]` lines 27-28 (path + provides):**
    - old_string:
      ```
          - path: "data/karpathy_hn_2025.opml"
            provides: "Versioned OPML snapshot of Karpathy HN 2025 92-feed list"
      ```
    - new_string:
      ```
          - path: "data/agent_ecosystem_2026.opml"
            provides: "Versioned OPML snapshot of curated VitaClaw-relevant agent-ecosystem feed list (60-80 entries with omg:dimension|priority|source_type custom-namespace attributes)"
      ```

    **Edit 1.F — `must_haves.artifacts[2]` line 36 (verify_rss_opml `contains` value):**
    - old_string: `      contains: ">= 90"`
    - new_string: `      contains: ">= 60"`

    **Edit 1.G — Task 1.1 schema DDL block — `rss_feeds` CREATE TABLE (lines 132-143). Add 3 columns idempotently.**
    - old_string:
      ```
              """
              CREATE TABLE IF NOT EXISTS rss_feeds (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  xml_url TEXT NOT NULL UNIQUE,
                  html_url TEXT,
                  category TEXT,
                  active INTEGER DEFAULT 1,
                  last_fetched_at TEXT,
                  error_count INTEGER DEFAULT 0,
                  created_at TEXT DEFAULT (datetime('now', 'localtime'))
              )
              """,
      ```
    - new_string:
      ```
              """
              CREATE TABLE IF NOT EXISTS rss_feeds (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  xml_url TEXT NOT NULL UNIQUE,
                  html_url TEXT,
                  category TEXT,
                  active INTEGER DEFAULT 1,
                  last_fetched_at TEXT,
                  error_count INTEGER DEFAULT 0,
                  created_at TEXT DEFAULT (datetime('now', 'localtime')),
                  dimension TEXT,
                  priority TEXT,
                  source_type TEXT
              )
              """,
      ```

    **Edit 1.H — Task 1.1 `rss_classifications` CREATE TABLE — add `dimensions TEXT` column (lines 159-171). This supports the 05-03 classifier change.**
    - old_string:
      ```
              """
              CREATE TABLE IF NOT EXISTS rss_classifications (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  article_id INTEGER NOT NULL REFERENCES rss_articles(id),
                  topic TEXT NOT NULL,
                  depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
                  relevant INTEGER DEFAULT 0,
                  excluded INTEGER DEFAULT 0,
                  reason TEXT,
                  classified_at TEXT DEFAULT (datetime('now', 'localtime')),
                  UNIQUE(article_id, topic)
              )
              """,
      ```
    - new_string:
      ```
              """
              CREATE TABLE IF NOT EXISTS rss_classifications (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  article_id INTEGER NOT NULL REFERENCES rss_articles(id),
                  topic TEXT NOT NULL,
                  depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
                  relevant INTEGER DEFAULT 0,
                  excluded INTEGER DEFAULT 0,
                  reason TEXT,
                  dimensions TEXT,
                  classified_at TEXT DEFAULT (datetime('now', 'localtime')),
                  UNIQUE(article_id, topic)
              )
              """,
      ```

    **Edit 1.I — Task 1.3 description heading + content (the entire Task 1.3 block, lines 235-308). Replace OPML filename and curl recipe; bump count threshold; replace expected_samples with VitaClaw-relevant entries.** Apply as ONE edit covering the whole task block.

    - old_string: (the full block from `<task type="auto">` line 235 starting `<name>Task 1.3:` through `</task>` at line 308 — see file).
    - new_string: ENTIRE BLOCK rewritten as:
      ```xml
      <task type="auto">
        <name>Task 1.3: Bundle OPML snapshot + add feedparser/langdetect deps + verify parse</name>
        <files>data/agent_ecosystem_2026.opml, requirements.txt, tests/verify_rss_opml.py</files>
        <read_first>
          - .planning/phases/05-pipeline-automation/05-CONTEXT.md (Claude's Discretion: OPML source strategy — decision: bundle in-repo)
          - data/agent_ecosystem_2026.README.md (curation rationale; OPML structure)
          - requirements.txt (existing structure — alphabetical grouping preferred)
        </read_first>
        <action>
          **1. The OPML snapshot is already bundled.**
          `data/agent_ecosystem_2026.opml` was created by quick task 260505-seu (see `.planning/quick/260505-seu-agent-ecosystem-rss-curation/`). It is in-repo, 60-80 leaf outlines, each carrying `omg:dimension`, `omg:priority`, `omg:source_type` under custom namespace `xmlns:omg="https://omnigraph-vault/ns"`. No fetch needed — verify presence:
          ```bash
          ssh remote "cd ~/OmniGraph-Vault && test -f data/agent_ecosystem_2026.opml && wc -l data/agent_ecosystem_2026.opml"
          ```

          **2. Add deps to `requirements.txt`.**
          Append two lines preserving alphabetical order if the file is alphabetized, otherwise at the end:
          ```
          feedparser>=6.0
          langdetect>=1.0
          ```
          DO NOT re-sort or reformat the rest of the file (surgical change).

          Install on remote:
          ```bash
          ssh remote "cd ~/OmniGraph-Vault && venv/bin/pip install feedparser langdetect"
          ```

          **3. Create `tests/verify_rss_opml.py`:**
          ```python
          """Verify bundled OPML parses to at least 60 RSS feeds with all omg:* attrs set."""
          import sys
          from pathlib import Path
          import xml.etree.ElementTree as ET

          OPML = Path("data/agent_ecosystem_2026.opml")
          NS = {"omg": "https://omnigraph-vault/ns"}
          assert OPML.exists(), f"OPML not found at {OPML}"
          tree = ET.parse(OPML)
          feeds = tree.getroot().findall(".//outline[@type='rss']")
          print(f"feed_count: {len(feeds)}")
          assert 60 <= len(feeds) <= 80, f"Expected 60-80 feeds, got {len(feeds)}"

          # Every leaf has all 3 omg:* attrs non-empty
          missing = []
          for f in feeds:
              for attr in ("dimension", "priority", "source_type"):
                  v = f.get(f"{{{NS['omg']}}}{attr}")
                  if not v:
                      missing.append((f.get("text") or f.get("xmlUrl"), attr))
          assert not missing, f"Missing omg:* attrs on {len(missing)} entries: {missing[:5]}"

          # Spot check expected VitaClaw-relevant feeds
          urls = {f.get("xmlUrl") for f in feeds}
          expected_samples = [
              "langchain-ai",
              "microsoft",
              "huggingface.co",
          ]
          missing_samples = [s for s in expected_samples if not any(s in (u or "") for u in urls)]
          assert not missing_samples, f"Missing expected sample feeds: {missing_samples}"
          print("OK: OPML parse + omg-attr + sample check passed")
          sys.exit(0)
          ```
        </action>
        <verify>
          <automated>ssh remote "cd ~/OmniGraph-Vault && test -f data/agent_ecosystem_2026.opml && venv/bin/python tests/verify_rss_opml.py && venv/bin/pip list 2>/dev/null | grep -E '^(feedparser|langdetect)\s'" | wc -l | awk '{if($1 >= 2) exit 0; else exit 1}'</automated>
        </verify>
        <acceptance_criteria>
          - File `data/agent_ecosystem_2026.opml` exists; `python -c "import xml.etree.ElementTree as ET; ET.parse('data/agent_ecosystem_2026.opml')"` exits 0.
          - `tests/verify_rss_opml.py` exits 0 (60-80 feeds parsed, all omg:* attrs present, 3 known samples present).
          - `requirements.txt` contains `feedparser>=6.0` and `langdetect>=1.0`.
          - On remote, `venv/bin/pip list | grep -iE 'feedparser|langdetect'` returns both packages.
        </acceptance_criteria>
        <done>OPML bundled; deps installed; parse + omg:* validation verified.</done>
      </task>
      ```

    **Edit 1.J — Task 1.4 (lines 310-396). Replace OPML filename, parse to extract 3 new attrs, INSERT 7 columns instead of 4, update acceptance count and sample feeds.** Apply as ONE edit covering the whole task block.

    - old_string: (the full block from `<task type="auto">` line 310 starting `<name>Task 1.4:` through `</task>` at line 396 — see file).
    - new_string: ENTIRE BLOCK rewritten as:
      ```xml
      <task type="auto">
        <name>Task 1.4: Create seed script that populates `rss_feeds` from bundled OPML</name>
        <files>scripts/seed_rss_feeds.py</files>
        <read_first>
          - data/agent_ecosystem_2026.opml (Task 1.3 — already bundled)
          - enrichment/rss_schema.py (Task 1.1 output — schema DDL with dimension/priority/source_type columns added)
          - tests/verify_rss_opml.py (Task 1.3 output — parse pattern with namespace handling to reuse)
          - config.py (path to data dir — uses `BASE_DIR`, but `kol_scan.db` is at `data/kol_scan.db` relative to repo root)
        </read_first>
        <action>
          Create `scripts/seed_rss_feeds.py`:
          ```python
          """Seed rss_feeds table from bundled OPML.

          Idempotent via INSERT OR IGNORE (xml_url UNIQUE constraint). Safe to re-run.
          Run after batch_scan_kol.init_db has created the rss_feeds table.

          Reads the 3 custom-namespace attributes (omg:dimension, omg:priority, omg:source_type)
          and writes them into the new dimension/priority/source_type columns added in 05-01 Task 1.1.

          Usage:
              venv/bin/python scripts/seed_rss_feeds.py                # run
              venv/bin/python scripts/seed_rss_feeds.py --dry-run      # preview
          """
          from __future__ import annotations

          import argparse
          import sqlite3
          import sys
          import xml.etree.ElementTree as ET
          from pathlib import Path

          OPML = Path("data/agent_ecosystem_2026.opml")
          DB = Path("data/kol_scan.db")
          NS = {"omg": "https://omnigraph-vault/ns"}

          def parse_opml(path: Path) -> list[dict]:
              tree = ET.parse(path)
              feeds = []
              for outline in tree.getroot().findall(".//outline[@type='rss']"):
                  feeds.append({
                      "name": outline.get("text") or outline.get("title") or "",
                      "xml_url": outline.get("xmlUrl") or "",
                      "html_url": outline.get("htmlUrl") or None,
                      "category": None,
                      "dimension": outline.get(f"{{{NS['omg']}}}dimension") or None,
                      "priority": outline.get(f"{{{NS['omg']}}}priority") or None,
                      "source_type": outline.get(f"{{{NS['omg']}}}source_type") or None,
                  })
              return [f for f in feeds if f["xml_url"]]

          def seed(db_path: Path, feeds: list[dict], dry_run: bool) -> tuple[int, int]:
              conn = sqlite3.connect(db_path)
              try:
                  before = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
                  if not dry_run:
                      conn.executemany(
                          """INSERT OR IGNORE INTO rss_feeds
                             (name, xml_url, html_url, category, dimension, priority, source_type)
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          [(f["name"], f["xml_url"], f["html_url"], f["category"],
                            f["dimension"], f["priority"], f["source_type"]) for f in feeds],
                      )
                      conn.commit()
                  after = conn.execute("SELECT COUNT(*) FROM rss_feeds").fetchone()[0]
                  return before, after
              finally:
                  conn.close()

          def main() -> None:
              p = argparse.ArgumentParser()
              p.add_argument("--dry-run", action="store_true")
              args = p.parse_args()
              feeds = parse_opml(OPML)
              print(f"Parsed {len(feeds)} feeds from {OPML}")
              before, after = seed(DB, feeds, args.dry_run)
              print(f"rss_feeds count: {before} -> {after}")
              if args.dry_run:
                  print("(dry-run: no writes)")

          if __name__ == "__main__":
              main()
          ```

          Ensure the script prints the before/after count. On a fresh DB (empty `rss_feeds`), after count should be 60-80 (matching the OPML). On re-run, before == after (dedup via UNIQUE constraint).
        </action>
        <verify>
          <automated>ssh remote "cd ~/OmniGraph-Vault && venv/bin/python scripts/seed_rss_feeds.py && sqlite3 data/kol_scan.db 'SELECT COUNT(*) FROM rss_feeds'" | tail -1 | awk '{if($1 >= 60) exit 0; else exit 1}'</automated>
        </verify>
        <acceptance_criteria>
          - `scripts/seed_rss_feeds.py` exists.
          - After running on remote, `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds"` returns ≥ 60.
          - Re-running the script produces "rss_feeds count: <N> -> <N>" (no duplicates inserted).
          - The new columns are populated: `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds WHERE dimension IS NOT NULL AND priority IS NOT NULL AND source_type IS NOT NULL"` returns ≥ 60 (every row has all 3 attrs).
          - At least 5 distinct dimension values present: `sqlite3 data/kol_scan.db "SELECT COUNT(DISTINCT dimension) FROM rss_feeds"` returns ≥ 5.
          - Three known feeds are present: `sqlite3 data/kol_scan.db "SELECT COUNT(*) FROM rss_feeds WHERE xml_url LIKE '%langchain%' OR xml_url LIKE '%microsoft%' OR xml_url LIKE '%huggingface%'"` returns ≥ 3.
        </acceptance_criteria>
        <done>60-80 feeds registered with dimension/priority/source_type populated; ready for `rss_fetch.py` in Plan 05-02.</done>
      </task>
      ```

    ---

    ### File 2: `.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md`

    **Edit 2.A — `CLASSIFY_PROMPT` constant (lines 165-181). Add `dimensions` to output JSON contract.**

    - old_string:
      ```
          CLASSIFY_PROMPT = """
      你是技术文章分类器。给定一篇文章的标题和正文（可能是英文或中文），请对它在主题 "{topic}" 上做分类。

      **规则**：
      - 必须用中文回答 reason（无论原文语言）。
      - depth_score: 1=资讯/快讯，2=技术教程/分析，3=深度研究/架构拆解。
      - relevant: 0 或 1（是否与主题相关）。
      - excluded: 0 或 1（是否应被剔除，例如广告/招聘/纯转载）。
      - 只输出 JSON，不要任何其他文字。不要代码块围栏，不要解释。

      输入：
      title: {title}
      content: {content}

      输出 JSON 格式：
      {{"topic": "{topic}", "depth_score": 1|2|3, "relevant": 0|1, "excluded": 0|1, "reason": "<中文简要说明>"}}
      """
      ```
    - new_string:
      ```
          CLASSIFY_PROMPT = """
      你是技术文章分类器。给定一篇文章的标题和正文（可能是英文或中文），请对它在主题 "{topic}" 上做分类。

      **规则**：
      - 必须用中文回答 reason（无论原文语言）。
      - depth_score: 1=资讯/快讯，2=技术教程/分析，3=深度研究/架构拆解。
      - relevant: 0 或 1（是否与主题相关）。
      - excluded: 0 或 1（是否应被剔除，例如广告/招聘/纯转载）。
      - dimensions: list[str] — 选自 7 维分类法：{{"architecture","project","library","framework","skill","tool","idea"}}。一篇文章可对应 1-3 个维度；至少返回 1 个。第 1 个为主维度（primary），用于 daily-digest 分组。
      - 只输出 JSON，不要任何其他文字。不要代码块围栏，不要解释。

      输入：
      title: {title}
      content: {content}

      输出 JSON 格式：
      {{"topic": "{topic}", "depth_score": 1|2|3, "relevant": 0|1, "excluded": 0|1, "reason": "<中文简要说明>", "dimensions": ["<primary>", "<optional secondary>", ...]}}
      """
      ```

    **Edit 2.B — `_classify` parse logic (lines 208-220). Extract + validate dimensions.**

    - old_string:
      ```
          def _classify(api_key: str, title: str, content: str, topic: str) -> dict:
              prompt = CLASSIFY_PROMPT.format(topic=topic, title=title[:200], content=content[:4000])
              data = _call_deepseek(prompt, api_key)
              # Strict parse
              depth = int(data["depth_score"])
              assert 1 <= depth <= 3
              return {
                  "topic": topic,
                  "depth_score": depth,
                  "relevant": int(bool(data.get("relevant", 0))),
                  "excluded": int(bool(data.get("excluded", 0))),
                  "reason": str(data.get("reason", ""))[:500],
              }
      ```
    - new_string:
      ```
          VALID_DIMENSIONS = {"architecture", "project", "library", "framework", "skill", "tool", "idea"}

          def _classify(api_key: str, title: str, content: str, topic: str) -> dict:
              prompt = CLASSIFY_PROMPT.format(topic=topic, title=title[:200], content=content[:4000])
              data = _call_deepseek(prompt, api_key)
              # Strict parse
              depth = int(data["depth_score"])
              assert 1 <= depth <= 3
              # Dimensions: list[str] subset of 7-dim taxonomy; LLM must return ≥ 1.
              raw_dims = data.get("dimensions") or []
              if not isinstance(raw_dims, list):
                  raise ValueError(f"dimensions must be list, got {type(raw_dims).__name__}")
              dims = [d for d in raw_dims if isinstance(d, str) and d in VALID_DIMENSIONS]
              if not dims:
                  # Fallback: do not lose the row if LLM returned bad/empty dimensions; tag as "idea"
                  dims = ["idea"]
              return {
                  "topic": topic,
                  "depth_score": depth,
                  "relevant": int(bool(data.get("relevant", 0))),
                  "excluded": int(bool(data.get("excluded", 0))),
                  "reason": str(data.get("reason", ""))[:500],
                  "dimensions": dims,
              }
      ```

    **Edit 2.C — INSERT statement (lines 263-267). Add `dimensions` JSON-encoded column.**

    - old_string:
      ```
                          conn.execute(
                              """INSERT INTO rss_classifications
                                 (article_id, topic, depth_score, relevant, excluded, reason)
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (aid, topic, result["depth_score"], result["relevant"],
                               result["excluded"], result["reason"]),
                          )
      ```
    - new_string:
      ```
                          conn.execute(
                              """INSERT INTO rss_classifications
                                 (article_id, topic, depth_score, relevant, excluded, reason, dimensions)
                                 VALUES (?, ?, ?, ?, ?, ?, ?)""",
                              (aid, topic, result["depth_score"], result["relevant"],
                               result["excluded"], result["reason"], json.dumps(result["dimensions"])),
                          )
      ```

    **Edit 2.D — `must_haves.truths` (lines 14-19). Add a truth about dimensions.**

    - old_string:
      ```
        truths:
          - "`enrichment/rss_classify.py` reads unclassified rss_articles and writes rows to rss_classifications"
          - "Classifier LLM call reuses `batch_classify_kol.py` logic (same prompt shape + same JSON parse + same topic taxonomy)"
          - "EN→CN handling happens inside the prompt per D-08 — no separate translation step"
          - "Depth score parsing is strict (1-3 integer, bounded) with UNIQUE(article_id, topic) dedup"
          - "Per-article try/except — one LLM failure does not abort the run"
          - "Supports `--article-id N --dry-run` for single-article test mode"
      ```
    - new_string:
      ```
        truths:
          - "`enrichment/rss_classify.py` reads unclassified rss_articles and writes rows to rss_classifications"
          - "Classifier LLM call reuses `batch_classify_kol.py` logic (same prompt shape + same JSON parse + same topic taxonomy)"
          - "EN→CN handling happens inside the prompt per D-08 — no separate translation step"
          - "Depth score parsing is strict (1-3 integer, bounded) with UNIQUE(article_id, topic) dedup"
          - "LLM emits BOTH `depth_score (1-3)` AND `dimensions: list[str]` (subset of 7-dim taxonomy: architecture/project/library/framework/skill/tool/idea); written as JSON-encoded string into `rss_classifications.dimensions` column"
          - "Per-article try/except — one LLM failure does not abort the run"
          - "Supports `--article-id N --dry-run` for single-article test mode"
      ```

    **Edit 2.E — Acceptance criteria — add dimensions check (in Task 3.1 acceptance, lines 302-311). Insert one new criterion line after the existing `grep` for `必须用中文`.**

    - old_string:
      ```
          - `grep -q "请用中文回答" enrichment/rss_classify.py OR grep -q "必须用中文" enrichment/rss_classify.py` returns 0 (D-08 enforcement — Chinese-output instruction in prompt).
      ```
    - new_string:
      ```
          - `grep -q "请用中文回答" enrichment/rss_classify.py OR grep -q "必须用中文" enrichment/rss_classify.py` returns 0 (D-08 enforcement — Chinese-output instruction in prompt).
          - `grep -q "VALID_DIMENSIONS" enrichment/rss_classify.py` returns 0 (7-dim taxonomy guard present).
          - `grep -q "json.dumps(result\[\"dimensions\"\])" enrichment/rss_classify.py` returns 0 (dimensions JSON-encoded into INSERT).
      ```

    ---

    ### File 3: `.planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md`

    **Edit 3.A — `CANDIDATE_SQL` shape in `<interfaces>` block (lines 79-95). Add `c.dimensions` selection in RSS branch; KOL branch returns NULL placeholder so column count matches in UNION.**

    - old_string:
      ```
      Candidate SQL (planner-supplied shape):
      ```
      SELECT 'kol' AS src, a.id, a.title, a.url, a.author AS source, a.content AS body,
             c.topic, c.depth_score, c.classified_at, a.content_length
      FROM articles a JOIN classifications c ON c.article_id = a.id
      WHERE date(a.fetched_at) = ?
        AND c.depth_score >= 2 AND a.enriched = 2
      UNION ALL
      SELECT 'rss' AS src, a.id, a.title, a.url, f.name AS source, a.summary AS body,
             c.topic, c.depth_score, c.classified_at, a.content_length
      FROM rss_articles a JOIN rss_classifications c ON c.article_id = a.id
                          JOIN rss_feeds f ON a.feed_id = f.id
      WHERE date(a.fetched_at) = ?
        AND c.depth_score >= 2 AND a.enriched = 2
      ORDER BY depth_score DESC, content_length DESC, classified_at DESC
      LIMIT ?;
      ```
      ```
    - new_string:
      ```
      Candidate SQL (planner-supplied shape):
      ```
      -- KOL branch: NULL placeholder for dimensions (Phase 10 classifications schema has no dimensions column).
      -- RSS branch: c.dimensions is JSON-encoded list[str] from 05-03 classifier.
      -- Per D-07 REVISED: KOL requires enriched=2; RSS does NOT.
      SELECT 'kol' AS src, a.id, a.title, a.url, a.author AS source, a.content AS body,
             c.topic, c.depth_score, c.classified_at, a.content_length, NULL AS dimensions
      FROM articles a JOIN classifications c ON c.article_id = a.id
      WHERE date(a.fetched_at) = ?
        AND c.depth_score >= 2 AND a.enriched = 2
      UNION ALL
      SELECT 'rss' AS src, a.id, a.title, a.url, f.name AS source, a.summary AS body,
             c.topic, c.depth_score, c.classified_at, a.content_length, c.dimensions AS dimensions
      FROM rss_articles a JOIN rss_classifications c ON c.article_id = a.id
                          JOIN rss_feeds f ON a.feed_id = f.id
      WHERE date(a.fetched_at) = ?
        AND c.depth_score >= 2
      ORDER BY depth_score DESC, content_length DESC, classified_at DESC
      LIMIT ?;
      ```
      ```

    **Edit 3.B — Behavior tests (lines 106-113). Update Test 1 (sort is now per-group) and add new tests for grouping.**

    - old_string:
      ```
        <behavior>
          - Test 1: Given 7 candidate articles, the query+sort returns exactly 5 sorted by depth DESC, length DESC, classified_at DESC.
          - Test 2: Markdown output matches PRD section 3.3.2 shape — header, numbered entries with [topic], source line, excerpt, link, footer stats.
          - Test 3: Empty candidate pool — no Telegram send + log line "no candidates, skipping digest" + no archive file written.
          - Test 4: `--dry-run` does not call Telegram and does not write archive; prints rendered Markdown.
          - Test 5: Archive write uses atomic tmp-then-rename (test: `os.replace` or `.tmp` suffix present in code path).
          - Test 6: Archive path is `~/.hermes/omonigraph-vault/digests/<date>.md` (typo'd dir).
        </behavior>
      ```
    - new_string:
      ```
        <behavior>
          - Test 1: Within each `omg:dimension` group, sort is depth_score DESC, content_length DESC, classified_at DESC. Each group capped at 3 (TOP_N_PER_GROUP).
          - Test 2: Markdown output matches PRD section 3.3.2 shape — header, KOL "highlights" flat section first, then per-dimension RSS sections (only non-empty dimensions render), numbered entries with [topic], source line, excerpt, link, footer stats.
          - Test 3: Empty candidate pool (KOL=0 + RSS=0) — no Telegram send + log line "no candidates, skipping digest" + no archive file written.
          - Test 4: `--dry-run` does not call Telegram and does not write archive; prints rendered Markdown.
          - Test 5: Archive write uses atomic tmp-then-rename (test: `os.replace` or `.tmp` suffix present in code path).
          - Test 6: Archive path is `~/.hermes/omonigraph-vault/digests/<date>.md` (typo'd dir).
          - Test 7: Multi-dimension grouping — given 6 RSS candidates spanning 3 distinct primary dimensions (e.g., 2× tool, 2× framework, 2× idea), digest renders 3 separate sections each with its 2 entries. Empty dimensions are not rendered.
          - Test 8: TOP_N_PER_GROUP cap — given 5 RSS candidates with primary dimension `tool`, only 3 are rendered in the `tool` section (sorted by depth DESC then length DESC).
          - Test 9: KOL flat section — KOL candidates are rendered as a single flat depth-sorted "highlights" section (no dimension grouping); appears above the RSS dimension sections.
        </behavior>
      ```

    **Edit 3.C — `render` function design bullet (line 131). Replace single TOP-N renderer with grouped renderer; introduce TOP_N_PER_GROUP.**

    - old_string:
      ```
          - Constants: `DB = Path("data/kol_scan.db")`, `DIGEST_DIR = BASE_DIR / "digests"`, `TOP_N = 5`.
          - `CANDIDATE_SQL` constant: exactly the UNION ALL query from the `<interfaces>` block above, with 3 `?` placeholders (date, date, limit).
          - `def _excerpt(body: str, max_chars: int = 120) -> str`: flatten whitespace, truncate with ellipsis.
          - `def gather(date: str, top_n: int = TOP_N) -> tuple[list[dict], dict]`: execute `CANDIDATE_SQL` + stats queries (KOL total, RSS total, deep total); return `(candidates, stats)`.
          - `def render(date: str, candidates: list[dict], stats: dict) -> str`: build Markdown per PRD section 3.3.2. Header line, numbered entries with `[topic] Title`, source line (`source · WeChat` or `source · RSS`), excerpt, link. Footer: `Scanned today: {kol} KOL + {rss} RSS | Deep: {deep} | Ingested: {ingested}`.
      ```
    - new_string:
      ```
          - Constants: `DB = Path("data/kol_scan.db")`, `DIGEST_DIR = BASE_DIR / "digests"`, `TOP_N_PER_GROUP = 3`. The 7-dim group ordering is fixed: `architecture, framework, project, library, tool, skill, idea` (architecture-first to surface design intel; idea last because it absorbs official-eng-blog noise).
          - `CANDIDATE_SQL` constant: exactly the UNION ALL query from the `<interfaces>` block above (with `c.dimensions` selected on RSS branch and NULL on KOL branch), with 3 `?` placeholders (date, date, limit). Use a generous limit (e.g. 100) — per-group cap happens in Python.
          - `def _excerpt(body: str, max_chars: int = 120) -> str`: flatten whitespace, truncate with ellipsis.
          - `def _primary_dimension(dimensions_json: str | None) -> str | None`: parse JSON list, return first element if non-empty, else `None`. Returns `None` for KOL rows (column is NULL).
          - `def gather(date: str, limit: int = 100) -> tuple[list[dict], dict]`: execute `CANDIDATE_SQL` + stats queries (KOL total, RSS total, deep total); return `(candidates, stats)`. Each row dict includes `src`, `title`, `url`, `source`, `body`, `topic`, `depth_score`, `classified_at`, `content_length`, `dimensions` (raw JSON or NULL).
          - `def render(date: str, candidates: list[dict], stats: dict) -> str`: build Markdown per PRD section 3.3.2 with TWO sections:
            1. **KOL highlights** (flat) — all `src='kol'` rows sorted by depth DESC, content_length DESC, classified_at DESC; cap to top 5; rendered as numbered entries with `[topic] Title`. Skip section header if zero KOL rows.
            2. **RSS by dimension** (grouped) — for each `src='rss'` row, compute primary_dimension via `_primary_dimension(dimensions)`; bucket by primary_dimension. For each dimension in the fixed order, if bucket non-empty, render an H2 header `## {Dimension}` then top 3 entries sorted by depth DESC, content_length DESC, classified_at DESC. Skip empty buckets.
            Footer: `Scanned today: {kol} KOL + {rss} RSS | Deep: {deep} | Ingested: {ingested}`.
      ```

    **Edit 3.D — `must_haves.truths` (lines 13-21). Update truth about TOP_N + per-group cap.**

    - old_string:
      ```
        truths:
          - "`enrichment/daily_digest.py` selects today's depth>=2 articles via asymmetric UNION ALL: KOL branch (articles JOIN classifications) requires `enriched=2` per Phase 4 contract; RSS branch (rss_articles JOIN rss_classifications) has NO enriched filter per D-07 REVISED 2026-05-02 + D-19. Sort: depth_score DESC, content_length DESC, classified_at DESC."
          - "TOP 5 (configurable) rendered as Markdown per PRD section 3.3.2 sample format"
          - "Markdown includes title, category tag, source, 1-2 line excerpt, link"
          - "Telegram delivery via existing Phase 4 path (reuses TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"
          - "Local archive written atomically to `~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md`"
          - "Empty-state behavior: if zero candidates, skip Telegram (silent log) per CONTEXT.md Claude's Discretion item 4"
          - "`--date YYYY-MM-DD` and `--dry-run` CLI flags supported"
      ```
    - new_string:
      ```
        truths:
          - "`enrichment/daily_digest.py` selects today's depth>=2 articles via asymmetric UNION ALL: KOL branch (articles JOIN classifications) requires `enriched=2` per Phase 4 contract; RSS branch (rss_articles JOIN rss_classifications, with c.dimensions selected) has NO enriched filter per D-07 REVISED 2026-05-02 + D-19. Sort: depth_score DESC, content_length DESC, classified_at DESC."
          - "Render is two-section: (1) KOL flat 'highlights' top-5 depth-sorted; (2) RSS grouped by primary `omg:dimension` (first element of `dimensions` JSON list), each non-empty group capped at `TOP_N_PER_GROUP=3`."
          - "Markdown includes title, category tag, source, 1-2 line excerpt, link"
          - "Telegram delivery via existing Phase 4 path (reuses TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)"
          - "Local archive written atomically to `~/.hermes/omonigraph-vault/digests/YYYY-MM-DD.md`"
          - "Empty-state behavior: if zero candidates (KOL=0 AND RSS=0), skip Telegram (silent log) per CONTEXT.md Claude's Discretion item 4"
          - "`--date YYYY-MM-DD` and `--dry-run` CLI flags supported"
      ```

    **Edit 3.E — Acceptance — replace single LIMIT-based grep with per-group cap grep (lines 151-160).**

    - old_string:
      ```
          - File `enrichment/daily_digest.py` exists; at least 160 lines.
          - Exactly one `UNION ALL` in `CANDIDATE_SQL`.
          - `grep -q "ORDER BY depth_score DESC, content_length DESC, classified_at DESC" enrichment/daily_digest.py` returns 0.
          - `grep -q "LIMIT ?" enrichment/daily_digest.py` returns 0 (parameterized top-N).
          - `grep -q "os.replace" enrichment/daily_digest.py` returns 0 (atomic write).
          - `grep -q "BASE_DIR\|omonigraph-vault" enrichment/daily_digest.py` returns 0 (typo preserved).
          - All 6 pytest tests pass.
          - `--dry-run` on remote exits 0 and prints Markdown OR "no candidates" log line.
      ```
    - new_string:
      ```
          - File `enrichment/daily_digest.py` exists; at least 180 lines (was 160; bumped for grouping logic + 3 new tests).
          - Exactly one `UNION ALL` in `CANDIDATE_SQL`.
          - `grep -q "ORDER BY depth_score DESC, content_length DESC, classified_at DESC" enrichment/daily_digest.py` returns 0.
          - `grep -q "TOP_N_PER_GROUP = 3" enrichment/daily_digest.py` returns 0 (per-group cap constant present).
          - `grep -q "_primary_dimension" enrichment/daily_digest.py` returns 0 (helper present).
          - `grep -q "os.replace" enrichment/daily_digest.py` returns 0 (atomic write).
          - `grep -q "BASE_DIR\|omonigraph-vault" enrichment/daily_digest.py` returns 0 (typo preserved).
          - All 9 pytest tests pass (was 6; +3 for grouping/cap/KOL-flat).
          - `--dry-run` on remote exits 0 and prints Markdown OR "no candidates" log line.
      ```

    ---

    **Final step:** After all edits applied, sanity-check each PLAN.md still has its frontmatter intact and no orphan `<task>` tags (run `python -c "import re; print(open('05-01-...').read()).count('<task'))"` etc., expect counts unchanged from before edits in 05-01 = 4 tasks, 05-03 = 1 task, 05-05 = 1 task).
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; python -c "
import re
files = {
    '.planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md': 4,
    '.planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md': 1,
    '.planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md': 1,
}
for path, expected_tasks in files.items():
    s = open(path, encoding='utf-8').read()
    actual = len(re.findall(r'&lt;task type=', s))
    assert actual == expected_tasks, f'{path}: expected {expected_tasks} tasks, got {actual}'
    assert 'karpathy_hn_2025' not in s, f'{path}: stale karpathy reference'
    if '05-01' in path:
        assert 'agent_ecosystem_2026.opml' in s, f'{path}: new OPML name missing'
        assert 'dimension TEXT' in s, f'{path}: new column DDL missing'
        assert 'dimensions TEXT' in s, f'{path}: rss_classifications.dimensions column missing'
    if '05-03' in path:
        assert 'VALID_DIMENSIONS' in s, f'{path}: VALID_DIMENSIONS not added'
        assert 'json.dumps(result' in s, f'{path}: JSON encode not added'
    if '05-05' in path:
        assert 'TOP_N_PER_GROUP' in s, f'{path}: TOP_N_PER_GROUP not added'
        assert '_primary_dimension' in s, f'{path}: _primary_dimension helper not added'
print('OK: all 3 PLAN.md files passed structural + edit-content checks')
"</automated>
  </verify>
  <acceptance_criteria>
    - All 3 PLAN.md files edited; frontmatter intact (top `---` line still present, plan/phase/wave/depends_on unchanged).
    - Task counts unchanged: 05-01 = 4 tasks, 05-03 = 1 task, 05-05 = 1 task.
    - Zero `karpathy_hn_2025` references survive in any of the 3 PLAN.md files.
    - 05-01 contains: `agent_ecosystem_2026.opml`, `dimension TEXT`, `priority TEXT`, `source_type TEXT`, `dimensions TEXT` (in rss_classifications schema).
    - 05-03 contains: `VALID_DIMENSIONS`, the new dimensions field in CLASSIFY_PROMPT, `json.dumps(result["dimensions"])` in INSERT.
    - 05-05 contains: `TOP_N_PER_GROUP = 3`, `_primary_dimension`, the updated render-function spec.
    - Wave structure preserved (no `wave:` line changed; no `depends_on:` line changed).
  </acceptance_criteria>
  <done>3 PLAN.md files surgically updated; Phase 5 wave/dependency graph untouched.</done>
</task>

<task type="auto">
  <name>Task 4: Atomic git commit</name>
  <files>(no new files; commits the 5 modified/created files)</files>
  <read_first>
    - Output of Tasks 2 and 3 (5 files total).
  </read_first>
  <action>
    Stage and commit only the 5 files this task touched. Do NOT use `git add -A` (avoids picking up unrelated working-tree files).

    ```bash
    cd /c/Users/huxxha/Desktop/OmniGraph-Vault
    git add \
      data/agent_ecosystem_2026.opml \
      data/agent_ecosystem_2026.README.md \
      .planning/phases/05-pipeline-automation/05-01-rss-schema-and-opml-PLAN.md \
      .planning/phases/05-pipeline-automation/05-03-rss-classify-PLAN.md \
      .planning/phases/05-pipeline-automation/05-05-daily-digest-PLAN.md \
      .planning/quick/260505-seu-agent-ecosystem-rss-curation/260505-seu-PLAN.md
    git status --short
    git commit -m "docs(05): curate VitaClaw-relevant RSS source list — agent_ecosystem_2026.opml"
    git log -1 --stat
    ```

    Verify the commit landed:
    ```bash
    git log -1 --pretty=format:'%H %s' | grep -E 'agent_ecosystem_2026' && echo COMMIT_OK
    ```

    Do NOT push. Pushing is a separate operator step.
  </action>
  <verify>
    <automated>cd /c/Users/huxxha/Desktop/OmniGraph-Vault &amp;&amp; git log -1 --pretty=format:'%s' | grep -q 'agent_ecosystem_2026.opml' &amp;&amp; git log -1 --stat | grep -E 'data/agent_ecosystem_2026\.(opml|README\.md)' | wc -l | awk '{if($1 &gt;= 2) exit 0; else exit 1}'</automated>
  </verify>
  <acceptance_criteria>
    - `git log -1 --pretty=%s` matches `docs(05): curate VitaClaw-relevant RSS source list — agent_ecosystem_2026.opml`.
    - `git log -1 --stat` shows all 5 expected files (2 new under `data/`, 3 modified under `.planning/phases/05-pipeline-automation/`) plus the new `.planning/quick/260505-seu-agent-ecosystem-rss-curation/260505-seu-PLAN.md`.
    - Working tree shows no other unintended files staged: `git status --short` should not list any files outside the 6 expected paths.
  </acceptance_criteria>
  <done>Quick task committed atomically; ready for Phase 5 execution to consume the new OPML when its execute gate lifts.</done>
</task>

</tasks>

<verification>
- `data/agent_ecosystem_2026.opml` parses cleanly; 60-80 leaves; all 3 omg:* attrs populated; ≥5 dimensions / ≥20 github_release / ≥5 official_eng_blog / 0 twitter URLs.
- `data/agent_ecosystem_2026.README.md` exists with 6 required sections.
- All 3 Phase 5 PLAN.md files surgically updated; zero `karpathy_hn_2025` references survive; task counts and wave structure unchanged.
- One atomic git commit landed with the prescribed message.
</verification>

<success_criteria>
- ✅ OPML schema (omg:dimension|priority|source_type) consumable by Phase 5 plans 05-01/05-03/05-05 without further refactor.
- ✅ Phase 5 wave structure (Wave 1 = 05-01..05-03, Wave 2 = 05-04..05-05) preserved — quick task did not touch wave numbers, depends_on, or plan ordering.
- ✅ Locked Phase 5 decisions (D-07 RSS-not-enriched, D-08 EN→CN-in-prompt, D-15/D-18/D-19 asymmetric UNION ALL) preserved.
- ✅ Out-of-scope guarantees: no execution of any Phase 5 plan; no edits to 05-CONTEXT.md / 05-PRD.md / other plans (00, 02, 04, 06); no edits to production source code (lib/, ingest_wechat.py, etc.).
- ✅ User-named mandates (openclaw, hermes, vitaclaw, gsd, MerkleTree) addressed — included where canonical repo found, documented in README "Known blind spots" where not.
</success_criteria>

<output>
After all 4 tasks complete, create a brief SUMMARY at `.planning/quick/260505-seu-agent-ecosystem-rss-curation/260505-seu-SUMMARY.md` with: final feed count, dimension distribution, count of github_release / official_eng_blog / curated-Karpathy-survivors entries, list of mandated-but-omitted user names + reasons (if any), and the commit SHA.
</output>
