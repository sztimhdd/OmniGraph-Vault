# Milestone 2: Knowledge Infrastructure MVP — Simple GSD Guide

**Duration:** 2-3 weeks | **Single Sequential Track**

---

## What You're Building

User asks `/architect` → system retrieves from KB + applies rules → gives safe defaults + don't-use + TDD template.

**By end of Milestone 2:**
- ✅ Rules engine (20-30 rules in JSON)
- ✅ KB populated (GitHub tools + KOL articles)
- ✅ `/architect` skill designed (SKILL.md + test cases)
- ✅ All tests passing

---

## Step-by-Step GSD Workflow

### **Step 1: Create Milestone in GSD**

```bash
/gsd:new-milestone
```

When prompted:
- **Name:** `Milestone 2: Knowledge Infrastructure MVP`
- **Description:** Build rules engine, populate KB with GitHub tools and KOL content, design /architect skill
- **Duration:** 2-3 weeks

✅ Creates: `.planning/milestones/milestone-2/`

---

### **Step 2: Plan Phase 2.1 — Rules Engine + KB**

```bash
/gsd:plan-phase "Milestone 2: Knowledge Infrastructure MVP" "Phase 2.1: Rules Engine + Knowledge Base"
```

Answer prompts with this structure:

**Phase Goal:**
```
Build 20-30 structured rules and populate KB with 50+ GitHub tools 
+ 5-10 KOL articles for /architect to query against.
```

**Success Criteria:**
```
✓ rules_engine.json exists with 20-30 testable rules
✓ entity_registry.json maps GitHub URLs → entity IDs
✓ 50-100 GitHub tools indexed in OmniGraph-Vault KB
✓ 5-10 KOL articles indexed in KB
✓ query_lightrag.py can answer "best practices" questions
```

**Tasks (in order):**

Copy this into the plan:

```
### Task 2.1-01: Bootstrap Rules (Use Copilot GPT-5.4 Researcher)
- Run Copilot with these research prompts:
  1. "Overengineering patterns in indie/hobby projects"
  2. "Tech debt pitfalls in architecture choices"  
  3. "Solo-dev constraints & decision frameworks"
- Output: Unstructured rules list
- Est: 4 hours
- Owner: Copilot (corp tool)

### Task 2.1-02: Convert Rules to JSON (You)
- Deduplicate + weight Copilot output
- Create rules_engine.json with structure:
  { "id": "rule_001", "condition": "...", "recommendation": "...", "dont_use": [...] }
- Test: 3 manual scenarios (solo dev, startup, researcher)
- Output: rules_engine.json at project root
- Est: 3 hours
- Blocker: Needs 2.1-01 complete

### Task 2.1-03: Ingest GitHub Tools via Graphify (Agent)
- Use Graphify MCP to fetch ~100 AI tools (LangChain, Claude, etc.)
- Run: python ingest_wechat.py --source graphify --list tools.json
- Create entity_registry.json (GitHub URL → entity ID mapping)
- Verify: query_lightrag.py "What is LangChain?" returns GitHub info
- Output: KB contains GitHub tools; entity_registry.json
- Est: 4 hours

### Task 2.1-04: Ingest KOL Content (You)
- Manually curate 5-10 articles:
  - 3 WeChat KOL posts (AI architecture)
  - 2 GitHub issue discussions  
  - 2 Zhihu Q&A posts
- Run: python ingest_wechat.py "URL" --tag kol --author "name"
- Verify: query_lightrag.py "Best practices for X?" → mixed sources
- Output: 5-10 articles in KB
- Est: 6 hours

### Integration Checkpoint
- Run: python query_lightrag.py "What are best practices for building a chatbot?" hybrid
- Verify: Response contains GitHub docs + KOL perspectives + canonicalized Chinese↔English terms
- If ✅ Pass: Ready for Phase 2.2
```

✅ Creates: `.planning/milestones/milestone-2/phases/02-01-PLAN.md`

---

### **Step 3: Execute Phase 2.1**

```bash
/gsd:execute-phase "Milestone 2: Knowledge Infrastructure MVP" "Phase 2.1: Rules Engine + Knowledge Base"
```

This enters execution mode. Work through tasks sequentially:

**2.1-01 (Copilot):**
- Give Copilot the 3 research prompts
- Collect unstructured rules

**2.1-02 (You):**
- Organize rules into `rules_engine.json`
- Test with 3 scenarios manually

**2.1-03 (Agent):**
- Ask me to write Graphify ingestion script
- Run it, validate KB updated

**2.1-04 (You):**
- Ingest 5-10 articles manually
- Verify mixed-source queries work

**Checkpoint:**
- Run test query
- If passes: `/gsd:check-todos` (mark tasks complete)

---

### **Step 4: Plan Phase 2.2 — /architect Skill**

```bash
/gsd:plan-phase "Milestone 2: Knowledge Infrastructure MVP" "Phase 2.2: /architect Skill Design + Testing"
```

**Phase Goal:**
```
Design /architect skill (Propose + Query + Ingest modes).
Enhance skill_runner.py for multi-turn testing.
All tests passing.
```

**Success Criteria:**
```
✓ GSD:DISCUSS pattern documented
✓ /architect SKILL.md complete (300-400 lines)
✓ scripts/architect.sh works
✓ skill_runner.py supports multi-turn conversations
✓ 9+ test cases written
✓ All tests pass: python skill_runner.py skills/ --test-all
```

**Tasks:**

```
### Task 2.2-01: Design GSD:DISCUSS Pattern (You)
- Document 4-step conversation flow:
  1. Default Guess (user says yes/no)
  2. Question 1 (focused question)
  3. Question 2 (constraint question)
  4. Output (safe defaults + don't-use + TDD)
- Write example Q&A for 1 persona (solo dev)
- Output: .planning/GSD_DISCUSS_PATTERN.md
- Est: 3 hours

### Task 2.2-02: Write /architect SKILL.md (Agent)
- Create skills/omnigraph_architect/SKILL.md
- Include: frontmatter + 3 decision tree cases (Propose, Query, Ingest)
- Write scripts/architect.sh wrapper
- Test locally: python skill_runner.py skills/omnigraph_architect "test message"
- Output: SKILL.md + scripts/ working
- Est: 5 hours
- Blocker: Needs 2.2-01 + 2.1-02 (rules available)

### Task 2.2-03: Enhance skill_runner.py (Agent)
- Add multi-turn support to skill_runner.py:
  - TestCase now has inputs: list[str] instead of single input
  - Maintain conversation context across turns
  - Check expect_final only on last response
- Test: Run multi-turn test case manually
- Output: skill_runner.py enhanced
- Est: 4 hours

### Task 2.2-04: Write /architect Test Cases (You)
- Create tests/skills/test_omnigraph_architect.json
- Write 9 cases (3 per mode):
  - Propose mode: 3 multi-turn scenarios (solo dev, startup, researcher)
  - Query mode: 3 single-turn knowledge questions
  - Ingest mode: 3 URL ingestion tests
- Est: 3 hours
- Blocker: Needs 2.2-03 (enhanced skill_runner)

### Task 2.2-05: Full Integration Test (You)
- Run: python skill_runner.py skills/ --test-all
- Verify: omnigraph_ingest ✅ omnigraph_query ✅ omnigraph_architect ✅
- If any fail: Debug + fix
- Output: All tests passing
- Est: 2 hours
```

✅ Creates: `.planning/milestones/milestone-2/phases/02-02-PLAN.md`

---

### **Step 5: Execute Phase 2.2**

```bash
/gsd:execute-phase "Milestone 2: Knowledge Infrastructure MVP" "Phase 2.2: /architect Skill Design + Testing"
```

Work through tasks 2.2-01 through 2.2-05 sequentially.

By end: `python skill_runner.py skills/ --test-all` shows all 3 skills passing ✅

---

### **Step 6: Complete Milestone**

```bash
/gsd:check-todos  # Verify all tasks done

/gsd:complete-milestone "Milestone 2: Knowledge Infrastructure MVP"
```

✅ Done. Ready for Phase 3 (Hermes wrapping).

---

## That's It.

No parallel tracks. No complicated matrix. Just:

1. Create milestone
2. Plan Phase 2.1 (Rules + KB)
3. Execute 2.1 (4 sequential tasks)
4. Plan Phase 2.2 (/architect skill)
5. Execute 2.2 (5 sequential tasks)
6. Complete milestone

**Total:** 2-3 weeks, single developer, clear checkpoints.

Ready?
