# SkillHub-Ready Skill Development Requirements

## Overview

This document specifies all requirements for creating production-grade OpenClaw/Hermes skills suitable for SkillHub distribution. It is written for LLM agents building complete skills end-to-end.

---

## 1. Skill Structure

### Directory Layout

```
skill-name/
├── SKILL.md                    # Required. Frontmatter + instructions
├── LICENSE.txt                 # Required if proprietary or specific license
├── scripts/                    # Optional. Python scripts for deterministic tasks
│   ├── __init__.py            # Empty or utility imports
│   ├── main_script.py         # Named by function: extract_text.py, process_data.py
│   ├── utils.py               # Shared utilities across scripts
│   └── llm_interface.py        # Model abstraction layer
├── references/                 # Optional. Reference docs loaded on demand
│   ├── framework_guide.md      # Large docs (>300 lines) go here
│   ├── api_reference.md
│   └── faq.md
└── assets/                     # Optional. Templates, fonts, icons used in output
    ├── template.docx
    └── icon.svg
```

### Progressive Disclosure Rules

- **Metadata (100 words)**: Skill name + description. Always in context.
- **SKILL.md body (≤500 lines)**: Loaded when skill triggers. Use clear hierarchy with headers and pointers to `references/`.
- **Bundled resources**: Loaded on demand via explicit instruction in SKILL.md. E.g., "See `references/api_reference.md` for details on the X API."

If SKILL.md approaches 500 lines, reorganize: keep common use cases inline, move edge cases to `references/`, and provide clear navigation paths.

---

## 2. SKILL.md Format and Content

### Frontmatter (YAML)

```yaml
---
name: skill-identifier
description: |
  Clear statement of WHAT and WHEN. Include:
  - The main task this skill enables
  - Specific trigger phrases and contexts
  - Edge cases it handles
  - Edge cases it does NOT handle (use "Do NOT use when...")
  Make description "pushy" to counter undertriggering.
compatibility: |
  Optional. List required tools, APIs, or external services.
  E.g., "Requires: Anthropic API, Python 3.10+, libmagic"
license: Proprietary. See LICENSE.txt
---
```

### Frontmatter Rules

1. **name**: Alphanumeric + hyphens only. Matches directory name. E.g., `docx`, `pdf-reading`, `model-router`.
2. **description**: 100–200 words.
   - Start with: "Use this skill when [user action] to [outcome]."
   - Include: "This skill handles [edge case 1], [edge case 2]."
   - Include: "Do NOT use for [adjacent task 1], [adjacent task 2]."
   - Rationale: Claude's tendency to undertrigger requires explicit "when to use" statements. Near-miss exclusions (things that sound similar but belong to other skills) are crucial.
3. **compatibility**: Only if external dependencies matter. E.g., API keys, OS requirements, non-standard libraries.
4. **license**: State license here or point to LICENSE.txt if detailed.

### Body Content

Structure the body with clear headings and a consistent voice.

#### Pattern 1: Quick Reference

For skills with a clear, repeatable workflow:

```markdown
## Quick Reference

| Task | When | How |
|------|------|-----|
| Create a new document | User wants a .docx file | Use `python scripts/create_docx.py --template ...` |
| Edit existing content | User has a .docx and wants changes | Unpack → modify XML → repack |
| Extract text | User wants text from .docx | Run `extract-text document.docx` |
```

#### Pattern 2: Overview + Step-by-Step

For multi-step workflows:

```markdown
## Overview

This skill enables [core capability]. It works by:
1. [High-level step 1 with rationale]
2. [High-level step 2 with rationale]
3. [High-level step 3 with rationale]

## When to Use

- [Specific use case 1]
- [Specific use case 2]
- [NOT suitable for: specific use case 3 — use [other skill] instead]

## Key Concepts

[Explain the why behind 1–2 technical concepts. Use theory of mind to convey understanding to the model.]

## Workflow

### [Subtask 1 name]

[Detailed steps with commands, code snippets, and examples]

### [Subtask 2 name]

[Detailed steps]
```

#### Pattern 3: Reference with Examples

For tools with many modes:

```markdown
## Overview

[One-sentence description]

## Common Tasks

### Task A
[Brief intro]
```bash
[command]
```
**Output**: [description]

### Task B
[Brief intro]
```bash
[command]
```
**Output**: [description]

## Advanced

[Less common but important edge cases. Point to `references/` if very detailed.]
```

### Output Format Templates

Always include an "Output Format" or "Report Structure" section for any task that produces user-facing output:

```markdown
## Report Structure

ALWAYS use this exact template when outputting analysis:

# [Title]

## Executive Summary
[1–2 sentences: what was found]

## Key Findings
[Bullet points with evidence]

## Recommendations
[Numbered list with rationale]
```

### Input/Output Examples

Include 1–2 realistic examples for each major task:

```markdown
## Example: Extracting Text from a PDF

**Input**: A PDF file containing a 10-page technical report.

**Command**:
```bash
python scripts/extract_text.py --input report.pdf --output report.txt --preserve-formatting
```

**Output**: A plaintext file with markdown-style formatting preserved (bold → `**bold**`, headers → `# Header`).

---

## Example: Creating a Docx Template

**Input**: A folder with brand colors, a header image, and a style guide.

**Command**:
```bash
python scripts/create_docx.py --template brand/ --style formal --output report.docx
```

**Output**: A .docx file ready for the user to fill in content.
```

### Pointers to scripts/ and references/

For any non-trivial operation, explicitly tell the model how to use bundled scripts:

```markdown
### Editing an Existing Document

To modify content:

1. Run the unpack script (see `scripts/unpack.py --help` for options):
   ```bash
   python scripts/unpack.py input.docx output_folder/
   ```

2. Edit the XML files in `output_folder/word/document.xml`

3. Run the repack script:
   ```bash
   python scripts/repack.py output_folder/ output.docx
   ```

For detailed XML structure, see `references/docx_xml_guide.md`.
```

### Writing Style

- Use **imperative form**: "Extract the text." not "The skill extracts the text."
- **Explain the why**: "We unpack the .docx because it's a ZIP containing XML files; modifying the XML directly is faster than using the Office SDK." — This helps the model understand constraints and make good decisions.
- **Avoid vague MUSTs**: Instead of "ALWAYS validate input", write "Validate input to catch encoding errors early, which prevents downstream XML parsing failures."
- **Be specific about edge cases**: Not "Handle large files", but "For files >100MB, stream processing prevents memory exhaustion."
- **Theory of mind**: Assume the model understands CS fundamentals (processes, APIs, data formats). Use that to explain *why* the workflow is structured the way it is.

### Length Guidelines

Keep SKILL.md under 500 lines. If you're exceeding this:

1. Move large reference sections (API docs, full examples, troubleshooting tables) to `references/`.
2. Keep only the "what you need to know" inline with clear pointers outward.
3. Use a table of contents at the top if there are >5 major sections.

---

## 3. Python Scripts: Structure and Patterns

### Script Location and Naming

All Python scripts live in `scripts/` and are named by function, not generic names:

- ✅ `scripts/extract_text.py`, `scripts/create_docx.py`, `scripts/process_csv.py`
- ❌ `scripts/main.py`, `scripts/utils.py`, `scripts/helper.py`

`utils.py` is allowed only for truly shared utilities. If a script is substantial enough to warrant a file, give it a name that describes its output or primary action.

### CLI Interface

Every script must:

1. **Accept paths via flags, not stdin**:
   ```python
   import argparse
   
   parser = argparse.ArgumentParser(description="Extract text from PDF")
   parser.add_argument("--input", required=True, help="Path to input PDF")
   parser.add_argument("--output", required=True, help="Path to output text file")
   parser.add_argument("--model", default="claude-opus-4-6", help="LLM model to use")
   parser.add_argument("--verbose", action="store_true", help="Enable debug output")
   
   args = parser.parse_args()
   ```

2. **Output progress to stdout, errors to stderr**:
   ```python
   import sys
   
   print("Processing document...", file=sys.stdout)
   print("ERROR: File not found", file=sys.stderr)
   sys.exit(1)
   ```

3. **Exit cleanly**:
   ```python
   if success:
       print("✓ Complete")
       sys.exit(0)
   else:
       print("✗ Failed: [reason]", file=sys.stderr)
       sys.exit(1)
   ```

4. **Avoid input() calls**: Scripts run in automated pipelines; interactive prompts break workflows. Use defaults or `--input` flags instead.

### Environment and Secrets

**Never hardcode API keys, paths, or credentials.**

1. **Use environment variables**:
   ```python
   import os
   from dotenv import load_dotenv
   
   load_dotenv()  # Load from .env if present
   
   api_key = os.environ.get("ANTHROPIC_API_KEY")
   if not api_key:
       print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
       sys.exit(1)
   
   model_name = os.environ.get("LLM_MODEL", "claude-opus-4-6")  # Fallback default
   ```

2. **Accept critical config as CLI flags** (for easy overrides in CI):
   ```python
   parser.add_argument("--api-key", help="API key (default: $ANTHROPIC_API_KEY)")
   if args.api_key:
       api_key = args.api_key
   ```

3. **Document required env vars in a comment**:
   ```python
   """
   Extract text from PDF using Claude.
   
   Required env vars:
   - ANTHROPIC_API_KEY
   
   Optional env vars:
   - LLM_MODEL (default: claude-opus-4-6)
   - DEBUG (set to 1 to enable verbose logging)
   """
   ```

### LLM Model Abstraction Layer

**Do not embed model-specific SDK calls throughout your scripts.** Create a single abstraction layer so Deepseek, Gemini, and Claude can be swapped without touching pipeline logic.

#### Pattern: LLM Interface Class

```python
# scripts/llm_interface.py

import anthropic
import google.generativeai as genai
import os

class LLMInterface:
    """Model-agnostic LLM interface."""
    
    def __init__(self, provider: str = "anthropic", model: str = None):
        self.provider = provider
        if provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
            self.model = model or "claude-opus-4-6"
        elif provider == "google":
            genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
            self.model = model or "gemini-2.0-flash"
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def call(self, prompt: str, system: str = "", temperature: float = 0.7) -> str:
        """Call the LLM and return text response."""
        if self.provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        elif self.provider == "google":
            model = genai.GenerativeModel(self.model, system_instruction=system)
            response = model.generate_content(prompt)
            return response.text
    
    def count_tokens(self, text: str) -> int:
        """Return approximate token count."""
        if self.provider == "anthropic":
            # Approximate: 1 token ≈ 4 chars
            return len(text) // 4
        elif self.provider == "google":
            model = genai.GenerativeModel(self.model)
            return model.count_tokens(text).total_tokens

# Usage in a script:
if __name__ == "__main__":
    llm = LLMInterface(provider="anthropic")
    result = llm.call(prompt="Summarize: ...", system="You are a helpful assistant")
    print(result)
```

Use this in all scripts that call an LLM:

```python
from llm_interface import LLMInterface

llm = LLMInterface()
analysis = llm.call(
    prompt=f"Analyze this data: {data}",
    system="You are a data analyst."
)
```

### Dependencies

**Use `requirements.txt` or `pyproject.toml` to declare all dependencies.**

#### requirements.txt

```txt
anthropic>=0.25.0
python-dotenv>=1.0.0
pandas>=2.0.0
pydantic>=2.0.0
```

Pin major versions, allow patch updates. Avoid `>=` for pre-release versions (unstable APIs).

#### pyproject.toml

```toml
[project]
name = "skill-scripts"
version = "1.0.0"
dependencies = [
    "anthropic>=0.25.0",
    "python-dotenv>=1.0.0",
    "pandas>=2.0.0",
]

[build-system]
requires = ["setuptools", "wheel"]
build-backend = "setuptools.build_meta"
```

Include a setup section if the skill has a `__main__` entrypoint users will call directly.

### Script Quality Standards

1. **Single responsibility**: One script = one main output or transformation. Shared logic → `utils.py`.
2. **Idempotent where possible**: Re-running the same script with the same inputs should be safe. If it creates output, check for existing output and warn/skip or use `--force` flag.
3. **Clear error messages**: When something fails, print `ERROR: [what], why it happened, [how to fix]`. Not just `Error: KeyError: 'x'`.
4. **Logging in verbose mode**:
   ```python
   if args.verbose:
       print(f"DEBUG: Processing {len(items)} items", file=sys.stderr)
   ```
5. **No external prints except progress**: Don't print debug info, only the final result or structured progress.

---

## 4. Evaluation Suite (Evals)

### Structure

Create an `evals/` directory with:

```
evals/
├── evals.json              # Test case definitions
├── iteration-1/            # Results from first test run
│   ├── eval-0/
│   │   ├── with_skill/
│   │   │   └── outputs/
│   │   ├── without_skill/
│   │   │   └── outputs/
│   │   └── eval_metadata.json
│   └── ...
└── benchmark.json          # Aggregated results with timing/tokens
```

### evals.json Schema

```json
{
  "skill_name": "docx",
  "evals": [
    {
      "id": 0,
      "name": "create_formal_report",
      "prompt": "Create a formal project status report using a template",
      "expected_output": "A .docx file with title, executive summary, and action items sections filled in",
      "files": []
    },
    {
      "id": 1,
      "name": "extract_and_analyze",
      "prompt": "Extract text from this PDF and summarize the key findings",
      "expected_output": "Plaintext with markdown formatting, organized by section",
      "files": ["sample_report.pdf"]
    }
  ]
}
```

### Assertions

Each test case should have verifiable assertions in `eval_metadata.json`:

```json
{
  "eval_id": 0,
  "eval_name": "create_formal_report",
  "prompt": "Create a formal project status report using a template",
  "assertions": [
    {
      "text": "Output is a valid .docx file",
      "passed": true,
      "evidence": "File exists and opens in Python-docx without error"
    },
    {
      "text": "Document contains executive summary section",
      "passed": true,
      "evidence": "Paragraph text includes 'Executive Summary' heading"
    },
    {
      "text": "Report has at least 3 pages of content",
      "passed": false,
      "evidence": "Document contains only 1 page of boilerplate"
    }
  ]
}
```

### Assertion Field Names

Use exactly these field names (required by benchmark viewer):
- `text`: What the assertion checks (e.g., "Output contains no errors")
- `passed`: Boolean
- `evidence`: Explanation of why it passed or failed

---

## 5. Safety and Compliance

### Mandatory Checks

1. **No malware or exploit code**: Scripts must not attempt unauthorized access, data exfiltration, or system compromise.
2. **Intent matches description**: If the skill description says "Extract text from PDFs", the actual behavior must be extracting text. No hidden side effects.
3. **No undocumented capabilities**: If a script can delete files, that must be explicit in SKILL.md and CLI help text.
4. **Secure defaults**: 
   - Don't create world-readable files by default (use `mode=0o600` for sensitive outputs)
   - Don't log sensitive data (API keys, auth tokens, user data) unless `--verbose` is explicitly set
   - Don't make unnecessary network calls

### Data Privacy

- If the skill processes user data (PDFs, spreadsheets, etc.), document whether it:
  - Stays local (processed entirely in scripts/)
  - Sends to third-party APIs (disclose which services, e.g., "Uses Claude API")
  - Caches intermediate results (disclose retention policy)
- Include a privacy note in SKILL.md if processing user documents.

---

## 6. Description Optimization

### Trigger Eval Set

Before submitting to SkillHub, optimize the description via a trigger eval loop:

1. **Create 20 test queries** (mix of should-trigger and should-not-trigger):
   ```json
   [
     {"query": "I need to extract tables from a PDF and turn them into Excel", "should_trigger": true},
     {"query": "Write me a haiku about PDFs", "should_trigger": false},
     {"query": "My company needs to convert all our old .doc files to .docx", "should_trigger": true},
     {"query": "What's the difference between PDF and JPEG?", "should_trigger": false}
   ]
   ```

   - Should-trigger queries: Use specific context (file names, company names, URLs).
   - Should-not-trigger queries: Adjacent domains or near-misses that would mislead keyword matching.

2. **Run the optimization loop**:
   ```bash
   python -m scripts.run_loop \
     --eval-set trigger-eval.json \
     --skill-path skill-name/ \
     --model claude-opus-4-6 \
     --max-iterations 5 \
     --verbose
   ```

3. **Apply the best description** from the output JSON's `best_description` field to `SKILL.md` frontmatter.

The goal: maximize trigger rate on held-out test queries (40% of the eval set), not train queries (60%), to avoid overfitting.

---

## 7. Packaging for SkillHub

### Pre-Packaging Checklist

- [ ] SKILL.md frontmatter has all required fields (name, description)
- [ ] SKILL.md body ≤500 lines (use references/ for overflow)
- [ ] All scripts have CLI interface (--input, --output, --help)
- [ ] requirements.txt or pyproject.toml declares all dependencies
- [ ] LLM calls go through abstraction layer (llm_interface.py)
- [ ] No hardcoded API keys or paths
- [ ] Eval suite in evals/ with ≥2 test cases and assertions
- [ ] Description optimized via trigger eval loop
- [ ] README.md in repo root (not in skill/) explains how to run evals and tests
- [ ] LICENSE.txt if proprietary
- [ ] No trailing whitespace or linter errors

### Package Command

```bash
python -m scripts.package_skill skill-name/
```

This outputs `skill-name.skill` — a binary package containing the skill directory, all scripts, references, and metadata. This file is distributed on SkillHub.

---

## 8. Common Pitfalls

### 1. Description Under-Triggers

**Problem**: Skill description is too vague. Model rarely uses it.

**Fix**: Include explicit "when to use" statements in the description. List 3–5 specific trigger phrases. Include "Do NOT use for X" to help with near-miss exclusion.

Bad: "Skill for working with PDFs."
Good: "Use this skill when extracting text from PDFs, splitting multi-page documents, or merging multiple PDFs. Triggers include: 'extract tables', 'convert PDF to Excel', 'merge PDF files'. Do NOT use for creating PDFs from scratch — use the docx skill instead."

### 2. Scripts with Unclear Dependencies

**Problem**: Script assumes packages are installed globally or in a virtual environment the caller doesn't have.

**Fix**: Always declare dependencies in requirements.txt. Always accept paths via CLI flags, not hardcoded paths like `/home/user/data/input.txt`.

### 3. LLM Calls Hardcoded to One Provider

**Problem**: Script uses `anthropic.Anthropic()` directly throughout, making it impossible to swap providers.

**Fix**: Create an `llm_interface.py` abstraction. All LLM calls go through it.

### 4. Assertions That Are Vague or Subjective

**Problem**: "Output quality is good" (cannot verify objectively).

**Fix**: Use assertions that can be programmatically checked: file exists, contains specific keywords, no errors in stderr, execution time <10s.

### 5. SKILL.md That Reads Like a Manual

**Problem**: 1000 lines of prose. Model gets lost in details.

**Fix**: Keep SKILL.md focused on "what the skill does" and "how to use the bundled scripts". Move API docs, full tutorials, and verbose examples to `references/`.

---

## 9. Example Minimal Skill

Here's a complete, minimal skill to use as a template:

### Directory

```
hello-skill/
├── SKILL.md
├── LICENSE.txt
├── scripts/
│   ├── __init__.py
│   └── greet.py
└── evals/
    └── evals.json
```

### SKILL.md

```yaml
---
name: hello-skill
description: |
  Use this skill when the user wants to generate personalized greetings or 
  motivational messages using an LLM. It generates text files with formatted 
  output. Do NOT use for translations, content creation beyond greetings, 
  or image generation.
---

# Hello Skill

## Overview

This skill generates personalized greetings and motivational messages using Claude.

## Quick Start

```bash
python scripts/greet.py --input "Alice" --output greeting.txt --tone warm
```

**Output**: A text file containing a personalized greeting.

## Usage

Run the greeting script:

```bash
python scripts/greet.py \
  --input "Name" \
  --output output.txt \
  --tone [warm|professional|casual] \
  --model claude-opus-4-6
```

### Environment

Set `ANTHROPIC_API_KEY` to your API key.
```

### scripts/greet.py

```python
#!/usr/bin/env python3
"""Generate personalized greetings using Claude."""

import argparse
import os
import sys
from llm_interface import LLMInterface

def main():
    parser = argparse.ArgumentParser(description="Generate a personalized greeting")
    parser.add_argument("--input", required=True, help="Name or subject for greeting")
    parser.add_argument("--output", required=True, help="Path to output text file")
    parser.add_argument("--tone", default="warm", choices=["warm", "professional", "casual"])
    parser.add_argument("--model", default="claude-opus-4-6", help="LLM model to use")
    parser.add_argument("--verbose", action="store_true")
    
    args = parser.parse_args()
    
    # Initialize LLM
    llm = LLMInterface(provider="anthropic", model=args.model)
    
    # Generate greeting
    if args.verbose:
        print(f"Generating {args.tone} greeting for {args.input}", file=sys.stderr)
    
    prompt = f"Write a {args.tone} greeting for {args.input}. Keep it to 2–3 sentences."
    greeting = llm.call(prompt)
    
    # Write output
    with open(args.output, "w") as f:
        f.write(greeting)
    
    print(f"✓ Greeting written to {args.output}")
    sys.exit(0)

if __name__ == "__main__":
    main()
```

### scripts/llm_interface.py

(See Section 3 for full implementation)

### evals/evals.json

```json
{
  "skill_name": "hello-skill",
  "evals": [
    {
      "id": 0,
      "name": "warm_greeting",
      "prompt": "Generate a warm greeting for Alice",
      "expected_output": "A friendly, personalized greeting mentioning Alice by name",
      "files": []
    }
  ]
}
```

---

## 10. Checklist for LLM Agents

When building a skill, follow this checklist in order:

### Phase 1: Design
- [ ] Define what the skill does (1 sentence)
- [ ] List trigger phrases (3–5 specific contexts)
- [ ] List what NOT to do (2–3 adjacent tasks)
- [ ] Identify required scripts (what will be automated?)
- [ ] Identify required references (what docs are too long for SKILL.md?)

### Phase 2: Implement
- [ ] Create directory structure
- [ ] Write SKILL.md frontmatter (name, description)
- [ ] Write SKILL.md body with Overview, Quick Reference, Examples
- [ ] Create each script with CLI interface (--input, --output, --help)
- [ ] Create llm_interface.py with model abstraction
- [ ] Create requirements.txt
- [ ] Create 1–2 reference docs if needed

### Phase 3: Evaluate
- [ ] Create evals/evals.json with 2–3 test cases
- [ ] Run test cases manually
- [ ] Create eval_metadata.json files with assertions
- [ ] Verify assertions are objective and verifiable
- [ ] Document results in benchmark.json

### Phase 4: Optimize
- [ ] Create trigger eval set (20 queries)
- [ ] Run description optimization loop
- [ ] Update SKILL.md description with best result
- [ ] Verify description triggers on realistic prompts

### Phase 5: Package
- [ ] Review safety checklist (no malware, intent clear, secure defaults)
- [ ] Verify all dependencies declared
- [ ] Run package_skill.py to generate .skill file
- [ ] Create README.md in repo root (not skill/) explaining how to test
- [ ] Tag release in git

---

## 11. Reference: Script Template

Use this template for all new scripts:

```python
#!/usr/bin/env python3
"""
[One-line description of what this script does]

Required env vars:
  - ANTHROPIC_API_KEY

Optional env vars:
  - LLM_MODEL (default: claude-opus-4-6)

Example:
  python scripts/[script_name].py --input data.txt --output result.txt
"""

import argparse
import os
import sys
from pathlib import Path
from llm_interface import LLMInterface

def main():
    parser = argparse.ArgumentParser(
        description="[Longer description of functionality]"
    )
    parser.add_argument("--input", required=True, help="Path to input [file type]")
    parser.add_argument("--output", required=True, help="Path to output [file type]")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "claude-opus-4-6"))
    parser.add_argument("--verbose", action="store_true", help="Enable debug output")
    
    args = parser.parse_args()
    
    # Validate inputs
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Initialize LLM
    try:
        llm = LLMInterface(provider="anthropic", model=args.model)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Main logic
    if args.verbose:
        print(f"Processing {args.input}...", file=sys.stderr)
    
    try:
        # [Implementation]
        result = "..."
        
        # Write output
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as f:
            f.write(result)
        
        print(f"✓ Output written to {args.output}")
        sys.exit(0)
    
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## Appendix: Quick Links

- **Skill Creator Guide**: `/mnt/skills/examples/skill-creator/SKILL.md`
- **Example Public Skill**: `/mnt/skills/public/docx/SKILL.md`
- **Trigger Eval Optimization**: See Section 6 of this doc
- **Package Command**: `python -m scripts.package_skill skill-name/`
- **Run Evals**: `python -m scripts.run_evals evals/evals.json`
