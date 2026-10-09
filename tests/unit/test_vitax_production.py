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


def test_stored_markdown_keeps_exact_bytes_code_and_unknown_fetch_time(tmp_path: Path) -> None:
    markdown = "原文第一段。\n\n```python\nif True:\n    print('原样')\n\n    print('代码')\n```\n"
    path = tmp_path / "original.md"
    path.write_bytes(markdown.encode())
    item = {"source_id": "wechat-1", "source_url": "https://example.test/stored", "capture_format": "stored-markdown", "markdown_path": str(path), "raw_markdown_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "source_record_ref": {"source": "wechat", "record_id": 1}, "source_snapshot_id": "snapshot-one", "representation_saved_at": "2026-10-02T01:00:00Z", "fetched_at": None}
    source = {"documents": [item]}
    document = standardize_documents(source, capture_root=tmp_path)["documents"][0]
    assert document["raw_markdown_sha256"] == item["raw_markdown_sha256"]
    assert "raw_html_sha256" not in document and document["images"] == []
    assert document["fetched_at"] is None and document["representation_saved_at"] == item["representation_saved_at"]
    assert document["extraction_method"] == "stored-markdown:v1"
    assert markdown == document["paragraphs"][0]["text"]
    revision = document["revision_id"]
    proposal = {"knowledge": [{"knowledge_id": "stored-article", "kind": "article", "language": "zh", "title": "保存原文", "body": "代码证据保留了缩进及空行。", "citations": [{"revision_id": revision, "locator": "paragraph:1", "quote": "if True:\n    print('原样')\n\n    print('代码')"}]}], "entities": [], "relations": []}
    accepted = accept_model_output({"documents": [document]}, json.dumps(proposal), stage="article")
    build(accepted["projection"], tmp_path / "stored-public.sqlite")
    duplicated = standardize_documents({"documents": [item, {**item, "source_id": "alias-one", "source_url": "https://example.test/alias"}]}, capture_root=tmp_path)
    wiki = {"knowledge": [{"knowledge_id": "duplicate-source-wiki", "kind": "wiki", "language": "zh", "title": "同一来源", "body": "这是同一个稳定来源的两个版本。", "citations": [{"revision_id": d["revision_id"], "locator": "paragraph:1", "quote": "原文第一段。"} for d in duplicated["documents"]]}], "entities": [], "relations": []}
    # MVP-02: one source (even two revisions of one URL) may start a Wiki.
    accepted_wiki = accept_model_output(duplicated, json.dumps(wiki), stage="wiki")
    assert accepted_wiki["projection"]["knowledge"][0]["knowledge_id"] == "duplicate-source-wiki"
    for changes in ({"html_path": str(path)}, {"capture_format": "other"}, {"raw_markdown_sha256": "0" * 64}, {"image_context_path": str(path)}, {"source_record_ref": {"source": "rss", "record_id": True}}):
        with pytest.raises(ProductionError):
            standardize_documents({"documents": [{**item, **changes}]}, capture_root=tmp_path)


def test_wiki_can_start_from_one_source(tmp_path: Path) -> None:
    """Breaks if the retired two-source pairing gate still blocks a single source."""
    source = _input(tmp_path)
    source["documents"][1]["source_url"] = source["documents"][0]["source_url"]
    standardized = standardize_documents(source, capture_root=tmp_path)
    accepted = accept_model_output(standardized, _model(standardized))
    wiki = next(item for item in accepted["projection"]["knowledge"] if item["kind"] == "wiki")
    assert wiki["knowledge_id"] == "wiki-alpha-beta"


def test_article_without_model_citations_gets_a_truthful_source_link(tmp_path: Path) -> None:
    """Breaks if one missing citation field blocks the whole batch again (10/7)."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    alpha = standardized["documents"][0]
    proposal = {"knowledge": [{"knowledge_id": "article-alpha", "kind": "article", "language": "zh", "title": "阿尔法", "body": "阿尔法证据说明了结论。"}], "entities": [], "relations": []}
    accepted = accept_model_output({"schema_version": 1, "documents": [alpha]}, json.dumps(proposal), stage="article")
    knowledge = accepted["projection"]["knowledge"][0]
    quote = {item["evidence_id"]: item for item in accepted["projection"]["evidence"]}[knowledge["evidence_ids"][0]]
    assert quote["revision_id"] == alpha["revision_id"] and quote["quote"] in alpha["paragraphs"][0]["text"]


def test_wiki_knowledge_without_graph_lists_is_accepted(tmp_path: Path) -> None:
    """Breaks if a Wiki reply that omits entities/relations blocks the batch (10/5)."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    alpha, beta = standardized["documents"]
    proposal = {"knowledge": [{"knowledge_id": "wiki-alpha-beta", "kind": "wiki", "language": "zh", "title": "主题", "body": "两份来源共同说明主题。", "citations": [{"revision_id": alpha["revision_id"], "locator": "paragraph:1", "quote": "Alpha evidence is exact."}, {"revision_id": beta["revision_id"], "locator": "paragraph:1", "quote": "Beta evidence is exact."}]}]}
    accepted = accept_model_output(standardized, json.dumps(proposal), stage="wiki")
    assert accepted["projection"]["entities"] == [] and accepted["projection"]["relations"] == []


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


def test_direct_deepseek_receipt_accepts_only_matching_output(tmp_path):
    source = _input(tmp_path)
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(source))
    raw = _model(standardize_documents(source, capture_root=tmp_path))
    output = tmp_path / "output.json"; output.write_text(raw)
    receipt = tmp_path / "receipt.json"
    usage = dict(receipt_type="deepseek-chat.v1", provider="deepseek", model="deepseek-flash",
                 requested_model="deepseek-v4-flash", request_id="synthetic", api_calls=1, failed=False,
                 finish_reason="stop", prompt_tokens=10, completion_tokens=3, total_tokens=13,
                 output_sha256=hashlib.sha256(raw.encode()).hexdigest())
    receipt.write_text(json.dumps(usage | {"credential":"must-not-copy"}))
    accepted = run(input_path, tmp_path / "accepted", capture_root=tmp_path,
                   model_output=output, model_receipt=receipt, run_hermes=False, manual=None, sqlite_path=None)
    assert accepted["usage"] == usage
    output.write_text(raw + " ")
    with pytest.raises(ProductionError, match="output-bound"):
        run(input_path, tmp_path / "rejected", capture_root=tmp_path,
            model_output=output, model_receipt=receipt, run_hermes=False, manual=None, sqlite_path=None)


def test_wrapped_prose_citation_retains_exact_original_span():
    from vitax.production import _citations
    source='Before. Training-Time Harness\n中，保留原文。 After.'
    item={'revision_id':'rev-a','locator':'paragraph:1','quote':'Training-Time Harness 中，保留原文。'}
    _,evidence,_=_citations([item],{('rev-a','paragraph:1'):source})
    assert evidence[0]['quote']=='Training-Time Harness\n中，保留原文。'
    for invalid in ('Training-Time Harness 中，改写原文。','Training-Time Harness 中;保留原文。'):
        with pytest.raises(ProductionError, match='does not match'):
            _citations([item | {'quote':invalid}],{('rev-a','paragraph:1'):source})
    with pytest.raises(ProductionError, match='does not match'):
        _citations([item],{('rev-a','paragraph:1'):source+' '+source})


def test_citation_ids_resolve_to_exact_source_and_reject_unknown_ids():
    from vitax.production import _citations, _citation_bank
    locators={('rev-a','paragraph:1'):'An\nevalis a collection of challenges designed to answer a question about a model.'}
    bank=_citation_bank(locators)
    selected=next(item for item in bank if 'collection of challenges' in item['quote'])
    _,evidence,_=_citations([{'citation_id':selected['citation_id']}],locators)
    assert evidence[0]['quote']==selected['quote']
    assert evidence[0]['quote'] in locators[('rev-a','paragraph:1')]
    with pytest.raises(ProductionError, match='unknown citation'):
        _citations([{'citation_id':'invented'}],locators)


def test_model_entity_case_is_canonical_and_case_collision_is_rejected(tmp_path):
    standardized=standardize_documents(_input(tmp_path),capture_root=tmp_path)
    proposal=json.loads(_model(standardized))
    proposal['entities'][0]['entity_id']='Alpha'
    proposal['relations'][0]['source_id']='Alpha'
    accepted=accept_model_output(standardized,json.dumps(proposal))
    assert accepted['projection']['entities'][0]['entity_id']=='alpha'
    assert accepted['projection']['relations'][0]['source_id']=='alpha'
    proposal['entities'].append({'entity_id':'alpha','name':'collision'})
    with pytest.raises(ProductionError, match='unique'):
        accept_model_output(standardized,json.dumps(proposal))


def test_short_lines_still_have_verbatim_citation_bank():
    from vitax.production import _citation_bank
    text='\n\n  '+('harness\nshort prose\n' * 120)
    bank=_citation_bank({('rev-a','paragraph:1'):text})
    assert bank and bank[0]['quote'] in text
    from vitax.production import _citations
    _,evidence,_=_citations([{'citation_id':bank[0]['citation_id']}],{('rev-a','paragraph:1'):text.strip()})
    assert evidence[0]['quote'] in text


def test_relation_case_collision_is_rejected_before_build(tmp_path):
    standardized=standardize_documents(_input(tmp_path),capture_root=tmp_path)
    proposal=json.loads(_model(standardized))
    relation=proposal['relations'][0]
    proposal['relations'].append(relation | {'relation_id':relation['relation_id'].upper()})
    with pytest.raises(ProductionError, match='relation_id must be unique'):
        accept_model_output(standardized,json.dumps(proposal))


def test_wiki_json_object_content_wrapper_keeps_body_validation(tmp_path):
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    proposal = json.loads(_model(standardized))
    proposal['knowledge'] = [proposal['knowledge'][1]]
    proposal['entities'] = []; proposal['relations'] = []
    wrapped = {'type':'json_object','content':proposal}
    accepted = accept_model_output(standardized, json.dumps(wrapped), stage='wiki')
    assert accepted['projection']['knowledge'][0]['kind'] == 'wiki'
    del proposal['knowledge'][0]['body']
    with pytest.raises(ProductionError, match='body'):
        accept_model_output(standardized, json.dumps(wrapped), stage='wiki')


def test_wiki_flat_knowledge_object_is_adapted_and_still_validated(tmp_path):
    """Real cached Wiki output is one flat knowledge object, not a three-list envelope."""
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    wiki = json.loads(_model(standardized))['knowledge'][1]
    flat = {'type': 'wiki'} | {key: wiki.get(key, []) for key in ('knowledge_id', 'title', 'language', 'kind', 'image_ids', 'citations', 'body')}
    accepted = accept_model_output(standardized, json.dumps(flat), stage='wiki')
    assert accepted['projection']['knowledge'][0]['knowledge_id'] == 'wiki-alpha-beta'
    assert accepted['projection']['knowledge'][0]['kind'] == 'wiki'
    assert accepted['projection']['entities'] == [] and accepted['projection']['relations'] == []

    for bad, match in (
        (flat | {'kind': 'article'}, 'wiki stage may only produce wiki knowledge'),
        (flat | {'body': '   '}, 'body'),
        (flat | {'citations': [{'revision_id': wiki['citations'][0]['revision_id'], 'locator': 'paragraph:1', 'quote': 'not in source'}]}, 'citation'),
    ):
        with pytest.raises(ProductionError, match=match):
            accept_model_output(standardized, json.dumps(bad), stage='wiki')


def test_inline_bank_ids_close_evidence_and_unknown_ids_reject_article(tmp_path):
    from vitax.production import _citation_bank
    standardized = standardize_documents(_input(tmp_path), capture_root=tmp_path)
    alpha = standardized['documents'][0]
    proposal = json.loads(_model(standardized))
    proposal['knowledge'] = [proposal['knowledge'][0]]
    proposal['relations'] = []
    identifier = _citation_bank({(alpha['revision_id'],'paragraph:1'):alpha['paragraphs'][0]['text']})[0]['citation_id']
    proposal['knowledge'][0]['body'] += '（'+identifier+'）'
    accepted = accept_model_output({'documents':[alpha]},json.dumps(proposal),stage='article')
    assert identifier in accepted['projection']['knowledge'][0]['evidence_ids']
    assert identifier in {e['evidence_id'] for e in accepted['projection']['evidence']}
    proposal['knowledge'][0]['body'] += ' evidence-'+'0'*20
    with pytest.raises(ProductionError,match='unknown citation'):
        accept_model_output({'documents':[alpha]},json.dumps(proposal),stage='article')
