#!/usr/bin/env python3
"""Generate agent-news.json from OmniGraph classified articles.

Queries articles with layer2_verdict='ok', prioritizes Agent-related ones
by account tags + title keywords, outputs 5 articles in agent-news.json contract.

Usage:
    python gen_agent_news.py [--db-path DB] [--out PATH] [--dry-run]
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_DB = "/root/OmniGraph-Vault/data/kol_scan.db"
DEFAULT_OUT = "/opt/vitaclaw/control-plane/vitaclaw-site/dist/data/agent-news.json"
FALLBACK_OUT = "/opt/vitaclaw/control-plane/vitaclaw-site/public/data/agent-news.json"

# Agent-related topic keywords for account tag scoring
AGENT_TAGS = {
    "Agent": 3, "agent": 3,
    "RAG": 2, "rag": 2,
    "工程化": 2, "MCP": 3,
    "多智能体": 3, "multi-agent": 3,
    "AI": 1,
}

AGENT_TITLE_KEYWORDS = [
    "agent", "Agent", "RAG", "rag", "MCP", "mcp",
    "多智能体", "智能体", "编排", "工作流", "workflow",
    "LangGraph", "LangChain", "CrewAI", "AutoGen",
    "推理", "reasoning", "tool", "Tool", "function call",
    "skill", "Skill", "知识图谱", "knowledge graph",
]


def score_article(row: dict) -> int:
    """Higher = more Agent-relevant."""
    score = 0
    tags_str = (row.get("tags") or "").lower()
    title = (row.get("title") or "").lower()
    
    for kw, pts in AGENT_TAGS.items():
        if kw.lower() in tags_str:
            score += pts
    
    for kw in AGENT_TITLE_KEYWORDS:
        if kw.lower() in title:
            score += 1
    
    return score


def build_item(row: dict) -> dict:
    """Map DB row to agent-news.json item."""
    # Parse tags - might be JSON array or comma-separated
    raw_tags = row.get("tags") or "[]"
    try:
        tags = json.loads(raw_tags)
    except (json.JSONDecodeError, TypeError):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    
    def to_iso(ts):
        """Convert DB timestamp to ISO 8601 for Date.parse() compatibility."""
        if not ts:
            return ""
        try:
            # Handle 'YYYY-MM-DD HH:MM:SS' or ISO formats
            ts_str = str(ts).strip()
            if "T" in ts_str:
                return ts_str  # Already ISO
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            return dt.isoformat() + "Z"
        except (ValueError, TypeError):
            return str(ts)

    return {
        "originalTitle": row["title"],
        "originalUrl": row["url"],
        "summaryZh": (_summary := (row.get("digest") or row.get("summary") or "").strip()) and _summary[:200] or row.get("title", "")[:200],
        "tags": tags[:5],
        "sourceDomain": "mp.weixin.qq.com",
        "layer": "layer2",
        "curationStatus": "passed",
        "sourceName": row.get("name") or row.get("author") or "Unknown",
        "publishedAt": to_iso(row.get("scanned_at") or row.get("published_at") or ""),
        "collectedAt": to_iso(row.get("scanned_at") or row.get("fetched_at") or ""),
        "curatedAt": to_iso(row.get("layer2_at") or ""),
    }


def query_articles(db_path: str) -> list[dict]:
    """Query classified articles with full data."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # KOL articles: layer2_verdict='ok', joined with accounts
    cur.execute("""
        SELECT a.id, a.title, a.url, a.digest, a.scanned_at, a.layer2_at,
               ac.name, ac.tags
        FROM articles a
        JOIN accounts ac ON a.account_id = ac.id
        WHERE a.layer2_verdict = 'ok'
          AND a.title IS NOT NULL
          AND a.url IS NOT NULL
        ORDER BY a.layer2_at DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def generate(db_path: str, num: int = 5) -> dict:
    """Generate full agent-news.json contract."""
    rows = query_articles(db_path)
    
    if not rows:
        print("WARNING: No classified articles found. Keeping previous file.", file=sys.stderr)
        return None
    
    # Score and sort
    for r in rows:
        r["_score"] = score_article(r)
    # Highest score first, same score → most recent first
    rows.sort(key=lambda r: (-r["_score"], r.get("layer2_at") or "0000"), reverse=False)
    
    selected = rows[:num]
    
    items = [build_item(r) for r in selected]
    
    return {
        "contractVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate agent-news.json from OmniGraph classified articles")
    parser.add_argument("--db-path", default=DEFAULT_DB, help="Path to kol_scan.db")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output path for agent-news.json")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of writing")
    args = parser.parse_args()
    
    if not Path(args.db_path).exists():
        print(f"ERROR: DB not found at {args.db_path}", file=sys.stderr)
        sys.exit(1)
    
    result = generate(args.db_path)
    if result is None:
        sys.exit(1)
    
    json_str = json.dumps(result, ensure_ascii=False, indent=2)
    
    if args.dry_run:
        print(json_str)
        print(f"\n--- Would write {len(result['items'])} items to {args.out}", file=sys.stderr)
        return
    
    # Write to dist/ (live for Caddy) and public/ (survives redeploy)
    for target in [args.out, FALLBACK_OUT]:
        out_path = Path(target)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = out_path.with_suffix(".tmp")
        tmp_path.write_text(json_str + "\n", encoding="utf-8")
        tmp_path.replace(out_path)
        print(f"Wrote {len(result['items'])} items to {target}")
    for item in result["items"]:
        print(f"  [{item['sourceName']}] {item['originalTitle'][:50]}...")


if __name__ == "__main__":
    main()
