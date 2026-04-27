"""Unit tests for enrichment.merge_md."""
import pytest
from enrichment.merge_md import merge_wechat_with_haowen


@pytest.mark.unit
def test_merge_appends_knowledge_section():
    md = "# article\nbody text"
    haowen = [{"question": "q1", "summary": "s1", "best_source_url": "http://a"}]
    out = merge_wechat_with_haowen(md, haowen)
    assert "# article" in out
    assert "body text" in out
    assert "## 知识增厚" in out
    assert "### 问题 1: q1" in out
    assert "s1" in out
    assert "http://a" in out


@pytest.mark.unit
def test_merge_preserves_question_index_with_none_gap():
    md = "orig"
    haowen = [
        {"question": "q1", "summary": "s1", "best_source_url": "http://a"},
        None,  # q2 failed
        {"question": "q3", "summary": "s3", "best_source_url": "http://c"},
    ]
    out = merge_wechat_with_haowen(md, haowen)
    # Index label reflects position in the original list, not the filtered one
    assert "### 问题 1: q1" in out
    assert "### 问题 2:" not in out   # q2 skipped
    assert "### 问题 3: q3" in out


@pytest.mark.unit
def test_merge_all_failed_appends_empty_footer():
    md = "orig"
    out = merge_wechat_with_haowen(md, [None, None, None])
    assert "## 知识增厚" in out
    assert "未找到相关的知乎问答" in out
    assert out.startswith("orig")


@pytest.mark.unit
def test_merge_empty_list_treated_as_all_failed():
    out = merge_wechat_with_haowen("orig", [])
    assert "未找到相关的知乎问答" in out


@pytest.mark.unit
def test_merge_handles_missing_fields():
    md = "orig"
    haowen = [{"question": "q1"}]  # no summary, no url
    out = merge_wechat_with_haowen(md, haowen)
    assert "### 问题 1: q1" in out
    # Should not crash, should not emit broken "来源: " line with empty URL
    assert "来源: \n" not in out
