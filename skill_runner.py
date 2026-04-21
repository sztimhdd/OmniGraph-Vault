#!/usr/bin/env python3
"""
skill_runner.py — Local Hermes skill simulator.

Loads SKILL.md as a system prompt and sends test inputs through Gemini —
the same LLM backend Hermes uses. No Hermes installation required.

Usage:
    # Single message (interactive exploration)
    python skill_runner.py skills/omnigraph_query "what do I know about LightRAG?"

    # Run a JSON test suite
    python skill_runner.py skills/omnigraph_query --test-file tests/skills/test_omnigraph_query.json

    # Run all test suites under skills/
    python skill_runner.py skills/ --test-all

    # Structure validation only (no API call)
    python skill_runner.py skills/omnigraph_ingest --validate
    python skill_runner.py skills/ --validate --test-all
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows cp1252 console can't print unicode box-drawing chars — force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config  # loads ~/.hermes/.env, sets GEMINI_API_KEY

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ── Colour helpers ────────────────────────────────────────────────────────────

_TTY = sys.stdout.isatty()
_GREEN = "\033[92m" if _TTY else ""
_RED   = "\033[91m" if _TTY else ""
_GREY  = "\033[90m" if _TTY else ""
_BOLD  = "\033[1m"  if _TTY else ""
_RESET = "\033[0m"  if _TTY else ""


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SkillDef:
    name: str
    description: str
    path: Path
    body: str
    requires_config: list[str] = field(default_factory=list)
    requires_bins: list[str] = field(default_factory=list)


@dataclass
class TestCase:
    description: str
    input: str
    expect_contains: list[str] = field(default_factory=list)
    expect_not_contains: list[str] = field(default_factory=list)
    load_references: list[str] = field(default_factory=list)


@dataclass
class TestResult:
    case: TestCase
    passed: bool
    response: str
    failures: list[str] = field(default_factory=list)


# ── Frontmatter parser ────────────────────────────────────────────────────────

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Split SKILL.md into (metadata dict, body string)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end].strip()
    body = text[end + 4:]
    if _HAS_YAML:
        meta = yaml.safe_load(raw) or {}
    else:
        # Minimal fallback: top-level scalar key: value pairs only
        meta: dict = {}
        for line in raw.splitlines():
            if ":" in line and not line.startswith(" "):
                k, _, v = line.partition(":")
                meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


# ── Skill loading ─────────────────────────────────────────────────────────────

def load_skill(skill_dir: Path) -> SkillDef:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"No SKILL.md found in {skill_dir}")
    text = skill_md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)
    openclaw = meta.get("metadata", {}) if isinstance(meta.get("metadata"), dict) else {}
    openclaw = openclaw.get("openclaw", {}) if isinstance(openclaw, dict) else {}
    requires = openclaw.get("requires", {}) if isinstance(openclaw, dict) else {}
    return SkillDef(
        name=meta.get("name", skill_dir.name),
        description=meta.get("description", ""),
        path=skill_dir,
        body=body.strip(),
        requires_config=requires.get("config", []) if isinstance(requires, dict) else [],
        requires_bins=requires.get("bins", []) if isinstance(requires, dict) else [],
    )


_SIMULATOR_PREAMBLE = """\
You are simulating a Hermes agent skill in a local test harness.
Respond with plain text only. Do NOT call any functions or tools.
When the skill instructions say to run a command (e.g. `python ingest_wechat.py`),
tell the user what command they should run -- do not attempt to execute it yourself.
"""


def _build_system_prompt(skill: SkillDef, load_references: list[str]) -> str:
    parts = [_SIMULATOR_PREAMBLE, skill.body]
    for ref_path in load_references:
        ref_file = skill.path / "references" / ref_path
        if ref_file.exists():
            parts.append(f"\n\n## Reference: {ref_path}\n\n{ref_file.read_text(encoding='utf-8')}")
        else:
            print(f"{_GREY}  warning: reference not found: references/{ref_path}{_RESET}", file=sys.stderr)
    return "\n\n".join(parts)


# ── Gemini call ───────────────────────────────────────────────────────────────

_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
_MAX_RETRIES = 3


def call_gemini(system_prompt: str, user_message: str) -> str:
    import time
    from google import genai
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set -- check ~/.hermes/.env")
    client = genai.Client(api_key=api_key)

    for attempt in range(_MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.1,
                    # Disable function calling so the model never tries to invoke tools.
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="NONE")
                    ),
                ),
                contents=user_message,
            )
        except Exception as exc:
            msg = str(exc)
            if "503" in msg and attempt < _MAX_RETRIES - 1:
                time.sleep(5 * (attempt + 1))
                continue
            raise

        if response.text is not None:
            return response.text
        if response.candidates:
            reason = response.candidates[0].finish_reason
            raise RuntimeError(f"Gemini returned no text (finish_reason={reason})")
        raise RuntimeError("Gemini returned empty response (no candidates)")

    raise RuntimeError(f"Gemini unavailable after {_MAX_RETRIES} retries")


# ── Test execution ────────────────────────────────────────────────────────────

def run_test_case(skill: SkillDef, case: TestCase) -> TestResult:
    system_prompt = _build_system_prompt(skill, case.load_references)
    try:
        response = call_gemini(system_prompt, case.input)
    except Exception as exc:
        return TestResult(case=case, passed=False, response="", failures=[f"API error: {exc}"])

    failures: list[str] = []
    response_lower = response.lower()
    for expected in case.expect_contains:
        if expected.lower() not in response_lower:
            failures.append(f"expected to contain: '{expected}'")
    for forbidden in case.expect_not_contains:
        if forbidden.lower() in response_lower:
            failures.append(f"expected NOT to contain: '{forbidden}'")
    return TestResult(case=case, passed=not failures, response=response, failures=failures)


def run_test_file(skill: SkillDef, test_file: Path) -> list[TestResult]:
    raw = json.loads(test_file.read_text(encoding="utf-8"))
    cases = [TestCase(**c) for c in raw]
    return [run_test_case(skill, case) for case in cases]


# ── Structure validation ──────────────────────────────────────────────────────

def validate_skill(skill_dir: Path) -> list[str]:
    """Returns list of validation errors; empty list means pass."""
    errors: list[str] = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"SKILL.md missing in {skill_dir}"]
    text = skill_md.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(text)

    if not meta.get("name"):
        errors.append("frontmatter missing required field: name")
    elif not str(meta["name"]).replace("_", "").isalnum():
        errors.append(f"name '{meta['name']}' must be snake_case alphanumeric")

    if not meta.get("description"):
        errors.append("frontmatter missing required field: description")

    if not body.strip():
        errors.append("body is empty — no instructions written")

    # references/ — check that files referenced in body actually exist
    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        for ref_file in refs_dir.iterdir():
            if ref_file.name not in body:
                errors.append(f"references/{ref_file.name} exists but is not mentioned in SKILL.md body")

    # scripts/ — syntax check
    scripts_dir = skill_dir / "scripts"
    if scripts_dir.exists():
        for script in scripts_dir.iterdir():
            if script.suffix == ".sh":
                r = subprocess.run(["bash", "-n", str(script)], capture_output=True)
                if r.returncode != 0:
                    errors.append(f"scripts/{script.name}: bash syntax error — {r.stderr.decode().strip()}")
            elif script.suffix == ".py":
                r = subprocess.run([sys.executable, "-m", "py_compile", str(script)], capture_output=True)
                if r.returncode != 0:
                    errors.append(f"scripts/{script.name}: Python syntax error — {r.stderr.decode().strip()}")

    return errors


# ── Print helpers ─────────────────────────────────────────────────────────────

def _print_result(result: TestResult, verbose: bool) -> None:
    icon = f"{_GREEN}PASS{_RESET}" if result.passed else f"{_RED}FAIL{_RESET}"
    print(f"  {icon} {result.case.description}")
    if not result.passed:
        for failure in result.failures:
            print(f"      {_RED}{failure}{_RESET}")
        if verbose:
            preview = result.response[:400].replace("\n", " ")
            print(f"      {_GREY}response: {preview}...{_RESET}")


def _print_summary(results: list[TestResult]) -> int:
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    colour = _GREEN if passed == total else _RED
    print(f"\n  {colour}{passed}/{total} passed{_RESET}")
    return 0 if passed == total else 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local Hermes skill simulator — no Hermes installation required",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("skill_path", help="Skill directory, or parent directory when using --test-all")
    parser.add_argument("message", nargs="?", help="Single message to send (interactive mode)")
    parser.add_argument("--test-file", metavar="FILE", help="Path to JSON test case file")
    parser.add_argument("--test-all", action="store_true",
                        help="Run all test suites found under tests/skills/")
    parser.add_argument("--validate", action="store_true",
                        help="Structural validation only — no API calls")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show LLM response snippet on failure")
    args = parser.parse_args()

    skill_path = Path(args.skill_path)
    all_results: list[TestResult] = []
    failed_validations = 0

    # ── validate mode ────────────────────────────────────────────────────────
    if args.validate:
        targets = (
            [d for d in sorted(skill_path.iterdir()) if d.is_dir()]
            if args.test_all
            else [skill_path]
        )
        for target in targets:
            if not (target / "SKILL.md").exists():
                continue
            errors = validate_skill(target)
            skill_name = target.name
            if errors:
                print(f"{_RED}FAIL{_RESET} {_BOLD}{skill_name}{_RESET}")
                for err in errors:
                    print(f"  {_RED}x{_RESET} {err}")
                failed_validations += 1
            else:
                print(f"{_GREEN}PASS{_RESET} {_BOLD}{skill_name}{_RESET}")
        return 1 if failed_validations else 0

    # ── --test-all mode ──────────────────────────────────────────────────────
    if args.test_all:
        tests_root = Path("tests") / "skills"
        for skill_dir in sorted(skill_path.iterdir()):
            if not (skill_dir / "SKILL.md").exists():
                continue
            test_file = tests_root / f"test_{skill_dir.name}.json"
            if not test_file.exists():
                print(f"{_GREY}SKIP{_RESET} {skill_dir.name}  (no test file at {test_file})")
                continue
            skill = load_skill(skill_dir)
            print(f"\n{_BOLD}{skill.name}{_RESET}")
            results = run_test_file(skill, test_file)
            for result in results:
                _print_result(result, args.verbose)
            all_results.extend(results)
        return _print_summary(all_results)

    # ── single-skill modes ───────────────────────────────────────────────────
    skill = load_skill(skill_path)

    if args.test_file:
        print(f"\n{_BOLD}{skill.name}{_RESET}")
        results = run_test_file(skill, Path(args.test_file))
        for result in results:
            _print_result(result, args.verbose)
        return _print_summary(results)

    if args.message:
        system_prompt = _build_system_prompt(skill, [])
        response = call_gemini(system_prompt, args.message)
        print(response)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
