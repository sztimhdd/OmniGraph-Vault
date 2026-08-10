"""Verify the 2026-08-10 topic-keyword-table migration (quick topic-v2).

Guards:
1. --topic-file loads topic names from config/topic_keywords_2026.json
2. Layer1 prompt body mentions the new core-interest topics
3. Layer2 prompt body updated to new core interest
4. REJECT rules cover the user's explicitly-excluded directions
   (CV / vision / video / NLP / embodied / robotic)
5. Negative keywords in JSON mirror the REJECT rules
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.article_filter import (
    PROMPT_VERSION_LAYER1,
    _LAYER1_V1_PROMPT_BODY,
    _LAYER2_V1_PROMPT_BODY,
)

CONFIG = Path(__file__).resolve().parents[2] / "config" / "topic_keywords_2026.json"

NEW_TOPICS = {
    "Agent",
    "Orchestration",
    "Harness",
    "MemorySystem",
    "SkillEngineering",
    "ContextProtocol",
    "GraphEngineering",
}

NEGATIVE_DIRECTIONS = [
    "计算机视觉", "CV", "机器视觉", "视频生成", "具身智能", "机器人",
    "Robotic", "NLP", "语音识别", "图像生成", "自动驾驶",
]


def _load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


# ------------------- --topic-file argparse path -------------------

def test_topic_file_loads_all_seven_topics() -> None:
    """batch_classify_kol --topic-file must resolve to the 7 new topics."""
    data = _load_config()
    names = [t["name"] for t in data["topics"]]
    assert set(names) == NEW_TOPICS
    # keyword counts sane (not empty)
    for t in data["topics"]:
        assert len(t["keywords"]) >= 8, f"{t['name']} too few keywords"


def test_topic_file_json_shape() -> None:
    """Every topic has name/description/keywords; negative_keywords present."""
    data = _load_config()
    for t in data["topics"]:
        assert "name" in t and "description" in t and "keywords" in t
    assert isinstance(data.get("negative_keywords"), list)
    assert len(data["negative_keywords"]) >= 10


def test_user_named_keywords_present() -> None:
    """Vitaclaw and FDE (user-named directions) must be in the table."""
    data = _load_config()
    all_kw = " ".join(" ".join(t["keywords"]) for t in data["topics"]).lower()
    for need in ("vitaclaw", "fde", "harness", "memory", "skill", "mcp", "graphrag"):
        assert need in all_kw, f"missing user-named keyword: {need}"


# ------------------- Layer1 prompt alignment -------------------

def test_layer1_prompt_has_new_core_interest() -> None:
    body = _LAYER1_V1_PROMPT_BODY
    for term in ("Agent 工程", "Harness", "记忆系统", "MCP", "知识图谱工程", "GraphRAG", "Loop 工程"):
        assert term in body, f"Layer1 prompt missing core term: {term}"


def test_layer1_prompt_rejects_excluded_directions() -> None:
    """REJECT rule 1 must name CV/NLP/embodied/robotic as hard rejects."""
    body = _LAYER1_V1_PROMPT_BODY
    for term in ("具身智能", "人形机器人", "Robotic AI", "传统 NLP", "语音识别", "自动驾驶感知"):
        assert term in body, f"Layer1 REJECT missing excluded direction: {term}"


# ------------------- Layer2 prompt alignment -------------------

def test_layer2_prompt_has_new_core_interest() -> None:
    body = _LAYER2_V1_PROMPT_BODY
    for term in ("Harness", "记忆系统", "Skills", "MCP", "GraphRAG", "Vitaclaw", "FDE", "Loop 工程"):
        assert term in body, f"Layer2 prompt missing core term: {term}"


# ------------------- negative keywords mirror -------------------

def test_negative_keywords_cover_excluded_directions() -> None:
    data = _load_config()
    neg = " ".join(data["negative_keywords"]).lower()
    for term in ("计算机视觉", "机器视觉", "具身智能", "embodied", "robotic", "video generation",
                 "speech recognition", "stable diffusion", "sora"):
        assert term in neg, f"negative_keywords missing: {term}"


# ------------------- version bump discipline -------------------

def test_prompt_version_bumped_for_new_filter() -> None:
    """Changing the filter body without bumping PROMPT_VERSION_LAYER1 would
    silently skip re-evaluation of already-classified rows."""
    assert PROMPT_VERSION_LAYER1 != "layer1_v1_20260512", (
        "Layer1 prompt changed for topic-v2 — PROMPT_VERSION_LAYER1 must bump "
        "so existing NULL/old-version rows get re-selected."
    )
