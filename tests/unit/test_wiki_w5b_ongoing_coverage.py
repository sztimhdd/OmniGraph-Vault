"""W5B Task 2 behavior anchors: ongoing W3 coverage is successful-only + source-aware.

Production data shape at the hook boundary is a plain mapping::

    {"source": "wechat", "ref": "0123456789"}
    {"source": "rss", "ref": "abcdef0123"}

``ref`` is always the canonical 10-char lowercase ``md5(url)[:10]`` for BOTH
sources (design §6.1). ``rss_articles.content_hash`` is a 32-char body MD5
and is NEVER used as identity. Legacy direct callers may still pass bare
10-char refs; W3 resolves those across the local article index only when
unambiguous (Task 1 resolver), with a wechat ``articles.content_hash``
fallback for legacy content_hash-only fixtures.

Local-only constraint (design §4.6): no network, no LLM, no Tavily, no
Databricks import or call anywhere in this path.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from kb.wiki_articles import (
    SUPPORTED_ARTICLE_SOURCES,
    UnsupportedArticleSource,
    canonical_article_ref,
    live_ingestion_sources,
)
from kb.wiki_compiler.adapters import w3
from kb.wiki_compiler.models import EvidencePack


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _seed_source_db() -> sqlite3.Connection:
    """Source-aware fixture: articles + rss_articles with url/title columns.

    rss_articles carries a 32-char body ``content_hash`` that must never be
    treated as article identity.
    """
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE articles ("
        "id INTEGER PRIMARY KEY, title TEXT, url TEXT, content_hash TEXT)"
    )
    conn.execute(
        "CREATE TABLE rss_articles ("
        "id INTEGER PRIMARY KEY, title TEXT, url TEXT, summary TEXT, "
        "content_hash TEXT)"
    )
    return conn


def _seed_content_hash_only_db(hashes: list[str]) -> sqlite3.Connection:
    """Legacy W5A-style fixture: articles(content_hash) only, no url column."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE articles (content_hash TEXT PRIMARY KEY)")
    for h in hashes:
        conn.execute("INSERT INTO articles (content_hash) VALUES (?)", (h,))
    conn.commit()
    return conn


def _write_buffer(buf_dir: Path, ref: str, names: list[str]) -> None:
    buf_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": f"http://example.com/{ref}",
        "raw_entities": [{"name": n} for n in names],
        "timestamp": 0.0,
    }
    (buf_dir / f"{ref}_entities.json").write_text(json.dumps(payload), encoding="utf-8")


def _make_wiki(tmp_path: Path) -> Path:
    wiki = tmp_path / "wiki"
    (wiki / "entities").mkdir(parents=True, exist_ok=True)
    return wiki


# ---------------------------------------------------------------------------
# Step 2.1 (a): source-aware mapping resolution, RSS via canonical url ref
# ---------------------------------------------------------------------------


def test_source_aware_mapping_resolves_rss_via_canonical_url_ref(tmp_path):
    """RSS source-aware input resolves through rss_articles by md5(url)[:10]
    even when rss_articles.content_hash is an unrelated 32-char body MD5.

    The resulting EvidenceRef carries the canonical ref, the REAL local
    title, and source metadata — never the body hash.
    """
    conn = _seed_source_db()
    wx_url = "https://mp.weixin.qq.com/s/w5b-t2-wx"
    rss_url = "https://example.com/rss/w5b-t2"
    wx_ref = canonical_article_ref(wx_url)
    rss_ref = canonical_article_ref(rss_url)
    rss_body_hash = hashlib.md5(b"unrelated body text").hexdigest()  # 32 chars
    assert len(rss_body_hash) == 32 and rss_body_hash != rss_ref

    conn.execute(
        "INSERT INTO articles (id, title, url, content_hash) VALUES (1, ?, ?, ?)",
        ("WeChat Real Title", wx_url, wx_ref),
    )
    conn.execute(
        "INSERT INTO rss_articles (id, title, url, summary, content_hash) "
        "VALUES (1, ?, ?, ?, ?)",
        ("RSS Real Title", rss_url, "unrelated summary", rss_body_hash),
    )
    conn.commit()

    buf = tmp_path / "buf"
    _write_buffer(buf, wx_ref, ["Test Entity"])
    _write_buffer(buf, rss_ref, ["Test Entity"])
    wiki = _make_wiki(tmp_path)

    packs = w3.build_w3_evidence_packs(
        [
            {"source": "wechat", "ref": wx_ref},
            {"source": "rss", "ref": rss_ref},
        ],
        db_conn=conn,
        wiki_root=wiki,
        entity_buffer_dirs=[buf],
        min_frequency=2,
    )

    assert len(packs) == 1
    pack = packs[0]
    assert isinstance(pack, EvidencePack)
    by_ref = {e.ref: e for e in pack.evidence}
    # RSS evidence: canonical md5(url)[:10] ref, real local title, source metadata.
    assert by_ref[rss_ref].ref == rss_ref
    assert by_ref[rss_ref].title == "RSS Real Title"
    assert by_ref[rss_ref].metadata == {"source": "rss"}
    assert by_ref[rss_ref].provenance == "w3-entity-buffer"
    # WeChat evidence: same shape with its own source.
    assert by_ref[wx_ref].ref == wx_ref
    assert by_ref[wx_ref].title == "WeChat Real Title"
    assert by_ref[wx_ref].metadata == {"source": "wechat"}
    # The unrelated 32-char body MD5 is never an identity.
    assert rss_body_hash not in by_ref
    assert {e.ref for e in pack.evidence} == {wx_ref, rss_ref}
    # Any RSS evidence participates in the deterministic pack identity
    # (source-aware sha256 form, never the legacy refs-only form).
    material = "|".join(sorted(f"{s}:{r}" for s, r in (("rss", rss_ref), ("wechat", wx_ref))))
    assert pack.pack_id == f"w3-test-entity-{hashlib.sha256(material.encode()).hexdigest()[:16]}"
    assert pack.pack_id != f"w3-test-entity-{wx_ref}-{rss_ref}"


# ---------------------------------------------------------------------------
# Step 2.2: deterministic IDs — legacy all-WeChat parity + RSS non-alias
# ---------------------------------------------------------------------------


def test_all_wechat_legacy_id_unchanged_and_rss_collision_cannot_alias(tmp_path):
    """Deterministic identity rules:

    * an all-WeChat group keeps the legacy W5A pack_id AND patch_id
      byte-identical (title falls back to ref in the legacy content_hash-only
      fixture, so evidence content is unchanged too);
    * any RSS evidence switches the pack identity to a source-aware sha256
      form — two groups with the same ref SET but different source
      attribution must produce different pack_ids (no aliasing).
    """
    # --- Phase 1: legacy all-WeChat parity (W5A-era content_hash-only DB) ---
    conn = _seed_content_hash_only_db(["aaaaaaaaaa", "bbbbbbbbbb"])
    buf = tmp_path / "buf"
    _write_buffer(buf, "aaaaaaaaaa", ["Test Entity"])
    _write_buffer(buf, "bbbbbbbbbb", ["Test Entity"])
    wiki = _make_wiki(tmp_path)

    packs = w3.build_w3_evidence_packs(
        ["aaaaaaaaaa", "bbbbbbbbbb"],
        db_conn=conn,
        wiki_root=wiki,
        entity_buffer_dirs=[buf],
        min_frequency=2,
    )
    assert len(packs) == 1
    legacy_pack = w3.build_w3_pack_for_entity(
        "test-entity", ("aaaaaaaaaa", "bbbbbbbbbb"), wiki
    )
    assert packs[0].pack_id == legacy_pack.pack_id == (
        "w3-test-entity-aaaaaaaaaa-bbbbbbbbbb"
    )
    new_patch = w3.propose_w3_patch(packs[0], wiki_root=wiki)
    legacy_patch = w3.propose_w3_patch(legacy_pack, wiki_root=wiki)
    assert new_patch.patch_id == legacy_patch.patch_id

    # --- Phase 2: RSS collision non-alias ---
    conn2 = _seed_source_db()
    shared_url = "https://example.com/shared-article"
    other_url = "https://example.com/other-article"
    ref_x = canonical_article_ref(shared_url)
    ref_y = canonical_article_ref(other_url)
    # Same URL ingested under BOTH sources (realistic duplicate) + one more.
    for table, cols in (
        ("articles", ("id", "title", "url", "content_hash")),
        ("rss_articles", ("id", "title", "url", "summary", "content_hash")),
    ):
        if table == "articles":
            conn2.execute(
                f"INSERT INTO {table} (id, title, url, content_hash) "
                "VALUES (1, 'WX Shared', ?, ?)",
                (shared_url, ref_x),
            )
            conn2.execute(
                f"INSERT INTO {table} (id, title, url, content_hash) "
                "VALUES (2, 'WX Other', ?, ?)",
                (other_url, ref_y),
            )
        else:
            conn2.execute(
                f"INSERT INTO {table} (id, title, url, summary, content_hash) "
                "VALUES (1, 'RSS Shared', ?, 's', ?)",
                (
                    shared_url,
                    hashlib.md5(b"shared body").hexdigest(),
                ),
            )
            conn2.execute(
                f"INSERT INTO {table} (id, title, url, summary, content_hash) "
                "VALUES (2, 'RSS Other', ?, 's', ?)",
                (
                    other_url,
                    hashlib.md5(b"other body").hexdigest(),
                ),
            )
    conn2.commit()
    _write_buffer(buf, ref_x, ["Test Entity"])
    _write_buffer(buf, ref_y, ["Test Entity"])

    def _pack_id(*pairs):
        packs = w3.build_w3_evidence_packs(
            [{"source": s, "ref": r} for s, r in pairs],
            db_conn=conn2,
            wiki_root=wiki,
            entity_buffer_dirs=[buf],
            min_frequency=2,
        )
        assert len(packs) == 1, f"pairs {pairs!r} did not form exactly one pack"
        return packs[0].pack_id

    set1 = _pack_id(("wechat", ref_x), ("rss", ref_y))
    set2 = _pack_id(("wechat", ref_y), ("rss", ref_x))
    # Same ref SET, different source attribution: must NOT alias.
    assert set1 != set2
    # Determinism: the same logical set twice -> identical identity.
    assert _pack_id(("wechat", ref_x), ("rss", ref_y)) == set1
    # Source-aware sha256 form — never the legacy refs-only form.
    for pid in (set1, set2):
        assert pid.startswith("w3-test-entity-")
        assert pid != f"w3-test-entity-{ref_x}-{ref_y}"
        assert len(pid) == len("w3-test-entity-") + 16


# ---------------------------------------------------------------------------
# Step 2.1 (e/f) + 2.7: unknown source is explicit; min_frequency is
# distinct (source, ref) evidence
# ---------------------------------------------------------------------------


def test_unknown_source_explicit_failure_and_min_frequency_source_aware(tmp_path):
    """Unknown sources fail loudly (never a silent 0-pack success) and
    min_frequency counts distinct ``(source, ref)`` article evidence.

    A same-URL pair ingested under both sources counts 2 (design §6.2
    frequency is source-aware), where the legacy distinct-hash count saw 1.
    """
    wiki = _make_wiki(tmp_path)
    buf = tmp_path / "buf"

    # --- Phase 1: live ingestion sources audit (Step 2.7) ---
    conn = _seed_source_db()
    conn.execute(
        "CREATE TABLE ingestions ("
        "id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL, "
        "source TEXT NOT NULL DEFAULT 'wechat' "
        "CHECK (source IN ('wechat', 'rss')), "
        "status TEXT NOT NULL DEFAULT 'ok')"
    )
    conn.execute("INSERT INTO ingestions (article_id, source) VALUES (1, 'wechat')")
    conn.execute("INSERT INTO ingestions (article_id, source) VALUES (2, 'rss')")
    conn.commit()
    live = live_ingestion_sources(conn)
    assert live == {"wechat", "rss"}
    assert live <= set(SUPPORTED_ARTICLE_SOURCES)

    # --- Phase 2: unsupported source -> explicit failure (dedicated fixture
    # table bypasses the production CHECK; plan Step 2.7) ---
    conn2 = sqlite3.connect(":memory:")
    conn2.execute(
        "CREATE TABLE ingestions ("
        "id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL, "
        "source TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ok')"
    )
    conn2.execute("INSERT INTO ingestions (article_id, source) VALUES (1, 'other')")
    conn2.commit()
    assert "other" not in SUPPORTED_ARTICLE_SOURCES
    with pytest.raises(UnsupportedArticleSource):
        w3.build_w3_evidence_packs(
            [{"source": "other", "ref": "aaaaaaaaaa"}],
            db_conn=conn2,
            wiki_root=wiki,
            entity_buffer_dirs=[buf],
        )
    # Explicit failure family: ValueError, never a silent 0-pack success.
    with pytest.raises(ValueError):
        w3.build_w3_evidence_packs(
            [{"source": "other", "ref": "aaaaaaaaaa"}],
            db_conn=conn2,
            wiki_root=wiki,
            entity_buffer_dirs=[buf],
        )

    # --- Phase 3: min_frequency counts distinct (source, ref) pairs ---
    conn3 = _seed_source_db()
    shared_url = "https://example.com/minfreq-shared"
    ref = canonical_article_ref(shared_url)
    conn3.execute(
        "INSERT INTO articles (id, title, url, content_hash) VALUES (1, 'WX', ?, ?)",
        (shared_url, ref),
    )
    conn3.execute(
        "INSERT INTO rss_articles (id, title, url, summary, content_hash) "
        "VALUES (1, 'RSS', ?, 's', ?)",
        (shared_url, hashlib.md5(b"minfreq body").hexdigest()),
    )
    conn3.commit()
    _write_buffer(buf, ref, ["Test Entity"])

    packs = w3.build_w3_evidence_packs(
        [{"source": "wechat", "ref": ref}, {"source": "rss", "ref": ref}],
        db_conn=conn3,
        wiki_root=wiki,
        entity_buffer_dirs=[buf],
        min_frequency=2,
    )
    assert len(packs) == 1, (
        "same-URL both-sources pair must count as 2 distinct (source, ref) "
        "evidence at min_frequency=2"
    )
    assert {e.metadata["source"] for e in packs[0].evidence} == {"wechat", "rss"}
    # A single article alone never forms a pack at min_frequency=2.
    alone = w3.build_w3_evidence_packs(
        [{"source": "wechat", "ref": ref}],
        db_conn=conn3,
        wiki_root=wiki,
        entity_buffer_dirs=[buf],
        min_frequency=2,
    )
    assert alone == []
