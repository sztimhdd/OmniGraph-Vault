"""Offline contract tests for the VX-012A deterministic legacy import entry point.

All fixtures are synthetic. The tests never open runtime data, never touch the
network, and never call a model. The legacy tables are built from the sanitized
schema-contract fixture derived from the real three-host schema aggregation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import sqlite3
import stat
from pathlib import Path

import pytest

from vitax import knowledge
from vitax.legacy_migration import (
    MAX_SEARCH_LIMIT,
    LegacyImportError,
    current_candidate_dir,
    import_legacy_articles,
    load_import_records,
    read_candidate_record,
    search_candidate_records,
)

_CONTRACT_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "legacy_schema_contract.json"
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _contract() -> dict[str, object]:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def _wechat_row_one() -> dict[str, object]:
    """A fully translated KOL row with all three derived body variants."""
    return {
        "id": 1,
        "title": "Original title one",
        "url": "https://mp.weixin.qq.com/s/one",
        "body": "第一段正文。\n\n第二段正文。",
        "content_hash": "0123456789",
        "lang": "zh-CN",
        "update_time": 1777249680,
        "title_translated": "Translated title one",
        "body_translated": "First translated paragraph.\n\nSecond translated paragraph.",
        "translated_lang": "en",
        "body_cleaned": "Cleaned original body.",
        "body_repositioned": "Repositioned translated body.",
        "body_rewritten": "Rewritten display body.",
        "image_count": 2,
        "layer1_verdict": "candidate",
        "layer2_verdict": "ok",
    }


def _wechat_row_two() -> dict[str, object]:
    """A KOL row with no stored body and no translation (needs review)."""
    return {
        "id": 2,
        "title": "Original title two",
        "url": "https://mp.weixin.qq.com/s/two",
        "body": "",
        "lang": None,
        "update_time": 1777249681,
        "layer1_verdict": "candidate",
        "layer2_verdict": "ok",
    }


def _rss_row() -> dict[str, object]:
    """A fully translated RSS row with its own publish/fetch time fields."""
    return {
        "id": 7,
        "title": "RSS title",
        "url": "https://example.test/feed/7",
        "body": "RSS body text.",
        "content_hash": "abcdef0123456789",
        "lang": "en",
        "published_at": "2026-09-01T00:00:00+00:00",
        "fetched_at": "2026-09-01T01:00:00+00:00",
        "title_translated": "RSS 标题",
        "body_translated": "RSS 正文。",
        "translated_lang": "zh-CN",
        "body_cleaned": "Cleaned RSS body.",
        "body_rewritten": "Rewritten RSS body.",
        "layer1_verdict": "candidate",
        "layer2_verdict": "ok",
    }


def _wechat_row(record_id: int, **extra: object) -> dict[str, object]:
    """A minimal KOL row with a unique id/url, for denominator and slicing tests."""
    row: dict[str, object] = {
        "id": record_id,
        "title": f"Original title {record_id}",
        "url": f"https://mp.weixin.qq.com/s/{record_id}",
        "body": f"第{record_id}段正文。",
        "lang": "zh-CN",
        "update_time": 1777249700 + record_id,
        "layer1_verdict": "candidate",
        "layer2_verdict": "ok",
    }
    row.update(extra)
    return row


def _legacy_database(
    tmp_path: Path,
    *,
    articles: list[dict[str, object]] | None = None,
    rss: list[dict[str, object]] | None = None,
    ingestions: list[tuple[str, int, str]] | None = None,
    ingestions_table: bool = True,
    omit_columns: set[str] | None = None,
) -> Path:
    """Build a read-only export whose schema follows the schema-contract fixture.

    ``omit_columns`` drops columns from the built tables, so a test can simulate a
    remote export whose row keys lack a contract column.
    """
    contract = _contract()
    omitted = set(omit_columns or ())
    article_rows = [_wechat_row_one(), _wechat_row_two()] if articles is None else articles
    rss_rows = [_rss_row()] if rss is None else rss
    database = tmp_path / "legacy.sqlite"
    if database.exists():
        database.unlink()
    connection = sqlite3.connect(database)
    try:
        for source in ("wechat", "rss"):
            spec = contract["sources"][source]
            integers = set(spec["integer_columns"])
            definitions = ", ".join(
                f"{name} {'INTEGER' if name in integers else 'TEXT'}"
                for name in spec["columns"]
                if name not in omitted
            )
            connection.execute(f"CREATE TABLE {spec['table']} ({definitions})")
        for table, rows in (("articles", article_rows), ("rss_articles", rss_rows)):
            for row in rows:
                present = {name: value for name, value in row.items() if name not in omitted}
                columns = ", ".join(present)
                marks = ", ".join("?" for _ in present)
                connection.execute(
                    f"INSERT INTO {table} ({columns}) VALUES ({marks})", tuple(present.values())
                )
        if ingestions_table:
            connection.execute(
                "CREATE TABLE ingestions ("
                "id INTEGER PRIMARY KEY, source TEXT, article_id INTEGER, status TEXT)"
            )
            rows = ingestions
            if rows is None:
                rows = [
                    ("wechat", int(row["id"]), "ok") for row in article_rows
                ] + [("rss", int(row["id"]), "ok") for row in rss_rows]
            connection.executemany(
                "INSERT INTO ingestions (source, article_id, status) VALUES (?, ?, ?)", rows
            )
        connection.commit()
    finally:
        connection.close()
    return database


def _set_column(database: Path, table: str, record_id: int, column: str, value: object) -> None:
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            f"UPDATE {table} SET {column} = ? WHERE id = ?", (value, record_id)
        )
        connection.commit()
    finally:
        connection.close()


def _import(tmp_path: Path, **overrides: object) -> dict[str, object]:
    options: dict[str, object] = {
        "legacy_database": _legacy_database(tmp_path),
        "output_dir": tmp_path / "candidate",
        "source": "wechat",
        "limit": 1,
    }
    options.update(overrides)
    return import_legacy_articles(**options)  # type: ignore[arg-type]


def _store_dir(output_dir: Path) -> Path:
    """Directory that currently holds the committed candidate files."""
    directory = current_candidate_dir(output_dir)
    assert directory is not None, "candidate has no committed store"
    return directory


def _knowledge_bodies(output_dir: Path) -> list[str]:
    with knowledge.KnowledgeReader(_store_dir(output_dir) / "public-candidate.sqlite") as reader:
        return [row[0] for row in reader.connection.execute("SELECT body FROM knowledge")]


def test_records_preserve_original_and_translation_assets_separately(tmp_path: Path) -> None:
    """Breaks if the migration collapses original text into the translation asset."""
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=tmp_path / "candidate", source="wechat"
    )
    record = load_import_records(tmp_path / "candidate")[0]

    assert record["schema_version"] == 1
    assert record["original"]["title"] == "Original title one"
    assert record["original"]["text"] == "第一段正文。\n\n第二段正文。"
    assert record["translation"]["title"] == "Translated title one"
    assert record["translation"]["text"] == "First translated paragraph.\n\nSecond translated paragraph."
    assert record["translation"]["lang"] == "en"
    assert record["translation"]["provenance"] == {
        "origin": "legacy-store",
        "model": "unknown",
        "prompt_version": "unknown",
    }
    assert record["source"]["source"] == "wechat"
    assert record["source"]["source_ref"] == "articles:1"
    assert record["source"]["url"] == "https://mp.weixin.qq.com/s/one"
    assert record["source"]["identity_key"] == "wechat:" + hashlib.sha256(
        b"https://mp.weixin.qq.com/s/one"
    ).hexdigest()


def test_identity_ignores_legacy_content_hash(tmp_path: Path) -> None:
    """Breaks if source identity is inferred from a legacy content hash."""
    database = _legacy_database(tmp_path)
    import_legacy_articles(
        legacy_database=database, output_dir=tmp_path / "candidate", source="wechat", limit=1
    )
    store = _store_dir(tmp_path / "candidate") / "import-records.jsonl"
    before = load_import_records(tmp_path / "candidate")[0]
    before_bytes = store.read_bytes()

    _set_column(database, "articles", 1, "content_hash", "ffffffffff")
    import_legacy_articles(
        legacy_database=database, output_dir=tmp_path / "candidate", source="wechat", limit=1
    )
    second = load_import_records(tmp_path / "candidate")[0]

    assert second["source"]["identity_key"] == before["source"]["identity_key"]
    assert second["revision_id"] == before["revision_id"]
    assert second["migration"]["migration_version"] == 1
    assert store.read_bytes() == before_bytes


def test_unchanged_source_does_not_append_a_second_record(tmp_path: Path) -> None:
    """Breaks if re-running the same import duplicates logical articles."""
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=tmp_path / "candidate", source="wechat"
    )
    before = load_import_records(tmp_path / "candidate")

    summary = import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=tmp_path / "candidate", source="wechat"
    )

    assert summary["results"]["skipped"] == len(before)
    assert summary["results"]["imported"] == 0
    after = load_import_records(tmp_path / "candidate")
    assert len(after) == len(before)
    assert [item["original"] for item in after] == [item["original"] for item in before]
    assert [item["translation"] for item in after] == [item["translation"] for item in before]
    assert [item["revision_id"] for item in after] == [item["revision_id"] for item in before]


def test_unchanged_reimport_is_byte_identical_and_does_not_bump_version(tmp_path: Path) -> None:
    """Breaks if a no-op re-import rewrites the store or advances the version."""
    database = _legacy_database(tmp_path)
    output = tmp_path / "candidate"
    import_legacy_articles(legacy_database=database, output_dir=output, source="wechat")
    store = _store_dir(output) / "import-records.jsonl"
    before_bytes = store.read_bytes()
    before_versions = [r["migration"]["migration_version"] for r in load_import_records(output)]

    summary = import_legacy_articles(legacy_database=database, output_dir=output, source="wechat")

    assert summary["results"]["imported"] == 0
    assert summary["results"]["skipped"] == len(before_versions)
    assert store.read_bytes() == before_bytes
    after_versions = [r["migration"]["migration_version"] for r in load_import_records(output)]
    assert after_versions == before_versions


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Breaks if a preview mutates the candidate directory."""
    output = tmp_path / "candidate"
    summary = _import(tmp_path, output_dir=output, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["results"]["imported"] == 1
    assert not output.exists()


def test_migration_quality_and_publication_statuses_are_independent(tmp_path: Path) -> None:
    """Breaks if a quality review downgrade erases migration or publication state."""
    database = _legacy_database(tmp_path)
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=1, public=True
    )
    before = load_import_records(output)
    assert before[0]["migration"]["status"] == "imported"
    assert before[0]["publication"]["status"] == "public"

    import_legacy_articles(
        legacy_database=database,
        output_dir=output,
        source="wechat",
        limit=1,
        quality_override="needs-review",
    )

    after = load_import_records(output)
    assert len(after) == 1
    assert after[0]["migration"]["status"] == "imported"
    assert after[0]["quality"]["status"] == "needs-review"
    assert after[0]["publication"]["status"] == "public"
    assert after[0]["migration"]["migration_version"] == 2
    assert after[0]["revision_id"] == before[0]["revision_id"]


def test_different_content_revision_coexists_without_overwriting_human_content(tmp_path: Path) -> None:
    """Breaks if a newer content revision replaces an older, human-marked revision."""
    database = _legacy_database(tmp_path)
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=1, public=True
    )
    first = [r for r in load_import_records(output) if r["source"]["source_ref"] == "articles:1"][0]
    assert first["publication"]["status"] == "public"
    first_revision = first["revision_id"]

    _set_column(database, "articles", 1, "body", "修订后的正文。\n\n另一段。")
    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=1
    )

    assert summary["results"]["revised"] == 1
    revisions = [
        r for r in load_import_records(output) if r["source"]["source_ref"] == "articles:1"
    ]
    assert len(revisions) == 2
    old = [r for r in revisions if r["revision_id"] == first_revision][0]
    new = [r for r in revisions if r["revision_id"] != first_revision][0]
    assert old["original"]["text"] == "第一段正文。\n\n第二段正文。"
    assert old["publication"]["status"] == "public"
    assert old["migration"]["migration_version"] == 1
    assert new["original"]["text"] == "修订后的正文。\n\n另一段。"
    assert new["publication"]["status"] == "private"


def test_public_projection_is_a_strict_subset_of_publication_status(tmp_path: Path) -> None:
    """Breaks if private assets or an untranslated article leak into the public read model."""
    output = tmp_path / "candidate"
    summary = _import(tmp_path, output_dir=output, public=True, release_id="release-vx012a")
    database = _store_dir(output) / "public-candidate.sqlite"

    with knowledge.KnowledgeReader(database) as reader:
        knowledge_item = reader.read_knowledge(summary["public_knowledge_ids"][0])
        evidence = reader.read_evidence(knowledge_item["knowledge"]["evidence_ids"][0])
        bodies = [row[0] for row in reader.connection.execute("SELECT body FROM knowledge")]

    assert knowledge_item["release_id"] == "release-vx012a"
    assert knowledge_item["knowledge"]["kind"] == "article"
    assert knowledge_item["knowledge"]["title"] == "Translated title one"
    assert evidence["evidence"]["quote"] == "First translated paragraph."
    assert all("第一段正文" not in body for body in bodies)


def test_public_projection_requires_a_full_translation(tmp_path: Path) -> None:
    """Breaks if original text or a partial translation is published as the public body."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[
            {
                "id": 5,
                "title": "Original only",
                "url": "https://mp.weixin.qq.com/s/five",
                "body": "只有原文没有译文。",
                "lang": "zh-CN",
                "update_time": 1777249700,
                "layer1_verdict": "candidate",
                "layer2_verdict": "ok",
            },
            {
                "id": 6,
                "title": "Title only",
                "url": "https://mp.weixin.qq.com/s/six",
                "body": "原文正文。",
                "title_translated": "Translated title only",
                "translated_lang": "en",
                "update_time": 1777249701,
                "layer1_verdict": "candidate",
                "layer2_verdict": "ok",
            },
        ],
    )
    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=2, public=True
    )

    assert summary["public_records"] == 0
    records = load_import_records(output)
    assert [record["translation"]["completeness"] for record in records] == ["none", "title-only"]
    assert all(record["publication"]["status"] == "public" for record in records)
    assert _knowledge_bodies(output) == []


def test_quality_override_cannot_bypass_the_public_gate(tmp_path: Path) -> None:
    """Breaks if an explicit quality override can publish a not-qualified asset."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[
            {
                "id": 8,
                "title": "Untranslated",
                "url": "https://mp.weixin.qq.com/s/eight",
                "body": "原文正文内容。",
                "lang": "zh-CN",
                "update_time": 1777249800,
                "layer1_verdict": "candidate",
                "layer2_verdict": "ok",
            }
        ],
    )
    summary = import_legacy_articles(
        legacy_database=database,
        output_dir=output,
        source="wechat",
        limit=1,
        public=True,
        quality_override="passed",
    )

    record = load_import_records(output)[0]
    assert record["quality"]["status"] == "passed"
    assert record["quality"]["deterministic_status"] == "needs-review"
    assert record["publication"]["safety_qualification"]["status"] == "not-qualified"
    assert summary["public_records"] == 0
    assert _knowledge_bodies(output) == []


def test_private_records_never_produce_a_public_projection(tmp_path: Path) -> None:
    """Breaks if original text is published because a legacy store contained it."""
    output = tmp_path / "candidate"
    summary = _import(tmp_path, output_dir=output)

    assert summary["results"]["imported"] == 1
    assert summary["public_records"] == 0
    assert load_import_records(output)[0]["publication"]["status"] == "private"
    database = _store_dir(output) / "public-candidate.sqlite"
    assert database.exists()
    with knowledge.KnowledgeReader(database) as reader:
        assert reader.connection.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 0
        assert reader.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0


def test_zero_eligible_replaces_a_stale_public_database(tmp_path: Path) -> None:
    """Breaks if a run with no eligible records leaves a stale public read model."""
    output = tmp_path / "candidate"
    output.mkdir()
    (output / "public-candidate.sqlite").write_bytes(b"stale, not a database")

    summary = _import(tmp_path, output_dir=output)

    assert summary["public_records"] == 0
    database = _store_dir(output) / "public-candidate.sqlite"
    with knowledge.KnowledgeReader(database) as reader:
        assert reader.release_id == "vx012a-legacy-candidate"
        assert reader.connection.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0] == 0
    assert not list(output.glob(".*.tmp"))
    assert not list((output / "generations").glob(".*.tmp"))


def test_missing_translation_is_recorded_as_unknown_not_invented(tmp_path: Path) -> None:
    """Breaks if a missing translation is backfilled by a model or a heuristic."""
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path),
        output_dir=output,
        source="wechat",
        offset=1,
        limit=1,
    )
    record = load_import_records(output)[0]

    assert record["original"]["text"] == ""
    assert record["translation"]["title"] is None
    assert record["translation"]["text"] is None
    assert record["translation"]["completeness"] == "none"
    assert record["translation"]["lang"] == "unknown"
    assert record["translation"]["provenance"] == {
        "origin": "unknown",
        "model": "unknown",
        "prompt_version": "unknown",
    }
    assert record["quality"]["status"] == "needs-review"
    assert "missing-original-body" in record["quality"]["reason_codes"]


def test_body_variants_and_rss_publish_time_are_preserved(tmp_path: Path) -> None:
    """Breaks if adapter-available body variants or RSS publish time are dropped."""
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=output, source="wechat", limit=1
    )
    wechat = load_import_records(output)[0]
    assert wechat["original"]["variants"] == {
        "cleaned": "Cleaned original body.",
        "repositioned": "Repositioned translated body.",
        "rewritten": "Rewritten display body.",
    }
    assert wechat["source_published_at"] is None

    rss_output = tmp_path / "rss-candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=rss_output, source="rss", limit=1
    )
    rss = load_import_records(rss_output)[0]
    assert rss["source_published_at"] == "2026-09-01T00:00:00+00:00"
    assert rss["original"]["variants"] == {
        "cleaned": "Cleaned RSS body.",
        "repositioned": None,
        "rewritten": "Rewritten RSS body.",
    }


def test_row_adapter_never_calls_the_versioned_mapper_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if the row adapter depends on a host-versioned row-to-record helper.

    The 2026-09 remote read ran an older ``kb.data.article_query`` whose
    ``_row_to_record_*`` helpers ignored the optional columns, so rows that carried
    a stored translation were recorded as ``none``. The adapter must build the
    record from the selected row and never call those helpers.
    """
    from vitax import legacy_migration

    def fail(*_: object, **__: object) -> None:
        raise AssertionError("the row adapter must not call the _row_to_record_* helpers")

    # raising=False: the decoupled adapter no longer imports these names at all.
    monkeypatch.setattr(legacy_migration, "_row_to_record_kol", fail, raising=False)
    monkeypatch.setattr(legacy_migration, "_row_to_record_rss", fail, raising=False)

    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=output, source="wechat", limit=1
    )
    wechat = load_import_records(output)[0]
    assert wechat["translation"]["completeness"] == "full"
    assert wechat["translation"]["title"] == "Translated title one"
    assert wechat["translation"]["lang"] == "en"
    assert wechat["original"]["variants"] == {
        "cleaned": "Cleaned original body.",
        "repositioned": "Repositioned translated body.",
        "rewritten": "Rewritten display body.",
    }

    rss_output = tmp_path / "rss-candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path), output_dir=rss_output, source="rss", limit=1
    )
    rss = load_import_records(rss_output)[0]
    assert rss["source_published_at"] == "2026-09-01T00:00:00+00:00"
    assert rss["translation"]["title"] == "RSS 标题"
    assert rss["translation"]["lang"] == "zh-CN"
    assert rss["original"]["variants"] == {
        "cleaned": "Cleaned RSS body.",
        "repositioned": None,
        "rewritten": "Rewritten RSS body.",
    }


def test_row_without_translated_lang_keeps_translation_and_reports_unknown_language(
    tmp_path: Path,
) -> None:
    """Breaks if an absent translated_lang column drops stored translated text.

    The 2026-09 remote row keys carried title_translated/body_translated but no
    translated_lang at all; the record must stay ``full`` and report the language
    as ``unknown`` instead of degrading to ``none`` or inventing a language.
    """
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(tmp_path, omit_columns={"translated_lang"}),
        output_dir=output,
        source="wechat",
        limit=1,
    )
    record = load_import_records(output)[0]

    assert record["translation"]["title"] == "Translated title one"
    assert (
        record["translation"]["text"]
        == "First translated paragraph.\n\nSecond translated paragraph."
    )
    assert record["translation"]["completeness"] == "full"
    assert record["translation"]["lang"] == "unknown"
    assert record["translation"]["provenance"]["origin"] == "legacy-store"
    assert record["original"]["variants"]["rewritten"] == "Rewritten display body."


def test_null_translated_lang_keeps_translation_and_reports_unknown_language(
    tmp_path: Path,
) -> None:
    """Breaks if a NULL translated_lang erases stored translated text."""
    output = tmp_path / "candidate"
    import_legacy_articles(
        legacy_database=_legacy_database(
            tmp_path, articles=[{**_wechat_row_one(), "translated_lang": None}]
        ),
        output_dir=output,
        source="wechat",
        limit=1,
    )
    record = load_import_records(output)[0]

    assert record["translation"]["completeness"] == "full"
    assert record["translation"]["title"] == "Translated title one"
    assert record["translation"]["lang"] == "unknown"


def test_optional_overlay_only_targets_real_article_record_fields() -> None:
    """Breaks if the row overlay could try to set a field ArticleRecord lacks."""
    from dataclasses import fields

    from kb.data.article_query import ArticleRecord

    from vitax.legacy_migration import _OPTIONAL_RECORD_COLUMNS

    assert set(_OPTIONAL_RECORD_COLUMNS) <= {field.name for field in fields(ArticleRecord)}


def test_assets_and_provenance_are_explicitly_unknown(tmp_path: Path) -> None:
    """Breaks if unverifiable assets or provenance are omitted rather than marked unknown."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output)
    record = load_import_records(output)[0]

    assert record["assets"]["images"]["status"] == "unknown"
    assert record["assets"]["images"]["count"] == 2
    assert record["assets"]["provenance"]["status"] == "unknown"
    assert record["original"]["provenance"] == {"origin": "legacy-store"}


def test_import_never_opens_a_socket_or_calls_a_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if the deterministic entry point gains a network or LLM dependency."""

    def fail(*_: object, **__: object) -> None:
        raise AssertionError("the deterministic import entry point must not use the network")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)

    summary = _import(tmp_path)

    assert summary["llm_requests"] == 0
    assert summary["network_requests"] == 0


def test_import_requires_source_and_output_inside_an_existing_private_directory(tmp_path: Path) -> None:
    """Breaks if the entry point can be pointed at runtime data or a shared root."""
    with pytest.raises(LegacyImportError, match="source"):
        import_legacy_articles(
            legacy_database=_legacy_database(tmp_path),
            output_dir=tmp_path / "candidate",
            source="kol",
        )
    with pytest.raises(LegacyImportError, match="limit"):
        _import(tmp_path, limit=51)
    with pytest.raises(LegacyImportError, match="output"):
        _import(tmp_path, output_dir=tmp_path / "missing" / "candidate")


def test_records_are_append_only_and_readable_after_a_new_process(tmp_path: Path) -> None:
    """Breaks if the candidate store needs in-memory state to be re-read."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output)

    store = _store_dir(output)
    payload = (store / "import-records.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in payload.splitlines() if line]

    assert len(rows) == 1
    assert load_import_records(output) == rows
    manifest = json.loads((store / "import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["llm_requests"] == 0


def test_ingestion_status_filters_the_migration_denominator(tmp_path: Path) -> None:
    """Breaks if scanned/failed/skipped rows without a successful ingestion migrate."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[_wechat_row(1), _wechat_row(2), _wechat_row(3), _wechat_row(4)],
        ingestions=[
            ("wechat", 1, "failed"),
            ("wechat", 2, "skipped"),
            ("wechat", 3, "ok"),
            ("wechat", 4, "ok"),
        ],
    )

    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=5
    )

    assert summary["results"]["input"] == 2
    assert summary["results"]["imported"] == 2
    assert [r["source"]["source_ref"] for r in load_import_records(output)] == [
        "articles:3",
        "articles:4",
    ]


def test_limit_and_offset_apply_to_success_records_only(tmp_path: Path) -> None:
    """Breaks if pagination counts non-successful rows as part of the denominator."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[_wechat_row(1), _wechat_row(2), _wechat_row(3), _wechat_row(4)],
        ingestions=[
            ("wechat", 1, "failed"),
            ("wechat", 2, "ok"),
            ("wechat", 3, "skipped"),
            ("wechat", 4, "ok"),
        ],
    )

    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", offset=1, limit=1
    )

    assert summary["results"]["input"] == 1
    assert [r["source"]["source_ref"] for r in load_import_records(output)] == ["articles:4"]


def test_missing_ingestions_table_fails_explicitly(tmp_path: Path) -> None:
    """Breaks if a missing success denominator silently falls back to a whole-table read."""
    database = _legacy_database(tmp_path, ingestions_table=False)

    with pytest.raises(LegacyImportError, match="ingestions"):
        import_legacy_articles(
            legacy_database=database, output_dir=tmp_path / "candidate", source="wechat"
        )


def test_schema_contract_fixture_is_sanitized_and_covers_both_sources() -> None:
    """Breaks if the schema contract carries data, or drops a source contract."""
    contract = _contract()
    assert set(contract["sources"]) == {"wechat", "rss"}
    raw = _CONTRACT_PATH.read_text(encoding="utf-8")
    assert "://" not in raw
    for source, spec in contract["sources"].items():
        assert spec["columns"]
        for column in spec["columns"]:
            assert _IDENTIFIER.match(column), (source, column)
        assert set(contract["required_columns"]) <= set(spec["columns"])
        for column in spec["translation_fields"]:
            assert column in spec["columns"], (source, column)
        for column in spec["body_variant_fields"]:
            assert column in spec["columns"], (source, column)
        time_columns = [value for value in spec["time_fields"].values() if value is not None]
        assert time_columns
        for column in time_columns:
            assert column in spec["columns"], (source, column)
    assert contract["sources"]["wechat"]["time_fields"]["source_updated_at"] == "update_time"
    assert contract["sources"]["rss"]["time_fields"]["source_published_at"] == "published_at"
    assert contract["sources"]["rss"]["time_fields"]["fetched_at"] == "fetched_at"
    assert "body_repositioned" in contract["sources"]["wechat"]["body_variant_fields"]
    assert "body_repositioned" not in contract["sources"]["rss"]["body_variant_fields"]


def test_schema_contract_fixture_matches_the_adapter_column_contract() -> None:
    """Breaks if the adapter reads columns that the real schema aggregation lacks."""
    from vitax.legacy_migration import _OPTIONAL_COLUMNS, _REQUIRED_COLUMNS

    contract = _contract()
    assert set(_REQUIRED_COLUMNS) == set(contract["required_columns"])
    declared = set()
    for spec in contract["sources"].values():
        declared |= set(spec["columns"])
    assert set(_OPTIONAL_COLUMNS) <= declared
    assert set(_REQUIRED_COLUMNS) <= declared


_POSIX_ONLY = pytest.mark.skipif(
    os.name != "posix", reason="POSIX permission bits are unavailable on this platform"
)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@_POSIX_ONLY
def test_candidate_directory_and_files_are_owner_only(tmp_path: Path) -> None:
    """Breaks if the private candidate store is created world-readable."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output)

    assert _mode(output) == 0o700
    generations = output / "generations"
    assert _mode(generations) == 0o700
    store = _store_dir(output)
    assert store.parent == generations
    assert _mode(store) == 0o700
    for name in ("import-records.jsonl", "import-manifest.json", "public-candidate.sqlite"):
        assert _mode(store / name) == 0o600, name
    assert _mode(output / "current") == 0o600


@_POSIX_ONLY
def test_existing_loose_candidate_directory_is_tightened_to_owner_only(tmp_path: Path) -> None:
    """Breaks if a pre-existing group/other-readable candidate directory is trusted as-is."""
    output = tmp_path / "candidate"
    output.mkdir()
    os.chmod(output, 0o755)

    _import(tmp_path, output_dir=output)

    assert _mode(output) == 0o700
    assert _mode(_store_dir(output) / "import-records.jsonl") == 0o600


@_POSIX_ONLY
def test_group_or_other_writable_candidate_directory_is_rejected(tmp_path: Path) -> None:
    """Breaks if a candidate directory anyone can write is accepted as a private store."""
    output = tmp_path / "candidate"
    output.mkdir()
    os.chmod(output, 0o777)

    with pytest.raises(LegacyImportError, match="writable"):
        _import(tmp_path, output_dir=output)
    assert not (output / "import-records.jsonl").exists()


def test_concurrent_import_of_the_same_candidate_is_rejected(tmp_path: Path) -> None:
    """Breaks if two batches can read-modify-write the same candidate at once."""
    from vitax.legacy_migration import _candidate_lock

    output = tmp_path / "candidate"
    database = _legacy_database(tmp_path)
    import_legacy_articles(legacy_database=database, output_dir=output, source="wechat", limit=1)
    store = _store_dir(output) / "import-records.jsonl"
    before = store.read_bytes()

    with _candidate_lock(output):
        with pytest.raises(LegacyImportError, match="lock"):
            import_legacy_articles(
                legacy_database=database, output_dir=output, source="wechat", limit=1
            )

    assert store.read_bytes() == before


def test_one_failing_record_does_not_abort_the_rest_of_the_batch(tmp_path: Path) -> None:
    """Breaks if a single unconvertible row fails the whole batch instead of being recorded."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[
            _wechat_row(1),
            {**_wechat_row(2), "url": ""},  # no source URL -> build_record raises
            _wechat_row(3),
        ],
    )

    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=5
    )

    assert summary["results"]["input"] == 3
    assert summary["results"]["imported"] == 2
    assert summary["results"]["failed"] == 1
    assert [entry["source_ref"] for entry in summary["failures"]] == ["articles:2"]
    assert [r["source"]["source_ref"] for r in load_import_records(output)] == [
        "articles:1",
        "articles:3",
    ]


def test_failed_record_is_persisted_with_a_bounded_reason(tmp_path: Path) -> None:
    """Breaks if a failure is counted without a durable, bounded reason next to the records."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path, articles=[_wechat_row(1), {**_wechat_row(2), "url": ""}]
    )

    summary = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=5
    )

    entry = summary["failures"][0]
    assert entry["state"] == "failed"
    assert entry["source_ref"] == "articles:2"
    assert entry["reason"] and len(entry["reason"]) <= 300
    store = _store_dir(output)
    persisted = [
        json.loads(line)
        for line in (store / "import-failures.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert persisted == summary["failures"]
    manifest = json.loads((store / "import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["failure_count"] == 1
    assert manifest["summary"]["results"]["failed"] == 1


def test_rerun_retries_only_the_failed_records(tmp_path: Path) -> None:
    """Breaks if a repaired row is never retried, or a good row is re-imported."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path, articles=[_wechat_row(1), {**_wechat_row(2), "url": ""}]
    )
    first = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=5
    )
    assert first["results"]["failed"] == 1
    before = {r["source"]["source_ref"]: r for r in load_import_records(output)}

    _set_column(database, "articles", 2, "url", "https://mp.weixin.qq.com/s/two")
    second = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=5
    )

    assert second["results"]["imported"] == 1
    assert second["results"]["skipped"] == 1
    assert second["results"]["failed"] == 0
    assert second["failures"] == []
    assert (
        _store_dir(output) / "import-failures.jsonl"
    ).read_text(encoding="utf-8").strip() == ""
    after = {r["source"]["source_ref"]: r for r in load_import_records(output)}
    assert after["articles:1"] == before["articles:1"]
    assert sorted(after) == ["articles:1", "articles:2"]


def test_public_projection_failure_keeps_the_previous_batch_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Breaks if records/manifest are committed before the public read model is buildable."""
    from vitax import legacy_migration

    output = tmp_path / "candidate"
    database = _legacy_database(tmp_path)
    import_legacy_articles(legacy_database=database, output_dir=output, source="wechat", limit=1)
    store = _store_dir(output)
    tracked = [
        store / name
        for name in ("import-records.jsonl", "import-failures.jsonl", "import-manifest.json")
    ]
    before = {path.name: path.read_bytes() for path in tracked}

    def fail(*_: object, **__: object) -> None:
        raise knowledge.KnowledgeError("forced public projection failure")

    monkeypatch.setattr(legacy_migration, "build", fail)
    _set_column(database, "articles", 1, "body", "修订后的正文。")

    with pytest.raises(LegacyImportError):
        import_legacy_articles(
            legacy_database=database, output_dir=output, source="wechat", limit=1
        )

    assert {path.name: path.read_bytes() for path in tracked} == before
    assert not list(output.glob(".*.tmp"))
    assert not list((output / "generations").glob(".*.tmp"))


def test_commit_writes_one_generation_named_by_the_current_pointer(tmp_path: Path) -> None:
    """Breaks if a commit spreads the batch across the flat candidate paths."""
    output = tmp_path / "candidate"
    summary = _import(tmp_path, output_dir=output)

    pointer = output / "current"
    assert pointer.is_file()
    assert pointer.read_text(encoding="utf-8").strip() == summary["generation"]
    store = output / "generations" / summary["generation"]
    assert store.is_dir()
    for name in (
        "import-records.jsonl",
        "import-failures.jsonl",
        "import-manifest.json",
        "public-candidate.sqlite",
    ):
        assert (store / name).is_file(), name
        # A new commit never writes the flat paths that an older reader used.
        assert not (output / name).exists(), name
    assert load_import_records(output) == load_import_records(store)
    assert _store_dir(output) == store

    manifest = json.loads((store / "import-manifest.json").read_text(encoding="utf-8"))
    assert manifest["generation"] == summary["generation"]
    assert set(manifest["generation_files"]) == {
        "import-records.jsonl",
        "import-failures.jsonl",
        "public-candidate.sqlite",
    }
    for name, digest in manifest["generation_files"].items():
        assert hashlib.sha256((store / name).read_bytes()).hexdigest() == digest


def test_reader_rejects_a_generation_that_does_not_match_its_manifest(tmp_path: Path) -> None:
    """Breaks if a tampered or half-written generation is read instead of refused."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output)
    records = _store_dir(output) / "import-records.jsonl"

    records.write_bytes(records.read_bytes() + b"\n")
    with pytest.raises(LegacyImportError, match="manifest"):
        load_import_records(output)

    (output / "current").write_text("0000deadbeef\n", encoding="utf-8")
    with pytest.raises(LegacyImportError, match="missing generation"):
        load_import_records(output)


def test_reader_uses_the_current_generation_not_flat_leftovers(tmp_path: Path) -> None:
    """Breaks if stray flat files are mixed into the generation the pointer names."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output)
    committed = load_import_records(output)

    (output / "import-records.jsonl").write_text(
        json.dumps({"revision_id": "stale-flat-record"}) + "\n", encoding="utf-8"
    )

    assert load_import_records(output) == committed
    assert [record["source"]["source_ref"] for record in load_import_records(output)] == [
        "articles:1"
    ]


def test_legacy_flat_candidate_is_still_readable(tmp_path: Path) -> None:
    """Breaks if a candidate written before the generation layout stops being read."""
    output = tmp_path / "candidate"
    output.mkdir()
    legacy_record = {"revision_id": "vx012a-legacy"}
    (output / "import-records.jsonl").write_text(
        json.dumps(legacy_record) + "\n", encoding="utf-8"
    )

    assert load_import_records(output) == [legacy_record]
    assert current_candidate_dir(output) == output


def test_import_upgrades_a_legacy_flat_candidate_without_losing_records(tmp_path: Path) -> None:
    """Breaks if an older on-disk candidate is ignored or dropped when the layout changes."""
    output = tmp_path / "candidate"
    database = _legacy_database(tmp_path, articles=[_wechat_row(1), _wechat_row(2)])
    import_legacy_articles(legacy_database=database, output_dir=output, source="wechat", limit=1)
    flat_records = (_store_dir(output) / "import-records.jsonl").read_bytes()

    # Re-materialize the committed generation as a pre-generation flat candidate.
    shutil.rmtree(output / "generations")
    (output / "current").unlink()
    (output / "import-records.jsonl").write_bytes(flat_records)
    assert [record["source"]["source_ref"] for record in load_import_records(output)] == [
        "articles:1"
    ]

    import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", offset=1, limit=1
    )

    assert (output / "current").is_file()
    assert sorted(record["source"]["source_ref"] for record in load_import_records(output)) == [
        "articles:1",
        "articles:2",
    ]


def test_current_batch_failure_count_excludes_other_offsets(tmp_path: Path) -> None:
    """Breaks if a clean batch inherits an unresolved failure from another offset."""
    output = tmp_path / "candidate"
    database = _legacy_database(
        tmp_path,
        articles=[{**_wechat_row(1), "url": ""}, _wechat_row(2), _wechat_row(3)],
    )

    first = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", offset=0, limit=1
    )
    assert first["results"]["failed"] == 1
    assert first["results"]["outstanding_failed"] == 1
    assert [entry["source_ref"] for entry in first["batch_failures"]] == ["articles:1"]
    assert [entry["source_ref"] for entry in first["failures"]] == ["articles:1"]

    second = import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", offset=1, limit=1
    )
    # This batch imported a clean row, so its own failure count is zero even though
    # the candidate still carries the earlier offset's unresolved failure.
    assert second["results"]["failed"] == 0
    assert second["results"]["outstanding_failed"] == 1
    assert second["batch_failures"] == []
    assert [entry["source_ref"] for entry in second["failures"]] == ["articles:1"]

    manifest = json.loads(
        (_store_dir(output) / "import-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["batch_failure_count"] == 0
    assert manifest["failure_count"] == 1


def _private_candidate(tmp_path: Path) -> Path:
    """A committed candidate with one translated row and one untranslated row."""
    output = tmp_path / "candidate"
    database = _legacy_database(tmp_path, articles=[_wechat_row_one(), _wechat_row_two()])
    import_legacy_articles(
        legacy_database=database, output_dir=output, source="wechat", limit=2
    )
    return output


def _revision_by_source_ref(output: Path) -> dict[str, str]:
    return {
        record["source"]["source_ref"]: record["revision_id"]
        for record in load_import_records(output)
    }


def test_search_matches_title_original_and_translation_text_case_insensitively(
    tmp_path: Path,
) -> None:
    """Breaks if a search inspects one text field only or compares case-sensitively."""
    output = _private_candidate(tmp_path)
    revisions = _revision_by_source_ref(output)
    assert set(revisions) == {"articles:1", "articles:2"}

    def hits(query: str) -> list[str]:
        return [item["revision_id"] for item in search_candidate_records(output, query)]

    # Original title, original body, translated title, and translated body all match.
    assert hits("ORIGINAL TITLE TWO") == [revisions["articles:2"]]
    assert hits("第二段正文") == [revisions["articles:1"]]
    assert hits("Translated Title ONE") == [revisions["articles:1"]]
    assert hits("first translated paragraph") == [revisions["articles:1"]]
    # A term that appears nowhere returns no rows rather than an error.
    assert hits("no-such-text") == []


def test_search_results_are_stable_summaries_of_the_private_records(tmp_path: Path) -> None:
    """Breaks if a result page is unordered, unstable, or carries the whole record."""
    output = _private_candidate(tmp_path)
    revisions = _revision_by_source_ref(output)

    results = search_candidate_records(output, "title")

    # Ordered by title, then revision id, so the same query returns the same page.
    assert [item["title"] for item in results] == ["Original title one", "Original title two"]
    assert [item["revision_id"] for item in results] == [
        revisions["articles:1"],
        revisions["articles:2"],
    ]
    assert search_candidate_records(output, "title") == results
    assert set(results[0]) == {
        "revision_id",
        "title",
        "quality",
        "translation",
        "publication",
        "source",
    }
    assert results[0]["source"]["source_ref"] == "articles:1"
    assert results[0]["quality"]["deterministic_status"] == "passed"
    assert results[0]["translation"]["completeness"] == "full"
    assert results[0]["publication"]["status"] == "private"


def test_search_limit_defaults_to_twenty_and_caps_the_page(tmp_path: Path) -> None:
    """Breaks if the search page size is unbounded or leaves the documented default."""
    import inspect

    assert inspect.signature(search_candidate_records).parameters["limit"].default == 20

    output = _private_candidate(tmp_path)
    assert len(search_candidate_records(output, "title", limit=1)) == 1
    assert len(search_candidate_records(output, "title")) == 2
    assert len(search_candidate_records(output, "title", limit=MAX_SEARCH_LIMIT)) == 2
    # A directory with nothing committed is an empty page, not an error.
    assert search_candidate_records(tmp_path / "empty", "title") == []


@pytest.mark.parametrize("query", ["", "   ", "\n"])
def test_search_rejects_an_empty_query(tmp_path: Path, query: str) -> None:
    """Breaks if an empty query returns the whole store instead of being refused."""
    output = _private_candidate(tmp_path)

    with pytest.raises(LegacyImportError, match="query"):
        search_candidate_records(output, query)


@pytest.mark.parametrize("limit", [0, -1, MAX_SEARCH_LIMIT + 1])
def test_search_rejects_a_limit_outside_the_contract(tmp_path: Path, limit: int) -> None:
    """Breaks if a caller can request a non-positive or unbounded page."""
    output = _private_candidate(tmp_path)

    with pytest.raises(LegacyImportError, match="limit"):
        search_candidate_records(output, "title", limit=limit)


def test_read_returns_the_full_private_record_with_source_provenance(tmp_path: Path) -> None:
    """Breaks if the single-record read drops preserved text or source provenance."""
    output = _private_candidate(tmp_path)
    stored = {record["revision_id"]: record for record in load_import_records(output)}
    revision_id = _revision_by_source_ref(output)["articles:1"]

    record = read_candidate_record(output, revision_id)

    assert record == stored[revision_id]
    assert record["original"]["title"] == "Original title one"
    assert record["original"]["text"] == "第一段正文。\n\n第二段正文。"
    assert record["translation"]["text"] == (
        "First translated paragraph.\n\nSecond translated paragraph."
    )
    assert record["source"]["source_ref"] == "articles:1"
    assert record["source"]["url"] == "https://mp.weixin.qq.com/s/one"
    assert record["source"]["identity_key"].startswith("wechat:")
    assert record["quality"]["deterministic_status"] == "passed"
    assert record["publication"]["status"] == "private"


def test_read_returns_private_content_and_never_the_public_projection(tmp_path: Path) -> None:
    """Breaks if the private read hands back the translated public projection instead."""
    output = tmp_path / "candidate"
    _import(tmp_path, output_dir=output, public=True)
    stored = load_import_records(output)[0]
    assert stored["publication"]["safety_qualification"]["status"] == "qualified"
    # The public projection exists and carries the translation only.
    assert _knowledge_bodies(output) == ["First translated paragraph.\n\nSecond translated paragraph."]

    record = read_candidate_record(output, stored["revision_id"])

    assert record == stored
    assert record["original"]["text"] == "第一段正文。\n\n第二段正文。"
    # No public-projection keys leak into the private record.
    assert "visibility" not in record
    assert "knowledge_id" not in record
    assert "body" not in record


def test_read_rejects_a_missing_or_empty_revision_id(tmp_path: Path) -> None:
    """Breaks if a missing record resolves to a guess or an empty value instead."""
    output = _private_candidate(tmp_path)

    with pytest.raises(LegacyImportError, match="revision_id"):
        read_candidate_record(output, "vx012a-does-not-exist")
    with pytest.raises(LegacyImportError, match="revision_id"):
        read_candidate_record(output, "")
    with pytest.raises(LegacyImportError, match="revision_id"):
        read_candidate_record(tmp_path / "empty", "vx012a-anything")


def test_search_and_read_leave_the_committed_candidate_bytes_unchanged(tmp_path: Path) -> None:
    """Breaks if a read path rewrites, restages, or reorders the private candidate."""
    output = _private_candidate(tmp_path)
    store = _store_dir(output)

    def digest() -> dict[str, str]:
        return {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(store.iterdir())
        }

    before = digest()
    pointer_before = (output / "current").read_bytes()

    search_candidate_records(output, "title")
    read_candidate_record(output, _revision_by_source_ref(output)["articles:1"])

    assert digest() == before
    assert (output / "current").read_bytes() == pointer_before
    assert [path.name for path in (output / "generations").iterdir()] == [store.name]
