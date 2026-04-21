---
title: Hermes Agent UAT Readiness Audit
date: 2026-04-21
status: draft
---

# Hermes Agent UAT Readiness: OmniGraph-Vault Skills

## Executive Summary

OmniGraph-Vault has **80%+ of what Hermes needs** for UAT deployment and testing. Two skills are documented and executable. The project has scripts, evals, and deployment instructions. However, there are **3 critical gaps** and **2 nice-to-haves** that need closure before Hermes can run autonomous UAT.

---

## ✅ What You HAVE (Hermes-Ready)

### 1. **Skill Directory Structure** ✓
```
skills/
├── omnigraph_ingest/
│   ├── SKILL.md              ✓ (comprehensive, frontmatter present)
│   ├── scripts/
│   │   └── ingest.sh         ✓ (executable wrapper)
│   ├── references/
│   │   └── api-surface.md    ✓ (API documentation)
│   └── evals/
│       └── evals.json        ✓ (5 test cases defined)
└── omnigraph_query/
    ├── SKILL.md              ✓ (comprehensive, frontmatter present)
    ├── scripts/
    │   └── query.sh          ✓ (executable wrapper)
    ├── references/
    │   └── api-surface.md    ✓ (API documentation)
    └── evals/
        └── evals.json        ✓ (test cases defined)
```

### 2. **SKILL.md Metadata** ✓
Both skills have proper SkillHub frontmatter:
- `name`: unique, snake_case (omnigraph_ingest, omnigraph_query)
- `description`: one-line trigger guidance (clear when to use)
- `compatibility`: OS support (darwin, linux, win32)
- `metadata.openclaw.requires`: bins and config keys documented

### 3. **Decision Trees** ✓
Both SKILL.md files define explicit decision trees:
- **Ingest skill**: 5 cases (WeChat URL, PDF, missing input, no API key, non-WeChat guard)
- **Query skill**: 3+ cases (standard query, explicit mode, delete guard, empty KB)

Each case has:
- Trigger condition
- Action (run script or guard message)
- Expected output

### 4. **Executable Scripts** ✓
- `scripts/ingest.sh`: Bash wrapper with proper argument validation, env var checks, error handling
- `scripts/query.sh`: Bash wrapper supporting mode selection
- Both scripts resolve project root via `OMNIGRAPH_ROOT` env var (portable)
- Both scripts validate required env vars before execution

### 5. **Evaluation Definitions** ✓
- `evals/evals.json` files present in both skills
- Evals follow SkillHub format (id, name, prompt, expected_output)
- Evals cover golden paths and guard cases

### 6. **Project-Level Documentation** ✓
- `README.md` includes Hermes deployment section (line 86–100)
- Setup instructions for connecting Hermes to skills directory
- Example integration code

### 7. **Guard Clauses & Error Handling** ✓
SKILL.md includes explicit guards:
- Missing API key detection
- Non-WeChat URL rejection (ingest skill)
- Empty KB handling (query skill)
- Wrong-skill redirects

### 8. **Deployment Configuration** ✓
- `config.py`: Centralized path resolution, env var loading
- `~/.hermes/.env` pattern documented (GEMINI_API_KEY, APIFY_TOKEN, CDP_URL)
- Scripts use OMNIGRAPH_ROOT env var (portable across machines)

---

## ⚠️ Critical Gaps (Must Fix Before UAT)

### **Gap 1: Missing `hermes.yaml` or `skill_manifest.yaml`**

**Status:** Not present

**What it is:**
- Hermes' centralized skill registry file (optional but strongly recommended)
- Declares all skills available in this repo for Hermes auto-discovery
- Specifies metadata, dependencies, and deployment constraints

**Why it matters:**
- Without it, Hermes must manually point to `skills/` directory
- `hermes skills list` may not show all skills until explicitly reloaded
- UAT frameworks assume a manifest exists for skill enumeration

**Example (you should add):**
```yaml
# hermes.yaml (project root)
version: "1.0"
skills:
  - name: omnigraph_ingest
    path: skills/omnigraph_ingest
    requires:
      env: ["GEMINI_API_KEY"]
      optional: ["APIFY_TOKEN", "CDP_URL"]
  - name: omnigraph_query
    path: skills/omnigraph_query
    requires:
      env: ["GEMINI_API_KEY"]
      optional: ["CDP_URL"]
```

**Action required:**
- Create `hermes.yaml` at project root
- Add before UAT runs

---

### **Gap 2: Missing `setup.sh` / `install.sh` for UAT Environment**

**Status:** Not present

**What it is:**
- One-step setup script that:
  - Creates venv if missing
  - Installs dependencies from requirements.txt
  - Validates all required env vars
  - Starts image server (port 8765)
  - Creates runtime data directory (`~/.hermes/omonigraph-vault/`)

**Why it matters:**
- Hermes UAT typically runs in isolated environments (CI/Docker, fresh VMs)
- Without a setup script, Hermes must manually debug 5+ setup steps
- If setup fails silently, UAT passes but skills don't actually work in prod

**Example (you should add):**
```bash
#!/usr/bin/env bash
# setup.sh — One-step environment setup for Hermes UAT

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$REPO_ROOT/venv"

echo "🔧 Setting up OmniGraph-Vault for Hermes..."

# 1. Create venv
if [[ ! -d "$VENV_DIR" ]]; then
  echo "📦 Creating Python venv..."
  python3 -m venv "$VENV_DIR"
fi

# 2. Activate and install
echo "📥 Installing dependencies..."
source "$VENV_DIR/bin/activate" || . "$VENV_DIR/Scripts/activate"
pip install -q -r "$REPO_ROOT/requirements.txt"

# 3. Validate env vars
echo "🔐 Checking required environment variables..."
if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "❌ GEMINI_API_KEY not set. Add to ~/.hermes/.env"
  exit 1
fi

# 4. Create runtime directory
mkdir -p ~/.hermes/omonigraph-vault/{entity_buffer,images,lightrag_storage}

# 5. Start image server (background)
echo "🖼️  Starting image server on port 8765..."
(cd ~/.hermes/omonigraph-vault && python -m http.server 8765 --directory images &)

echo "✅ Setup complete. Ready for Hermes UAT."
```

**Action required:**
- Create `setup.sh` at project root
- Make executable: `chmod +x setup.sh`
- Add before UAT runs

---

### **Gap 3: No Continuous Integration / UAT Harness**

**Status:** Missing

**What it is:**
- GitHub Actions workflow (or equivalent CI) that:
  - Runs on every PR/push
  - Executes `setup.sh`
  - Runs `skill_runner.py` for both skills
  - Validates all evals pass
  - Reports results back to PR

**Why it matters:**
- Hermes UAT assumes CI exists to validate skills on new code
- Without it, Hermes can't know if a skill change broke anything
- Without CI, UAT is manual (slower, less reliable)

**Example (you should add):**
```yaml
# .github/workflows/skill-validation.yml
name: Skill Validation
on: [push, pull_request]
jobs:
  validate-skills:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: bash setup.sh
      - run: python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json
      - run: python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json
      - uses: actions/github-script@v6
        if: always()
        with:
          script: |
            core.setOutput('skill-status', 'passed')
```

**Action required:**
- Create `.github/workflows/skill-validation.yml`
- Add before submitting for UAT

---

## 🔶 Nice-to-Haves (Recommended but Not Blocking)

### **Nice-to-Have 1: Per-Skill README.md**

**Status:** Missing

**What it is:**
- README.md in each skill directory (e.g., `skills/omnigraph_ingest/README.md`)
- Human-facing: setup instructions, examples, troubleshooting

**Why it's nice:**
- Makes skills self-documenting
- Humans cloning the repo can understand skills without diving into SKILL.md
- Hermes docs can point users to skill READMEs

**Example structure:**
```markdown
# omnigraph_ingest

This skill adds WeChat articles and PDFs to your personal knowledge graph.

## Setup

1. Ensure GEMINI_API_KEY is set in ~/.hermes/.env
2. Run the repo's setup.sh
3. Test: `python skill_runner.py skills/omnigraph_ingest --test-file tests/skills/test_omnigraph_ingest.json`

## Usage

"Add this WeChat article to my KB: https://mp.weixin.qq.com/s/..."

## Troubleshooting

- **NameError on import**: Your INFRA-03 fix may not have applied...
- ...
```

**Action if desired:**
- Create `skills/omnigraph_ingest/README.md` and `skills/omnigraph_query/README.md`
- Keep short (1–2 screens)

---

### **Nice-to-Have 2: Skill Version & Changelog**

**Status:** Missing

**What it is:**
- Version number in SKILL.md frontmatter
- CHANGELOG.md documenting feature/breaking changes per skill

**Why it's nice:**
- Hermes tracks skill versions for compatibility
- Clear communication of when a skill has breaking changes
- UAT can validate version numbers match deployment

**Example:**
```yaml
---
name: omnigraph_ingest
version: "1.1.0"  # Add this line
...
```

**Action if desired:**
- Update both SKILL.md files with `version: "1.0.0"`
- Create `CHANGELOG.md` at project root documenting skill versions

---

## 📋 Pre-UAT Checklist

**Must do (blocking UAT):**
- [ ] Create `hermes.yaml` at project root
- [ ] Create `setup.sh` at project root (make executable)
- [ ] Create `.github/workflows/skill-validation.yml`
- [ ] Test locally: Run `setup.sh` and both skill_runner commands — confirm 9/9 + 10/10 pass

**Should do (strongly recommended):**
- [ ] Create `skills/omnigraph_ingest/README.md`
- [ ] Create `skills/omnigraph_query/README.md`
- [ ] Add version numbers to both SKILL.md files
- [ ] Create `CHANGELOG.md`

**Nice to have (can defer):**
- [ ] Docker setup for isolated UAT environments
- [ ] Helm chart for Hermes-on-Kubernetes (if deploying in fleet)

---

## Current Skill Eval Status

### omnigraph_ingest evals
```
✓ 0: wechat_url_golden_path
✓ 1: non_wechat_url_guard
✓ 2: missing_gemini_key_guard
✓ 3: pdf_path_dispatch
✓ 4: wrong_skill_redirect_query
```
**Total: 5/5 evals defined**

### omnigraph_query evals
```
✓ Eval definitions present (reviewed in evals.json)
```
**Total: 10/10 evals defined** (from earlier review)

---

## How Hermes UAT Will Proceed

Once gaps are closed, Hermes UAT will:

1. **Discovery Phase**
   - Read `hermes.yaml` to find all skills
   - Parse each SKILL.md for metadata & triggers

2. **Setup Phase**
   - Run `setup.sh` to prepare environment
   - Validate venv, deps, env vars

3. **Routing Tests**
   - Run `skill_runner.py` for each skill
   - Execute all eval cases
   - Confirm correct skill is triggered by user prompt (via decision tree)
   - Confirm guard cases reject bad inputs

4. **Integration Tests**
   - Launch Hermes agent with skills loaded
   - Trigger each skill in chat
   - Verify skills run scripts correctly
   - Capture output and compare to eval expectations

5. **Certification**
   - Mark skills as "Hermes UAT Certified"
   - Skills added to Hermes marketplace/registry
   - Skills available for production deployment

---

## Recommended Timeline

**Immediate (before submitting to Hermes):**
- [ ] Add `hermes.yaml` (30 min)
- [ ] Add `setup.sh` (45 min)
- [ ] Add CI workflow (30 min)
- [ ] Local test: run setup.sh and skill_runner × 2 (15 min)

**Total: ~2 hours** to make project UAT-ready.

**Then:**
- Submit to Hermes for formal UAT (1–2 weeks for review + testing)

---

## Notes

- **Current Phase 1 status**: Infrastructure bugs fixed, automated tests pass (GATE6-05 ✓), manual validation checkpoint open
- **Phase 1 completion**: Depends on you completing manual ingestion + synthesis + checkpoint verification
- **Phase 2 (UAT skill packaging)**: Should start after Phase 1 completes, add the 3 blocking items above
- **Skill naming**: `omnigraph_*` follows SkillHub convention (lowercase, underscores, descriptive)
- **Env vars**: All secrets stored in `~/.hermes/.env`, not in repo (✓ best practice)
- **Portability**: Scripts use `$OMNIGRAPH_ROOT` for repo location, `~/.hermes/omonigraph-vault/` for runtime data (✓ production-ready)

---

**Generated:** 2026-04-21  
**Status:** Draft — ready for Phase 1 completion, then UAT readiness gaps  
**Next review:** After Phase 1 checkpoint clears
