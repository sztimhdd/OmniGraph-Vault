"""CLI-layer regression test for the 2026-06-25 --topic single-value bug (quick 260625-jv2).

Bug: batch_classify_kol.py main() declared --topic as a single-value required flag.
argparse is last-wins, so a systemd ExecStart passing
    --topic Agent --topic LLM --topic RAG --topic NLP --topic CV
collapsed to args.topic='CV' and run() was called ONCE -> only CV classified.
(Re-regression of quick 260507-ent, which fixed the DB-layer one-row-per-(article_id,topic).)

Fix under test: --topic uses action="append"; main() loops run() once per topic.

These tests pin the OBSERVABLE argparse->run contract (call-count + call-arg order), not
implementation shape. We dodge the import-time DEEPSEEK_API_KEY coupling
(config + lib eager imports) by seeding dummy keys before importing the module — the same
coupling-avoidance spirit as test_classifications_multitopic.py (which sidesteps the import
entirely via copied DDL; this test must import to drive main()).
"""
from __future__ import annotations

import os
import sys

# Defuse import-time DEEPSEEK_API_KEY / GEMINI_API_KEY coupling BEFORE importing the module.
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")
os.environ.setdefault("GEMINI_API_KEY", "dummy")

import batch_classify_kol  # noqa: E402  (import after env seed is intentional)


def _run_main_with(monkeypatch, argv: list[str]):
    """Drive main() with a fake CLI, run() mocked, DB existence forced True.
    Returns the mock for assertion on call-count / call-args."""
    import unittest.mock as mock

    mock_run = mock.MagicMock()
    monkeypatch.setattr(batch_classify_kol, "run", mock_run)
    # main() guards `if not DB_PATH.exists(): sys.exit(1)`. WindowsPath.exists is a
    # read-only slot and cannot be patched directly via monkeypatch.setattr on the
    # instance. Replace DB_PATH with a MagicMock whose exists() returns True instead.
    fake_db_path = mock.MagicMock()
    fake_db_path.exists.return_value = True
    monkeypatch.setattr(batch_classify_kol, "DB_PATH", fake_db_path)
    monkeypatch.setattr(sys, "argv", ["batch_classify_kol.py", *argv])
    batch_classify_kol.main()
    return mock_run


def test_multi_topic_runs_once_per_topic_in_order(monkeypatch) -> None:
    topics = ["Agent", "LLM", "RAG", "NLP", "CV"]
    argv = []
    for t in topics:
        argv += ["--topic", t]
    mock_run = _run_main_with(monkeypatch, argv)

    assert mock_run.call_count == len(topics), (
        f"each --topic flag must trigger one run() call; expected {len(topics)} "
        f"got {mock_run.call_count}"
    )
    # First positional arg of each call is the topic; pin order.
    called_topics = [c.args[0] for c in mock_run.call_args_list]
    assert called_topics == topics, (
        f"run() must be called once per topic in CLI order; got {called_topics}"
    )


def test_single_topic_backward_compatible(monkeypatch) -> None:
    mock_run = _run_main_with(monkeypatch, ["--topic", "Agent"])
    assert mock_run.call_count == 1, "single --topic must call run() exactly once"
    assert mock_run.call_args_list[0].args[0] == "Agent"


def test_non_topic_args_forwarded_to_run(monkeypatch) -> None:
    mock_run = _run_main_with(
        monkeypatch, ["--topic", "Agent", "--min-depth", "3", "--classifier", "gemini", "--dry-run"]
    )
    assert mock_run.call_count == 1
    # run(topic, min_depth, classifier, dry_run) — positional contract from line 369.
    (topic, min_depth, classifier, dry_run) = mock_run.call_args_list[0].args
    assert (topic, min_depth, classifier, dry_run) == ("Agent", 3, "gemini", True)
