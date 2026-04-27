---
phase: 04-knowledge-enrichment-zhihu
plan: 02
type: execute
wave: 2
depends_on: [04-00]
files_modified:
  - enrichment/__init__.py
  - enrichment/extract_questions.py
  - tests/unit/test_extract_questions.py
autonomous: true
requirements: [D-03, D-12]
must_haves:
  truths:
    - "extract_questions.py exists in the enrichment/ package"
    - "CLI invocation: python -m enrichment.extract_questions <article_md_path> [--hash <hash>]"
    - "Uses Gemini 2.5 Flash Lite with google_search grounding tool"
    - "Writes questions.json to $ENRICHMENT_DIR/<hash>/questions.json (atomic)"
    - "Emits single-line JSON summary on stdout under 50KB (D-03 contract)"
    - "Returns nonzero exit code on any failure"
    - "Articles under 2000 chars return a specific exit code / summary (skipped=-1)"
  artifacts:
    - path: "enrichment/__init__.py"
      provides: "enrichment package marker"
    - path: "enrichment/extract_questions.py"
      provides: "CLI + library function for Gemini-grounded question extraction"
      exports: ["extract_questions", "main"]
      min_lines: 80
    - path: "tests/unit/test_extract_questions.py"
      provides: "Grounding-tool presence, JSON output, short-article skip, error path"
      min_lines: 60
  key_links:
    - from: "enrichment/extract_questions.py"
      to: "Gemini API via google.genai"
      via: "types.Tool(google_search=types.GoogleSearch()) passed in config.tools"
      pattern: "google_search=types\\.GoogleSearch\\(\\)"
    - from: "enrichment/extract_questions.py"
      to: "$ENRICHMENT_DIR/<hash>/questions.json"
      via: "atomic write (tmp → rename)"
      pattern: "os\\.replace|\\.rename"
---

<objective>
Build the question-extraction helper: given a WeChat article markdown, call
Gemini 2.5 Flash Lite with Google Search grounding and return 1–3 under-documented
technical questions the article raises but does not answer.

Per D-12, this replaces the PRD's DeepSeek selection. The grounding tool lets
the model avoid suggesting questions already well-covered on the public web,
so downstream 好问 calls spend their budget on genuine gaps.

Purpose: This is the first Python helper the top-level Hermes skill
(`enrich_article`) calls. Its stdout contract (D-03) is what the skill parses
to drive the per-question loop.

Output: `enrichment/extract_questions.py` with a CLI entry point and unit tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md
@.planning/phases/04-knowledge-enrichment-zhihu/04-00-SUMMARY.md
@config.py
@docs/enrichment-prd.md

<interfaces>
From RESEARCH.md §4 — Gemini + grounding minimal snippet:

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-2.5-flash-lite",
    contents=["..."],
    config=types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
    ),
)
text = response.text
grounding = response.candidates[0].grounding_metadata  # may have grounding_chunks
```

From RESEARCH.md §9 — config.py additions:
- `ENRICHMENT_MIN_LENGTH = 2000`
- `ENRICHMENT_MAX_QUESTIONS = 3`
- `ENRICHMENT_LLM_MODEL = "gemini-2.5-flash-lite"`
- `ENRICHMENT_GROUNDING_ENABLED = True`
- `ENRICHMENT_BASE_DIR = BASE_DIR / "enrichment"`

These keys are ADDED in Plan 07 (integration). For this plan, read env-var
fallbacks directly so the helper is standalone:
- `ENRICHMENT_MIN_LENGTH` from env with default `2000`
- `ENRICHMENT_MAX_QUESTIONS` from env with default `3`
- `ENRICHMENT_LLM_MODEL` from env with default `"gemini-2.5-flash-lete"`
- `ENRICHMENT_BASE_DIR` from env `ENRICHMENT_DIR` with default `~/.hermes/omonigraph-vault/enrichment`

D-03 stdout contract:
```
{"hash": "<hash>", "status": "ok", "question_count": 2, "artifact": "/path/to/questions.json"}
```
Or on skip:
```
{"hash": "<hash>", "status": "skipped", "reason": "too_short", "char_count": 1200}
```
Or on fail:
```
{"hash": "<hash>", "status": "error", "error": "<message>"}
```
(exit code 0 for ok/skipped, 1 for error)
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 2.1: enrichment/extract_questions.py — library + CLI</name>
  <files>enrichment/__init__.py, enrichment/extract_questions.py, tests/unit/test_extract_questions.py</files>
  <read_first>
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §4 (Gemini + grounding SDK details, gotchas)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-RESEARCH.md §9 (config.py keys — for env-var fallbacks)
    - .planning/phases/04-knowledge-enrichment-zhihu/04-CONTEXT.md decisions D-03, D-12 (stdout contract, LLM choice)
    - tests/conftest.py (mock_gemini_client fixture shape)
  </read_first>
  <behavior>
    - Given article >= 2000 chars: mocked Gemini returns JSON array; function returns list of dicts; CLI writes questions.json and prints ok JSON summary.
    - Given article < 2000 chars: skip — exit 0, print skipped JSON, do NOT call Gemini.
    - Given Gemini raises: exit 1, print error JSON to stdout (not stderr for JSON contract; exception traceback goes to stderr).
    - Gemini call MUST include `google_search` tool when `ENRICHMENT_GROUNDING_ENABLED != "0"`.
    - Output file written atomically (tmp → rename).
    - Output file path: `$ENRICHMENT_DIR/<hash>/questions.json` (create dirs if missing).
  </behavior>
  <action>
    Create `enrichment/__init__.py` (empty — package marker).

    Create `enrichment/extract_questions.py`:

    ```python
    """Extract 1–3 under-documented technical questions from a WeChat article.

    Uses Gemini 2.5 Flash Lite with google_search grounding (D-12).
    Output contract (D-03): single-line JSON on stdout; full questions.json on disk.

    CLI:
        python -m enrichment.extract_questions <article_md_path> [--hash <hash>]
    """
    from __future__ import annotations

    import argparse
    import hashlib
    import json
    import logging
    import os
    import re
    import sys
    from pathlib import Path

    logger = logging.getLogger(__name__)

    DEFAULT_MIN_LENGTH = int(os.environ.get("ENRICHMENT_MIN_LENGTH", "2000"))
    DEFAULT_MAX_QUESTIONS = int(os.environ.get("ENRICHMENT_MAX_QUESTIONS", "3"))
    DEFAULT_MODEL = os.environ.get("ENRICHMENT_LLM_MODEL", "gemini-2.5-flash-lite")
    DEFAULT_BASE_DIR = Path(os.environ.get(
        "ENRICHMENT_DIR",
        str(Path.home() / ".hermes" / "omonigraph-vault" / "enrichment"),
    ))
    GROUNDING_ENABLED = os.environ.get("ENRICHMENT_GROUNDING_ENABLED", "1") != "0"


    _PROMPT_TMPL = (
        "You are a technical editor reviewing a Chinese AI/Agent engineering article. "
        "Identify {max_q} questions the article raises but does NOT answer in depth. "
        "Use Google Search to avoid suggesting questions already well-covered on the "
        "public web — focus on genuine under-documented gaps.\n\n"
        "Reply with ONLY a JSON array of objects with fields `question` (Chinese ok) "
        "and `context` (1-sentence why this is a gap). No prose before or after.\n\n"
        "Article:\n{article}"
    )


    def extract_questions(article_text: str, max_q: int = DEFAULT_MAX_QUESTIONS) -> list[dict]:
        """Call Gemini with grounding; return list of {question, context} dicts.

        Raises on API error. Parses best-effort JSON from response.text.
        """
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        tools = []
        if GROUNDING_ENABLED:
            tools = [types.Tool(google_search=types.GoogleSearch())]

        response = client.models.generate_content(
            model=DEFAULT_MODEL,
            contents=[_PROMPT_TMPL.format(max_q=max_q, article=article_text)],
            config=types.GenerateContentConfig(tools=tools) if tools else None,
        )
        text = response.text or ""
        # Strip code fences / prose and parse JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            raise ValueError(f"Gemini response did not contain a JSON array: {text[:200]}")
        parsed = json.loads(match.group(0))
        if not isinstance(parsed, list):
            raise ValueError(f"Parsed JSON is not a list: {parsed}")
        return parsed[:max_q]


    def _atomic_write_json(path: Path, data) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)


    def _derive_hash(article_path: Path, override: str | None) -> str:
        if override:
            return override
        return hashlib.md5(article_path.read_bytes()).hexdigest()[:10]


    def main(argv: list[str] | None = None) -> int:
        parser = argparse.ArgumentParser()
        parser.add_argument("article_path", help="Path to WeChat article markdown")
        parser.add_argument("--hash", help="Article hash; derived from md5 if omitted")
        parser.add_argument("--base-dir", default=str(DEFAULT_BASE_DIR),
                            help="Base enrichment dir")
        args = parser.parse_args(argv)

        article_path = Path(args.article_path)
        base_dir = Path(args.base_dir)
        article_hash = _derive_hash(article_path, args.hash)

        if not article_path.is_file():
            print(json.dumps({"hash": article_hash, "status": "error",
                              "error": f"article_path not found: {article_path}"}))
            return 1

        article_text = article_path.read_text(encoding="utf-8")
        if len(article_text) < DEFAULT_MIN_LENGTH:
            print(json.dumps({"hash": article_hash, "status": "skipped",
                              "reason": "too_short", "char_count": len(article_text)}))
            return 0

        try:
            questions = extract_questions(article_text, max_q=DEFAULT_MAX_QUESTIONS)
        except Exception as e:
            import traceback
            traceback.print_exc(file=sys.stderr)
            print(json.dumps({"hash": article_hash, "status": "error", "error": str(e)}))
            return 1

        out_path = base_dir / article_hash / "questions.json"
        _atomic_write_json(out_path, {
            "hash": article_hash,
            "article_path": str(article_path),
            "questions": questions,
        })

        print(json.dumps({
            "hash": article_hash,
            "status": "ok",
            "question_count": len(questions),
            "artifact": str(out_path),
        }))
        return 0


    if __name__ == "__main__":
        sys.exit(main())
    ```

    Create `tests/unit/test_extract_questions.py`:

    ```python
    """Unit tests for enrichment.extract_questions — D-12 grounding, D-03 contract."""
    from __future__ import annotations
    import json
    import sys
    from pathlib import Path
    from unittest.mock import MagicMock
    import pytest


    @pytest.fixture(autouse=True)
    def _set_gemini_key(monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")


    @pytest.mark.unit
    def test_extract_questions_calls_google_search_tool(mocker, monkeypatch):
        """D-12: the grounding tool must be attached to the request."""
        monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "1")
        from enrichment import extract_questions as eq
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '[{"question": "q1", "context": "c1"}]'
        mock_client.models.generate_content.return_value = mock_response
        mocker.patch("google.genai.Client", return_value=mock_client)

        result = eq.extract_questions("a" * 3000, max_q=2)

        assert result == [{"question": "q1", "context": "c1"}]
        call = mock_client.models.generate_content.call_args
        config = call.kwargs["config"]
        # Tool named "google_search" should be present
        tool_names = [type(t.google_search).__name__ if hasattr(t, "google_search") and t.google_search else None for t in config.tools]
        assert any(n == "GoogleSearch" for n in tool_names), (
            f"Expected GoogleSearch tool in config.tools; got {config.tools}"
        )


    @pytest.mark.unit
    def test_extract_questions_respects_max_q(mocker, monkeypatch):
        monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
        from enrichment import extract_questions as eq
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '[{"question":"q1","context":"c1"},{"question":"q2","context":"c2"},{"question":"q3","context":"c3"},{"question":"q4","context":"c4"}]'
        mock_client.models.generate_content.return_value = mock_response
        mocker.patch("google.genai.Client", return_value=mock_client)
        result = eq.extract_questions("a" * 3000, max_q=3)
        assert len(result) == 3


    @pytest.mark.unit
    def test_cli_short_article_returns_skipped(tmp_path: Path, capsys):
        from enrichment.extract_questions import main
        article = tmp_path / "short.md"
        article.write_text("tiny")  # << 2000 chars
        rc = main([str(article), "--hash", "h1", "--base-dir", str(tmp_path)])
        out = json.loads(capsys.readouterr().out.strip())
        assert rc == 0
        assert out["status"] == "skipped"
        assert out["reason"] == "too_short"
        assert out["hash"] == "h1"


    @pytest.mark.unit
    def test_cli_success_writes_atomic_json(tmp_path: Path, mocker, capsys, monkeypatch):
        monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '[{"question":"Q","context":"C"}]'
        mock_client.models.generate_content.return_value = mock_response
        mocker.patch("google.genai.Client", return_value=mock_client)

        from enrichment.extract_questions import main
        article = tmp_path / "a.md"
        article.write_text("x" * 2500)
        rc = main([str(article), "--hash", "abcd", "--base-dir", str(tmp_path)])
        out = json.loads(capsys.readouterr().out.strip())
        assert rc == 0
        assert out["status"] == "ok" and out["question_count"] == 1
        qjson = json.loads((tmp_path / "abcd" / "questions.json").read_text(encoding="utf-8"))
        assert qjson["hash"] == "abcd"
        assert qjson["questions"] == [{"question":"Q","context":"C"}]
        # No leftover tmp files
        assert not list((tmp_path / "abcd").glob("*.tmp"))


    @pytest.mark.unit
    def test_cli_gemini_error_returns_1(tmp_path: Path, mocker, capsys, monkeypatch):
        monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = RuntimeError("boom")
        mocker.patch("google.genai.Client", return_value=mock_client)

        from enrichment.extract_questions import main
        article = tmp_path / "a.md"
        article.write_text("x" * 2500)
        rc = main([str(article), "--hash", "e1", "--base-dir", str(tmp_path)])
        out = json.loads(capsys.readouterr().out.strip())
        assert rc == 1
        assert out["status"] == "error"
        assert "boom" in out["error"]


    @pytest.mark.unit
    def test_cli_output_line_under_50kb(tmp_path: Path, mocker, capsys, monkeypatch):
        """D-03 Hermes tool_output.max_bytes cap = 50000."""
        monkeypatch.setenv("ENRICHMENT_GROUNDING_ENABLED", "0")
        from enrichment.extract_questions import main
        article = tmp_path / "short.md"
        article.write_text("tiny")
        main([str(article), "--hash", "h1", "--base-dir", str(tmp_path)])
        line = capsys.readouterr().out.strip()
        assert len(line.encode("utf-8")) < 50000
        assert "\n" not in line  # single-line
    ```
  </action>
  <verify>
    <automated>pytest tests/unit/test_extract_questions.py -x -v</automated>
  </verify>
  <acceptance_criteria>
    - Files `enrichment/__init__.py` and `enrichment/extract_questions.py` exist
    - `grep -q "google_search=types.GoogleSearch()" enrichment/extract_questions.py` succeeds
    - `grep -q "gemini-2.5-flash-lite" enrichment/extract_questions.py` succeeds
    - `grep -q "ENRICHMENT_MIN_LENGTH" enrichment/extract_questions.py` succeeds
    - `grep -q "os.replace" enrichment/extract_questions.py` succeeds (atomic write)
    - `grep -q "def main" enrichment/extract_questions.py` succeeds
    - `grep -qE "status.:..(ok|skipped|error)" enrichment/extract_questions.py` succeeds (three status values present)
    - `pytest tests/unit/test_extract_questions.py -x -v` exits 0 with all 6 tests passing
    - `python -m enrichment.extract_questions --help` exits 0 (CLI entry point works)
  </acceptance_criteria>
  <done>extract_questions module works; all 6 unit tests pass; CLI entry point responds to --help</done>
</task>

</tasks>

<verification>
  - `pytest tests/unit/test_extract_questions.py -x -v` green
  - `python -m enrichment.extract_questions --help` returns usage without error
  - Module is importable: `python -c "from enrichment.extract_questions import extract_questions, main"`
</verification>

<success_criteria>
- Gemini + `google_search` grounding wired per D-12
- Single-line JSON stdout contract per D-03
- Short-article skip (<2000 chars) returns `status: skipped`, exits 0
- Atomic file write (tmp → rename)
- 6 unit tests green
</success_criteria>

<output>
After completion, create `.planning/phases/04-knowledge-enrichment-zhihu/04-02-SUMMARY.md`.
</output>
