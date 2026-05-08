"""Synthesize answers from already-ingested OmniGraph docs without Gemini.

This is a deployment-safe fallback for environments where Gemini embedding or
LightRAG query initialization is unavailable. It reads LightRAG's persisted full
documents, performs deterministic lexical retrieval, and uses DeepSeek only for
the final answer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


DEFAULT_MODEL = "deepseek-chat"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
MAX_DOC_CHARS = 4500


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def archive_filename(query: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    stamp = now.strftime("%Y-%m-%d_%H%M%S")
    slug = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", query.strip())
    slug = re.sub(r"-+", "-", slug).strip("-")[:48] or "untitled"
    return f"{stamp}_{slug}.md"


def cjk_runs(text: str) -> list[str]:
    return re.findall(r"[\u3400-\u9fff]+", text)


def query_tokens(query: str) -> list[str]:
    tokens: set[str] = set()
    lowered = query.lower()
    tokens.update(t for t in re.findall(r"[a-z0-9][a-z0-9_+.-]{1,}", lowered) if len(t) >= 2)

    for run in cjk_runs(query):
        if len(run) <= 6:
            tokens.add(run)
        for size in (2, 3, 4):
            for i in range(0, max(0, len(run) - size + 1)):
                tokens.add(run[i : i + size])

    stop = {
        "如何",
        "什么",
        "怎么",
        "应该",
        "参考",
        "最佳",
        "实践",
        "实现",
        "集成",
        "代码",
        "结构",
        "项目",
    }
    return sorted(t for t in tokens if t not in stop)


def load_docs(storage_dir: Path) -> dict[str, dict[str, Any]]:
    full_docs = storage_dir / "kv_store_full_docs.json"
    if not full_docs.exists():
        raise FileNotFoundError(f"LightRAG full-doc store not found: {full_docs}")
    with full_docs.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Unexpected full-doc store format: {type(data).__name__}")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def title_from_content(content: str) -> str:
    for line in content.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:180]
    return "Untitled document"


def score_doc(query: str, tokens: list[str], doc_id: str, doc: dict[str, Any]) -> float:
    content = str(doc.get("content") or "")
    title = title_from_content(content)
    haystack = f"{doc_id}\n{title}\n{content}".lower()
    title_lower = title.lower()
    score = 0.0

    q = query.lower().strip()
    if q and q in haystack:
        score += 100.0

    for token in tokens:
        if token in title_lower:
            score += 12.0
        count = haystack.count(token)
        if count:
            score += min(18.0, count * 1.8)

    if re.search(r"hermes|openclaw|mem0|agent|rag|memory|tool|skill", haystack):
        score += 2.0
    return score


def retrieve(query: str, docs: dict[str, dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    tokens = query_tokens(query)
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for doc_id, doc in docs.items():
        score = score_doc(query, tokens, doc_id, doc)
        if score > 0:
            ranked.append((score, doc_id, doc))
    ranked.sort(key=lambda item: item[0], reverse=True)

    selected: list[dict[str, Any]] = []
    for score, doc_id, doc in ranked[:top_k]:
        content = str(doc.get("content") or "")
        selected.append(
            {
                "id": doc_id,
                "score": round(score, 2),
                "title": title_from_content(content),
                "source": str(doc.get("file_path") or "unknown_source"),
                "content": content[:MAX_DOC_CHARS],
            }
        )
    return selected


def build_prompt(query: str, evidence: list[dict[str, Any]]) -> str:
    evidence_blocks = []
    for idx, item in enumerate(evidence, 1):
        evidence_blocks.append(
            "\n".join(
                [
                    f"[{idx}] id={item['id']} score={item['score']}",
                    f"title: {item['title']}",
                    f"source: {item['source']}",
                    "content:",
                    item["content"],
                ]
            )
        )

    joined = "\n\n---\n\n".join(evidence_blocks)
    return f"""You are OmniGraph Cloud Synthesizer.

Answer the user's question using only the evidence below. If the evidence is
thin or indirect, say so clearly. Prefer concrete engineering guidance,
architecture implications, and source-grounded caveats. Match the user's
language.

User question:
{query}

Retrieved evidence:
{joined}
"""


def call_deepseek(prompt: str) -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set in environment or ~/.hermes/.env")

    base_url = os.environ.get("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    requested = os.environ.get("OMNIGRAPH_CLOUD_SYNTHESIS_MODEL") or os.environ.get("DEEPSEEK_MODEL") or DEFAULT_MODEL
    models = [requested]
    if DEFAULT_MODEL not in models:
        models.append(DEFAULT_MODEL)

    last_error = None
    for model in models:
        try:
            response = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "You synthesize concise, evidence-grounded technical reports."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=180,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"DeepSeek synthesis failed: {last_error}")


def write_outputs(query: str, answer: str, base_dir: Path) -> tuple[Path, Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    archive_dir = base_dir / "synthesis_archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    latest = base_dir / "synthesis_output.md"
    archive = archive_dir / archive_filename(query)
    latest.write_text(answer, encoding="utf-8")
    archive.write_text(answer, encoding="utf-8")
    return latest, archive


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="No-Gemini synthesis over persisted OmniGraph docs.")
    parser.add_argument("query", help="Natural-language question to answer.")
    parser.add_argument("--top-k", type=int, default=8, help="Number of full docs to pass as evidence.")
    parser.add_argument(
        "--storage-dir",
        default=str(Path.home() / ".hermes" / "omonigraph-vault" / "lightrag_storage"),
        help="LightRAG storage directory containing kv_store_full_docs.json.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path.home() / ".hermes" / "omonigraph-vault"),
        help="Directory for synthesis_output.md and synthesis_archive/.",
    )
    return parser.parse_args()


def main() -> int:
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    load_env_file(Path.home() / ".hermes" / ".env")
    args = parse_args()
    docs = load_docs(Path(args.storage_dir).expanduser())
    evidence = retrieve(args.query, docs, max(1, args.top_k))
    if not evidence:
        print("No lexical evidence found in already-ingested docs.")
        return 2

    prompt = build_prompt(args.query, evidence)
    answer = call_deepseek(prompt)
    latest, archive = write_outputs(args.query, answer, Path(args.output_dir).expanduser())

    print(f"Retrieved {len(evidence)} docs from persisted LightRAG storage.")
    print(f"latest:  {latest}")
    print(f"archive: {archive}")
    print()
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
