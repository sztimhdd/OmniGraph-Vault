"""Unit tests for lib/checkpoint.py — Phase 12 foundation (CKPT-01/02/04).

Monkeypatches `lib.checkpoint.BASE_DIR` so no test touches real ~/.hermes state.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import pytest

from lib import checkpoint as ckpt


@pytest.fixture(autouse=True)
def _isolate_base(monkeypatch, tmp_path):
    fake_base = tmp_path / "omonigraph-vault"
    monkeypatch.setattr(ckpt, "BASE_DIR", fake_base)
    yield fake_base


# --- get_article_hash ------------------------------------------------------


def test_get_article_hash_deterministic():
    assert ckpt.get_article_hash("https://example.com") == ckpt.get_article_hash("https://example.com")


def test_get_article_hash_length_16():
    assert len(ckpt.get_article_hash("https://example.com")) == 16


def test_get_article_hash_sha256_not_md5():
    expected = hashlib.sha256(b"https://example.com").hexdigest()[:16]
    assert ckpt.get_article_hash("https://example.com") == expected


def test_get_article_hash_handles_unicode_url():
    # CJK characters in URL should hash cleanly
    assert len(ckpt.get_article_hash("https://例え.com/路径")) == 16


# --- get_checkpoint_dir ----------------------------------------------------


def test_get_checkpoint_dir_under_base():
    d = ckpt.get_checkpoint_dir("abc123")
    assert str(d).startswith(str(ckpt.BASE_DIR))
    assert "checkpoints" in str(d)
    assert "omonigraph" in str(d)


def test_get_checkpoint_dir_creates_parents():
    d = ckpt.get_checkpoint_dir("abc123")
    assert d.is_dir()
    # Idempotent
    d2 = ckpt.get_checkpoint_dir("abc123")
    assert d == d2


# --- STAGE_FILES schema ----------------------------------------------------


def test_stage_files_has_6_stages():
    assert set(ckpt.STAGE_FILES) == {
        "scrape",
        "classify",
        "image_download",
        "text_ingest",
        "vision_worker",
        "sub_doc_ingest",
    }


# --- write_stage / has_stage / read_stage ----------------------------------


def test_write_stage_scrape_atomic():
    h = "h1"
    ckpt.write_stage(h, "scrape", "<html>hi</html>")
    assert ckpt.has_stage(h, "scrape")
    assert ckpt.read_stage(h, "scrape") == "<html>hi</html>"
    # No .tmp remains
    d = ckpt.get_checkpoint_dir(h)
    assert not any(p.name.endswith(".tmp") for p in d.iterdir())


def test_write_stage_classify_atomic():
    h = "h2"
    payload = {"depth": 2, "topics": ["ai", "llm"], "rationale": "deep"}
    ckpt.write_stage(h, "classify", payload)
    assert ckpt.read_stage(h, "classify") == payload


def test_write_stage_classify_rejects_non_dict():
    with pytest.raises(TypeError):
        ckpt.write_stage("h", "classify", "not-a-dict")


def test_write_stage_image_manifest():
    h = "h3"
    manifest = [{"url": "https://x/1.png", "local_path": "a.png"}]
    ckpt.write_stage(h, "image_download", manifest)
    assert ckpt.has_stage(h, "image_download")
    assert ckpt.read_stage(h, "image_download") == manifest
    # Parent 03_images dir must be created
    assert (ckpt.get_checkpoint_dir(h) / "03_images").is_dir()


def test_write_stage_image_manifest_accepts_dict_wrapper():
    h = "h3a"
    manifest = [{"url": "x"}]
    ckpt.write_stage(h, "image_download", {"manifest": manifest})
    assert ckpt.read_stage(h, "image_download") == manifest


def test_write_stage_text_ingest_marker():
    h = "h4"
    ckpt.write_stage(h, "text_ingest")
    assert ckpt.has_stage(h, "text_ingest")
    assert ckpt.read_stage(h, "text_ingest") is True


def test_write_stage_sub_doc_ingest_marker():
    h = "h4b"
    ckpt.write_stage(h, "sub_doc_ingest")
    assert ckpt.has_stage(h, "sub_doc_ingest")
    assert ckpt.read_stage(h, "sub_doc_ingest") is True


def test_write_stage_rejects_unknown_stage():
    with pytest.raises(ValueError):
        ckpt.write_stage("h", "bogus", "x")


def test_write_stage_vision_worker_raises():
    # vision_worker is per-image; must use write_vision_description
    with pytest.raises(ValueError):
        ckpt.write_stage("h", "vision_worker", {"some": "data"})


def test_write_stage_atomic_no_partial_on_crash(monkeypatch):
    h = "hcrash"

    def boom(src, dst):
        raise OSError("simulated crash")

    # We patch os.replace (the actual atomic spelling used; see _atomic_write_bytes)
    # so the "crash during commit" simulation bypasses the pre-commit .tmp write.
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        ckpt.write_stage(h, "scrape", "<html/>")
    # No committed stage because replace failed
    assert ckpt.has_stage(h, "scrape") is False


def test_has_stage_matrix_absent():
    h = "hmissing"
    for stage in ckpt.STAGE_FILES:
        assert ckpt.has_stage(h, stage) is False


def test_has_stage_matrix_present():
    h = "hall"
    ckpt.write_stage(h, "scrape", "<html/>")
    ckpt.write_stage(h, "classify", {"depth": 1, "topics": [], "rationale": "x"})
    ckpt.write_stage(h, "image_download", [])
    ckpt.write_stage(h, "text_ingest")
    ckpt.write_vision_description(h, "img_0", {"provider": "siliconflow", "description": "d"})
    ckpt.write_stage(h, "sub_doc_ingest")
    for stage in ckpt.STAGE_FILES:
        assert ckpt.has_stage(h, stage) is True, f"stage {stage} should be present"


def test_has_stage_vision_requires_at_least_one_json():
    h = "hvis"
    (ckpt.get_checkpoint_dir(h) / "05_vision").mkdir(parents=True, exist_ok=True)
    assert ckpt.has_stage(h, "vision_worker") is False
    ckpt.write_vision_description(h, "img_0", {"provider": "x"})
    assert ckpt.has_stage(h, "vision_worker") is True


def test_read_stage_returns_none_if_absent():
    h = "habsent"
    for stage in ckpt.STAGE_FILES:
        assert ckpt.read_stage(h, stage) is None


def test_read_stage_vision_worker_returns_dict():
    h = "hvr"
    ckpt.write_vision_description(h, "img_0", {"provider": "siliconflow"})
    ckpt.write_vision_description(h, "img_1", {"provider": "gemini"})
    result = ckpt.read_stage(h, "vision_worker")
    assert set(result) == {"img_0.json", "img_1.json"}


# --- list_vision_markers (D-SUBDOC) ----------------------------------------


def test_list_vision_markers_empty_when_missing():
    assert ckpt.list_vision_markers("none") == []


def test_list_vision_markers_returns_ordered():
    h = "hlv"
    ckpt.write_vision_description(h, "img_b", {"provider": "b"})
    ckpt.write_vision_description(h, "img_a", {"provider": "a"})
    providers = [m["provider"] for m in ckpt.list_vision_markers(h)]
    assert providers == ["a", "b"]


# --- metadata --------------------------------------------------------------


def test_write_metadata_upsert():
    h = "hmeta"
    ckpt.write_metadata(h, {"url": "https://x", "title": "T1"})
    ckpt.write_metadata(h, {"last_completed_stage": "classify"})
    m = ckpt.read_metadata(h)
    assert m["url"] == "https://x"
    assert m["title"] == "T1"
    assert m["last_completed_stage"] == "classify"
    assert "created_at" in m and "updated_at" in m


def test_write_metadata_updates_updated_at():
    h = "hmetatime"
    ckpt.write_metadata(h, {"url": "u"})
    first = ckpt.read_metadata(h)["updated_at"]
    time.sleep(0.01)
    ckpt.write_metadata(h, {"title": "t"})
    second = ckpt.read_metadata(h)["updated_at"]
    assert second >= first


def test_read_metadata_missing_returns_empty_dict():
    assert ckpt.read_metadata("nope") == {}


# --- reset_article / reset_all ---------------------------------------------


def test_reset_article_removes_dir():
    h = "hrst"
    ckpt.write_stage(h, "scrape", "<p/>")
    assert ckpt.has_stage(h, "scrape")
    ckpt.reset_article(h)
    assert ckpt.has_stage(h, "scrape") is False


def test_reset_article_idempotent():
    ckpt.reset_article("never-existed")  # should not raise


def test_reset_all_removes_root():
    for h in ("a1", "a2"):
        ckpt.write_stage(h, "scrape", "<p/>")
    ckpt.reset_all()
    assert ckpt.list_checkpoints() == []


# --- list_checkpoints ------------------------------------------------------


def test_list_checkpoints_empty():
    assert ckpt.list_checkpoints() == []


def test_list_checkpoints_status_complete_vs_in_flight():
    # Article A: only scrape done -> in_flight
    ckpt.write_stage("ain", "scrape", "<p/>")
    ckpt.write_metadata("ain", {"url": "https://a", "title": "A"})
    # Article B: full pipeline including sub_doc_ingest -> complete
    for stage in ("scrape", "classify", "image_download", "text_ingest", "sub_doc_ingest"):
        if stage == "scrape":
            ckpt.write_stage("bdone", stage, "<p/>")
        elif stage == "classify":
            ckpt.write_stage("bdone", stage, {"depth": 1, "topics": [], "rationale": "x"})
        elif stage == "image_download":
            ckpt.write_stage("bdone", stage, [])
        else:
            ckpt.write_stage("bdone", stage)
    ckpt.write_metadata("bdone", {"url": "https://b", "title": "B"})

    records = {r["hash"]: r for r in ckpt.list_checkpoints()}
    assert records["ain"]["status"] == "in_flight"
    assert records["ain"]["last_stage"] == "scrape"
    assert records["bdone"]["status"] == "complete"
    assert records["bdone"]["last_stage"] == "sub_doc_ingest"
    assert records["bdone"]["url"] == "https://b"
    assert records["bdone"]["title"] == "B"
