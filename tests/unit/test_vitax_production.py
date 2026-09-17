"""Offline behavior tests for the real-source VitaX production slice."""
from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest

from vitax.knowledge import KnowledgeError, build
from vitax import production
from vitax.production import ProductionError, accept_model_output, merge_accepted_articles, run, standardize_documents

_REAL_EXTRACT_BODY = production._extract_body

@pytest.fixture(autouse=True)
def _deterministic_trafilatura_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit checks offline; real runs invoke the installed trafilatura API."""
    monkeypatch.setattr(
        production,
        "_extract_body",
        lambda html: (["Alpha evidence is exact."] if "Alpha evidence" in html else ["Beta evidence is exact."], "trafilatura-precision"),
    )


def _input(tmp_path: Path) -> dict[str, object]:
    first = tmp_path / "first.html"
    first.write_text(
        "<html><body><p>Alpha evidence is exact.</p><img src='/alpha.png' alt='Alpha diagram'></body></html>",
        encoding="utf-8",
    )
    second = tmp_path / "second.html"
    second.write_text("<html><body><p>Beta evidence is exact.</p></body></html>", encoding="utf-8")
    images = tmp_path / "images.jsonl"
    images.write_text(json.dumps({"image_url": "/alpha.png", "alt": "Alpha diagram", "nearby_text": "technical architecture"}) + "\n", encoding="utf-8")
    return {
        "documents": [
            {"source_id": "source-alpha", "source_url": "https://example.test/a", "html_path": str(first), "raw_html_sha256": hashlib.sha256(first.read_bytes()).hexdigest(), "image_context_path": str(images), "title": "Alpha", "fetched_at": "2026-09-09T21:51:50Z"},
            {"source_id": "source-beta", "source_url": "https://example.test/b", "html_path": str(second), "raw_html_sha256": hashlib.sha256(second.read_bytes()).hexdigest(), "title": "Beta", "source_published_at": "2026-09-08", "fetched_at": "2026-09-09T21:51:51Z"},
        ]
    }


def _model(standardized: dict[str, object]) -> str:
    alpha, beta = standardized["documents"]
    return json.dumps(
        {
            "knowledge": [
                {"knowledge_id": "article-alpha", "kind": "article", "language": "zh", "title": "阿尔法解读", "body": "阿尔法证据说明了结论。", "citations": [{"revision_id": alpha["revision_id"], "locator": "paragraph:1", "quote": "Alpha evidence is exact."}], "image_ids": [alpha["images"][0]["image_id"]]},
                {"knowledge_id": "wiki-alpha-beta", "kind": "wiki", "language": "zh", "title": "阿尔法与贝塔", "body": "两份来源共同说明主题。", "citations": [{"revision_id": alpha["revision_id"], "locator": "paragraph:1", "quote": "Alpha evidence is exact."}, {"revision_id": beta["revision_id"], "locator": "paragraph:1", "quote": "Beta evidence is exact."}]},
            ],
            "entities": [{"entity_id": "alpha", "name": "Alpha"}, {"entity_id": "beta", "name": "Beta"}],
            "relations": [{"relation_id": "alpha-supports-beta", "source_id": "alpha", "target_id": "beta", "relation_type": "supports", "citations": [{"revision_id": alpha["revision_id"], "locator": "paragraph:1", "quote": "Alpha evidence is exact."}]}],
        },
        ensure_ascii=False,
    )


def test_real_html_becomes_a_citable_public_projection_without_exposing_raw_html(tmp_path: Path) -> None:
    """Breaks if locators, source-image allowlisting, or public DTO reuse regress."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    accepted = accept_model_output(standardized, _model(standardized), release_id="release-real")
    database = tmp_path / "public.sqlite"
    build(accepted["projection"], database)

    alpha = standardized["documents"][0]
    assert alpha["content_hash"]
    assert alpha["fetched_at"] == "2026-09-09T21:51:50Z"
    assert alpha["paragraphs"] == [{"locator": "paragraph:1", "text": "Alpha evidence is exact."}]
    assert accepted["selected_images"] == [{"image_id": alpha["images"][0]["image_id"], "revision_id": alpha["revision_id"], "locator": "image:1", "source_article_url": "https://example.test/a", "source_url": "https://example.test/alpha.png", "caption": "Alpha diagram"}]
    assert b"<html>" not in database.read_bytes()


@pytest.mark.parametrize("mutation", ["quote", "punctuation", "image", "manual"])
def test_acceptance_rejects_unverifiable_or_overwriting_model_proposals(tmp_path: Path, mutation: str) -> None:
    """Breaks if a model can fabricate a quote, image URL, or overwrite manual knowledge."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    proposal = json.loads(_model(standardized))
    if mutation == "quote":
        proposal["knowledge"][0]["citations"][0]["quote"] = "invented quote"
        expected = "does not match"
        manual = None
    elif mutation == "punctuation":
        proposal["knowledge"][0]["citations"][0]["quote"] = "."
        proposal["knowledge"][0]["citations"][0]["locator"] = "paragraph:1"
        expected = "meaningful text"
        manual = None
    elif mutation == "image":
        proposal["knowledge"][0]["image_ids"] = ["https://untrusted.test/image.png"]
        expected = "unknown source image"
        manual = None
    else:
        expected = "manual knowledge"
        manual = {"knowledge": [{"knowledge_id": "article-alpha", "kind": "article", "title": "人工条目", "body": "人工内容", "evidence_ids": []}]}

    with pytest.raises(ProductionError, match=expected):
        accept_model_output(standardized, json.dumps(proposal), manual=manual)


def test_public_builder_omits_private_model_artifacts(tmp_path: Path) -> None:
    """Breaks if the production slice bypasses the existing public visibility allowlist."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    accepted = accept_model_output(standardized, _model(standardized))
    accepted["projection"]["knowledge"][0]["visibility"] = "private"

    database = tmp_path / "public.sqlite"
    build(accepted["projection"], database)
    assert "阿尔法解读".encode() not in database.read_bytes()


def test_wiki_stage_requires_wiki_and_deterministically_merges_accepted_articles(tmp_path: Path) -> None:
    """Breaks if Wiki reruns or drops the accepted articles it is meant to extend."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    article_source = json.loads(_model(standardized))
    article_source["knowledge"] = [article_source["knowledge"][0]]
    article = accept_model_output(
        {"schema_version": 1, "documents": [standardized["documents"][0]]},
        json.dumps(article_source),
        stage="article",
    )
    wiki_source = json.loads(_model(standardized))
    wiki_source["knowledge"] = [wiki_source["knowledge"][1]]
    wiki_source["entities"] = []
    wiki_source["relations"] = []
    wiki = accept_model_output(standardized, json.dumps(wiki_source), stage="wiki")
    merged = merge_accepted_articles(wiki, [article])

    assert [item["knowledge_id"] for item in merged["projection"]["knowledge"]] == ["article-alpha", "wiki-alpha-beta"]
    assert {item["entity_id"]: item for item in merged["projection"]["entities"]} == {
        item["entity_id"]: item for item in article["projection"]["entities"]
    }
    assert {item["relation_id"]: item for item in merged["projection"]["relations"]} == {
        item["relation_id"]: item for item in article["projection"]["relations"]
    }
    with pytest.raises(ProductionError, match="article stage"):
        accept_model_output(standardized, json.dumps(wiki_source), stage="article")


def test_wiki_acceptance_rejects_model_graph_duplicates(tmp_path: Path) -> None:
    """Breaks if the Wiki call can recreate article entities or relations."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    proposal = json.loads(_model(standardized))
    proposal["knowledge"] = [proposal["knowledge"][1]]

    with pytest.raises(ProductionError, match="wiki stage must not produce entities or relations"):
        accept_model_output(standardized, json.dumps(proposal), stage="wiki")


def test_wiki_requires_one_accepted_article_for_each_selected_revision(tmp_path: Path) -> None:
    """Breaks if a Wiki can cite a source that never completed article production."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    alpha, beta = standardized["documents"]
    source = json.loads(_model(standardized))
    source["knowledge"] = [source["knowledge"][0]]
    source["relations"] = []
    alpha_article = accept_model_output({"schema_version": 1, "documents": [alpha]}, json.dumps(source), stage="article")
    alpha_path = tmp_path / "alpha-accepted.json"
    alpha_path.write_text(json.dumps(alpha_article), encoding="utf-8")

    with pytest.raises(ProductionError, match="missing accepted article"):
        production._accepted_article_context([alpha_path], [alpha["revision_id"], beta["revision_id"]])

    beta_proposal = {
        "knowledge": [{"knowledge_id": "article-beta", "kind": "article", "language": "zh", "title": "贝塔解读", "body": "贝塔证据说明了结论。", "citations": [{"revision_id": beta["revision_id"], "locator": "paragraph:1", "quote": "Beta evidence is exact."}]}],
        "entities": [], "relations": [],
    }
    beta_article = accept_model_output({"schema_version": 1, "documents": [beta]}, json.dumps(beta_proposal), stage="article")
    beta_path = tmp_path / "beta-accepted.json"
    beta_path.write_text(json.dumps(beta_article), encoding="utf-8")
    context, _ = production._accepted_article_context([alpha_path, beta_path], [alpha["revision_id"], beta["revision_id"]])

    assert [item["knowledge_id"] for item in context] == ["article-alpha", "article-beta"]


def test_wiki_coverage_preserves_manual_and_model_articles_for_one_revision(tmp_path: Path) -> None:
    """Breaks if preserving manual article knowledge blocks a later Wiki update."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    alpha = standardized["documents"][0]
    proposal = json.loads(_model(standardized))
    proposal["knowledge"] = [proposal["knowledge"][0]]
    proposal["relations"] = []
    accepted = accept_model_output({"schema_version": 1, "documents": [alpha]}, json.dumps(proposal), stage="article")
    accepted["projection"]["knowledge"].append({"knowledge_id": "manual-alpha", "kind": "article", "title": "人工阿尔法", "body": "人工补充内容", "evidence_ids": accepted["projection"]["knowledge"][0]["evidence_ids"], "visibility": "public"})
    artifact = tmp_path / "alpha-with-manual.json"
    artifact.write_text(json.dumps(accepted), encoding="utf-8")

    context, _ = production._accepted_article_context([artifact], [alpha["revision_id"]])

    assert [item["knowledge_id"] for item in context] == ["article-alpha", "manual-alpha"]


def test_capture_root_rejects_outside_and_symlinked_html(tmp_path: Path) -> None:
    """Breaks if untrusted paths can expand the local Hermes capture boundary."""
    root = tmp_path / "captures"
    root.mkdir()
    outside = tmp_path / "outside.html"
    outside.write_text("<p>outside</p>", encoding="utf-8")
    escaped = root / "escaped.html"
    escaped.symlink_to(outside)
    source = _input(tmp_path)
    source["documents"] = [{"source_id": "source-alpha", "source_url": "https://example.test/a", "html_path": str(escaped), "raw_html_sha256": hashlib.sha256(outside.read_bytes()).hexdigest(), "title": "Alpha", "fetched_at": "2026-09-09T21:51:50Z"}]

    with pytest.raises(ProductionError, match="capture root"):
        standardize_documents(source, capture_root=root)


def test_capture_root_requires_the_recorded_raw_html_hash(tmp_path: Path) -> None:
    """Breaks if a substituted capture can enter a model prompt under an old identity."""
    source = _input(tmp_path)
    source["documents"] = [dict(source["documents"][0], raw_html_sha256="0" * 64)]

    with pytest.raises(ProductionError, match="raw_html_sha256"):
        standardize_documents(source, capture_root=tmp_path)


def test_final_hermes_envelope_rejects_quote_heavy_prompt_without_spawning() -> None:
    """Breaks if production measures a prompt differently from the Hermes transport."""
    standardized = {"documents": [{"revision_id": "rev-heavy", "title": "Heavy", "paragraphs": [{"locator": "paragraph:1", "text": '"' * 14500}], "images": []}]}
    module = production._load_hermes_module()

    with pytest.raises(ProductionError, match="adapter input budget"):
        production._validate_hermes_prompt(module, production._prompt(standardized))


def test_image_with_empty_alt_uses_source_context_as_a_citable_caption(tmp_path: Path) -> None:
    """Breaks if real technical figures disappear merely because their alt is empty."""
    source = _input(tmp_path)
    context = tmp_path / "images.jsonl"
    context.write_text(json.dumps({"image_url": "/flow.png", "alt": "", "nearby_text": "Contextual retrieval preprocessing flow diagram."}) + "\n", encoding="utf-8")
    standardized = standardize_documents(source, capture_root=tmp_path)

    image = standardized["documents"][0]["images"][0]
    assert image["caption"] == "Contextual retrieval preprocessing flow diagram."
    assert image["source_article_url"] == "https://example.test/a"
    assert image["source_url"] == "https://example.test/flow.png"


def test_image_caption_does_not_promote_html_residue_from_real_capture_context(tmp_path: Path) -> None:
    """Breaks if an SVG/attribute fragment reaches the accepted professional caption."""
    source = _input(tmp_path)
    context = tmp_path / "images.jsonl"
    context.write_text(json.dumps({"image_url": "/flow.png", "alt": "", "nearby_text": '1.70589 3.6 fill="currentColor"> Copy The resulting contextual text'}) + "\n", encoding="utf-8")
    standardized = standardize_documents(source, capture_root=tmp_path)

    assert standardized["documents"][0]["images"][0]["caption"] == "Source image from Alpha (caption unavailable in captured HTML)."


def test_offline_rebuild_links_immutable_model_and_usage_receipts(tmp_path: Path) -> None:
    """Breaks if caption repair requires another model call or loses actual usage."""
    source = _input(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")
    standardized = standardize_documents(source, capture_root=tmp_path)
    model_output = tmp_path / "model-output.json"
    model_output.write_text(_model(standardized), encoding="utf-8")
    receipt = tmp_path / "usage.json"
    receipt.write_text(json.dumps({"provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "api_calls": 1, "credential": "must-not-copy"}), encoding="utf-8")

    result = run(input_path, tmp_path / "rebuilt", capture_root=tmp_path, model_output=model_output, model_receipt=receipt, run_hermes=False, manual=None, sqlite_path=None)

    rebuilt = tmp_path / "rebuilt"
    assert result["usage"]["api_calls"] == 1
    assert json.loads((rebuilt / "usage.json").read_text()) == {"provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "api_calls": 1}
    assert json.loads((rebuilt / "model-receipt.json").read_text())["model_output"]["sha256"] == hashlib.sha256(model_output.read_bytes()).hexdigest()


def test_offline_receipt_rejects_invalid_known_usage_type(tmp_path: Path) -> None:
    """Breaks if receipt rebuild accepts a malformed field that live Hermes rejects."""
    source = _input(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")
    model_output = tmp_path / "model-output.json"
    model_output.write_text(_model(standardize_documents(source, capture_root=tmp_path)), encoding="utf-8")
    receipt = tmp_path / "usage.json"
    receipt.write_text(json.dumps({"provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "cache_read_tokens": "three"}), encoding="utf-8")
    output = tmp_path / "rejected-rebuild"

    with pytest.raises(ProductionError, match="usage schema"):
        run(input_path, output, capture_root=tmp_path, model_output=model_output, model_receipt=receipt, run_hermes=False, manual=None, sqlite_path=None)

    assert not (output / "usage.json").exists()
    assert not (output / "accepted.json").exists()


@pytest.mark.parametrize(
    "receipt_value",
    [
        {"provider": "openai-codex", "model": "gpt-6-astra", "failed": True},
        {"provider": "unexpected", "model": "gpt-6-astra", "failed": False},
        {"provider": "openai-codex", "model": "unexpected", "failed": False},
    ],
)
def test_offline_receipt_requires_a_successful_expected_hermes_route(
    tmp_path: Path, receipt_value: dict[str, object]
) -> None:
    """Breaks if a rejected live completion can be promoted through replay."""
    source = _input(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(source), encoding="utf-8")
    model_output = tmp_path / "model-output.json"
    model_output.write_text(_model(standardize_documents(source, capture_root=tmp_path)), encoding="utf-8")
    receipt = tmp_path / "usage.json"
    receipt.write_text(json.dumps(receipt_value), encoding="utf-8")
    output = tmp_path / "rejected-success-receipt"

    with pytest.raises(ProductionError, match="successful Hermes completion"):
        run(input_path, output, capture_root=tmp_path, model_output=model_output, model_receipt=receipt, run_hermes=False, manual=None, sqlite_path=None)

    assert not (output / "usage.json").exists()
    assert not (output / "accepted.json").exists()
    assert not (output / "projection.json").exists()


def test_route_mismatch_persists_safe_failure_artifacts_without_accepting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if a completed but route-invalid call loses evidence or enters projection."""
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(_input(tmp_path)), encoding="utf-8")
    fake = tmp_path / "fake-hermes"
    fake.write_text(
        "#!" + sys.executable + "\n" + '''import json, sys
result = sys.argv[sys.argv.index("--result-file") + 1]
with open(result, "w", encoding="utf-8") as handle:
    json.dump({"ok": False, "text": "completed mismatch output", "usage": {"provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "api_calls": 1, "credential": "private"}, "failure": {"code": "route_mismatch"}, "initialization": {"fallback_chain_count": 0, "tools_count": 0, "tool_names": [], "platform": "subagent", "session_db_none": True, "session_id_none": True}}, handle)
print("private stderr", file=sys.stderr)
sys.exit(2)
''',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    output = tmp_path / "failed"

    with pytest.raises(Exception, match="exit=2"):
        run(input_path, output, capture_root=tmp_path, model_output=None, run_hermes=True, manual=None, sqlite_path=None, stage="article", source_id="source-alpha")

    assert (output / "model-output.json").read_text(encoding="utf-8") == "completed mismatch output"
    assert json.loads((output / "usage.json").read_text(encoding="utf-8")) == {
        "provider": "openai-codex", "model": "gpt-6-astra", "failed": False, "api_calls": 1
    }
    failure = json.loads((output / "failure.json").read_text(encoding="utf-8"))
    assert failure["code"] == "run_invalid"
    assert failure["native_failure_code"] == "route_mismatch"
    assert failure["initialization"] == {"fallback_chain_count": 0, "tools_count": 0, "tool_names": [], "platform": "subagent", "session_db_none": True}
    artifacts = "".join(path.read_text(encoding="utf-8") for path in output.iterdir())
    assert "private" not in artifacts
    assert not (output / "accepted.json").exists()
    assert not (output / "projection.json").exists()


def test_explicit_hermes_adapter_import_loads_dataclass_without_spawning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks if spec execution omits the sys.modules registration dataclasses need."""
    monkeypatch.delitem(sys.modules, "vitax_explicit_hermes", raising=False)
    callback = production._load_hermes()

    assert callback.__name__ == "hermes_model_complete_with_usage"
    assert "vitax_explicit_hermes" not in sys.modules


def test_trafilatura_single_newline_output_keeps_multiple_standard_paragraphs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Breaks if real trafilatura text collapses a whole source into paragraph:1."""
    module = type(sys)("trafilatura")
    module.extract = lambda *_args, **_kwargs: "Heading\nFirst source paragraph.\nSecond source paragraph."
    monkeypatch.setitem(sys.modules, "trafilatura", module)

    paragraphs, method = _REAL_EXTRACT_BODY("<html>ignored</html>")

    assert method == "trafilatura-precision"
    assert paragraphs == ["Heading", "First source paragraph.", "Second source paragraph."]


def test_usage_invalid_native_envelope_retains_text_and_safe_diagnosis(tmp_path, monkeypatch):
    source = tmp_path / "input.json"
    source.write_text(json.dumps(_input(tmp_path)), encoding="utf-8")
    envelope = {"ok": False, "usage": None, "text": "原始输出",
                "failure": {"code": "usage_schema_invalid", "usage_field": "cache_read_tokens",
                            "usage_type": "str", "value": "sensitive-decoy"}}
    fake = tmp_path / "native-python"
    fake.write_text("#!" + sys.executable + "\nimport sys, json\n"
                    + "from pathlib import Path\n"
                    + "Path(sys.argv[sys.argv.index('--result-file') + 1]).write_text("
                    + repr(json.dumps(envelope)) + ")\nraise SystemExit(2)\n")
    fake.chmod(0o755)
    monkeypatch.setenv("OMNIGRAPH_HERMES_PYTHON", str(fake))
    output = tmp_path / "failure-artifact"
    with pytest.raises(Exception, match="exit=2"):
        run(source, output, capture_root=tmp_path, model_output=None, run_hermes=True,
            manual=None, sqlite_path=None, stage="article", source_id="source-alpha")
    assert (output / "model-output.json").read_text() == "原始输出"
    failure = json.loads((output / "failure.json").read_text())
    assert failure["usage_field"] == "cache_read_tokens"
    assert failure["usage_type"] == "str"
    assert "sensitive-decoy" not in (output / "failure.json").read_text()
    assert not (output / "accepted.json").exists()
    assert not (output / "projection.json").exists()
