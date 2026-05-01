"""
KOL article classifier — reads from SQLite, classifies via LLM, writes back.

Usage:
    python batch_classify_kol.py --topic "OpenClaw" --min-depth 2
    python batch_classify_kol.py --topic "Agent" --classifier gemini
    python batch_classify_kol.py --topic "RAG" --dry-run

Plan 05-00c Task 0c.4: default classifier is 'deepseek' (see :335). This
script already routes to the DeepSeek chat completions endpoint directly —
no unification with lightrag_llm.deepseek_model_complete is needed for the
quota-relief goal (DeepSeek quota is distinct from Gemini generate_content).
Full wrapper unification is a Phase 8 opportunistic cleanup.
"""
import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DB_PATH = PROJECT_ROOT / "data" / "kol_scan.db"

logger = logging.getLogger("batch_classify_kol")

try:
    import requests
except ImportError:
    requests = None

try:
    import yaml as _yaml_lib
except ImportError:
    _yaml_lib = None

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None

from lib import INGESTION_LLM, generate_sync

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
GEMINI_CLASSIFY_SLEEP = 5.0


def _load_hermes_env() -> None:
    dotenv_paths = [
        Path.home() / ".hermes" / ".env",
        Path("//wsl.localhost/Ubuntu-24.04/home/sztimhdd/.hermes/.env"),
    ]
    for p in dotenv_paths:
        if p.exists():
            dotenv_path = p
            break
    else:
        return
    try:
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("\"'")
            if key and val and key not in os.environ:
                os.environ[key] = val
    except Exception:
        pass


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            wechat_id TEXT,
            fakeid TEXT NOT NULL UNIQUE,
            tags TEXT,
            source TEXT,
            category TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            title TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            digest TEXT,
            update_time INTEGER,
            scanned_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS classifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            topic TEXT NOT NULL,
            depth_score INTEGER CHECK(depth_score BETWEEN 1 AND 3),
            relevant INTEGER DEFAULT 0,
            excluded INTEGER DEFAULT 0,
            reason TEXT,
            classified_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id, topic)
        );
        CREATE TABLE IF NOT EXISTS ingestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            status TEXT NOT NULL CHECK(status IN ('ok', 'failed', 'skipped')),
            ingested_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(article_id)
        );
        CREATE TABLE IF NOT EXISTS extracted_entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id INTEGER NOT NULL REFERENCES articles(id),
            entity_name TEXT NOT NULL,
            entity_type TEXT,
            extracted_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS entity_canonical (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_name TEXT NOT NULL UNIQUE,
            canonical_name TEXT NOT NULL,
            entity_type TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_classifications_topic ON classifications(topic);
        CREATE INDEX IF NOT EXISTS idx_classifications_article ON classifications(article_id);
        CREATE INDEX IF NOT EXISTS idx_extracted_entities_article ON extracted_entities(article_id);
    """)
    conn.commit()
    return conn


def get_deepseek_api_key() -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    dotenv_path = Path.home() / ".hermes" / ".env"
    if dotenv_path.exists():
        try:
            for line in dotenv_path.read_text().splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip("\"'")
                    if val:
                        return val
        except Exception:
            pass
    config_path = Path.home() / ".hermes" / "config.yaml"
    if config_path.exists() and _yaml_lib is not None:
        try:
            cfg = _yaml_lib.safe_load(config_path.read_text())
            raw = cfg.get("providers", {}).get("deepseek", {}).get("api_key", "")
            if raw and not raw.startswith("${"):
                return raw
        except Exception:
            pass
    return None


def _build_prompt(titles: list[str], topic_filter: str, min_depth: int, digests: list[str] | None = None) -> str:
    entries = []
    for i, title in enumerate(titles):
        entry = title
        if digests and i < len(digests) and digests[i]:
            entry = f"{title} [digest: {digests[i][:200]}]"
        entries.append(f"{i}: {entry}")

    return f"""You are a technical article curator. Classify each article below.
For each article, return a JSON array of objects with:
- index: the 0-based index
- depth_score: 1 (shallow news blurb / brief announcement), 2 (moderate analysis with some detail), 3 (deep technical deep-dive, substantive content)
- relevant: true/false — is this article substantially about "{topic_filter}"?
- reason: brief explanation (e.g. "news blurb", "deep technical analysis", "event notice", "off-topic")
Articles:
{chr(10).join(entries)}
Return ONLY valid JSON, no other text."""


def _call_deepseek(prompt: str, api_key: str) -> list[dict] | None:
    if requests is None:
        logger.warning("requests library not available — cannot call DeepSeek API")
        return None
    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": DEEPSEEK_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.0},
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            start = content.find("\n") + 1
            end = content.rfind("```")
            if end > start:
                content = content[start:end].strip()
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for key in ("results", "articles", "classifications"):
                if key in parsed and isinstance(parsed[key], list):
                    return parsed[key]
        logger.warning("DeepSeek returned unexpected format: %s", type(parsed))
        return None
    except Exception as exc:
        logger.warning("DeepSeek API call failed: %s", exc)
        return None


# Phase 10 plan 10-00 (D-10.02): full-body classifier prompt + call helper.
# These live alongside the legacy batch-scan helpers (`_build_prompt` +
# `_call_deepseek`) because the batch-scan path still uses the old schema.
# New {depth, topics, rationale} schema is scrape-first-only.
FULLBODY_TRUNCATION_CHARS = 8000  # D-10.02 suggested budget; avoids DeepSeek context blowup


def _build_fullbody_prompt(
    title: str,
    body: str,
    topic_filter: list[str] | None = None,
) -> str:
    """Build a DeepSeek prompt that classifies one article on its FULL BODY.

    D-10.02: the prompt MUST feed the article body (truncated to
    FULLBODY_TRUNCATION_CHARS) — NOT the WeChat digest — and instruct the
    model to return a single JSON object with ``depth`` (1-3), ``topics``
    (list of strings), and ``rationale`` (string).

    Unlike `_build_prompt` (batch-scan path, returns JSON array), this
    helper builds a single-article prompt — the caller is expected to call
    DeepSeek once per article (scrape-first path is per-article anyway).
    """
    truncated_body = body[:FULLBODY_TRUNCATION_CHARS]
    topic_hint = ""
    if topic_filter:
        keywords = ", ".join(f'"{k}"' for k in topic_filter)
        topic_hint = (
            f"\n\nThe user is filtering by topics: {keywords}. If the article is "
            f"substantively about any of these, include them in the topics list."
        )

    return f"""You are a technical article curator. Classify the following article.

Return ONLY a single JSON object with three keys:
- depth: integer 1-3 (1 = shallow news blurb / brief announcement, 2 = moderate analysis, 3 = deep technical deep-dive)
- topics: a list of 3-5 key concepts, domains, or technologies the article is substantively about (short strings, e.g. ["AI agents", "retrieval-augmented generation"])
- rationale: a one-sentence explanation of the depth score{topic_hint}

Title: {title}

Body:
{truncated_body}

Return ONLY a JSON object of the shape {{"depth": <1-3>, "topics": [...], "rationale": "..."}}. No other text, no markdown fences."""


def _call_deepseek_fullbody(prompt: str, api_key: str) -> dict | None:
    """Call DeepSeek with a full-body prompt; parse a single JSON object.

    D-10.02 / D-10.04: returns ``{"depth": int, "topics": list[str],
    "rationale": str}`` on success. Returns ``None`` on ANY error —
    orchestrator MUST skip the article (no fail-open).
    """
    if requests is None:
        logger.warning("requests library not available — cannot call DeepSeek API")
        return None
    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
            },
            timeout=120,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            start = content.find("\n") + 1
            end = content.rfind("```")
            if end > start:
                content = content[start:end].strip()
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            logger.warning(
                "DeepSeek fullbody returned non-object: %s", type(parsed).__name__
            )
            return None
        # Minimal shape check — depth + topics are load-bearing.
        if "depth" not in parsed or "topics" not in parsed:
            logger.warning("DeepSeek fullbody missing required keys: %s", list(parsed.keys()))
            return None
        return parsed
    except Exception as exc:
        logger.warning("DeepSeek fullbody API call failed: %s", exc)
        return None


def _call_gemini(prompt: str) -> list[dict] | None:
    if genai_types is None:
        logger.warning("google-genai package not available — cannot call Gemini API")
        return None
    try:
        # lib.generate_sync handles key resolution + rotation + rate limit + retry.
        text = generate_sync(
            INGESTION_LLM,
            prompt,
            config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return json.loads(text)
    except Exception as exc:
        logger.warning("Gemini API call failed: %s", exc)
        return None


def run(topic: str, min_depth: int, classifier: str, dry_run: bool) -> None:
    _load_hermes_env()
    conn = init_db()

    rows = conn.execute(
        """SELECT a.id, a.title, a.digest, acc.name
           FROM articles a
           JOIN accounts acc ON a.account_id = acc.id
           WHERE a.id NOT IN (
               SELECT article_id FROM classifications WHERE topic = ?
           )
           ORDER BY a.id""",
        (topic,),
    ).fetchall()

    if not rows:
        logger.info("No unclassified articles for topic '%s'", topic)
        conn.close()
        return

    articles = [{"article_id": r[0], "title": r[1], "digest": r[2], "account": r[3]} for r in rows]
    logger.info("Loaded %d unclassified articles for topic '%s'", len(articles), topic)

    titles = [a["title"] for a in articles]
    digests = [a["digest"] for a in articles]
    batch_size = 200
    is_gemini = classifier == "gemini"
    label = "Gemini" if is_gemini else "DeepSeek"

    if is_gemini:
        logger.info("  Rate limit: sleeping %.0fs (Gemini free tier: 15 RPM)", GEMINI_CLASSIFY_SLEEP)
        time.sleep(GEMINI_CLASSIFY_SLEEP)

    all_cls: list[dict] = []
    for batch_start in range(0, len(titles), batch_size):
        batch_titles = titles[batch_start:batch_start + batch_size]
        batch_digests = digests[batch_start:batch_start + batch_size]
        logger.info("Classifying %d–%d of %d via %s...",
                     batch_start + 1, min(batch_start + batch_size, len(titles)), len(titles), label)
        prompt = _build_prompt(batch_titles, topic, min_depth, batch_digests)
        result = _call_deepseek(prompt, get_deepseek_api_key()) if not is_gemini else _call_gemini(prompt)
        if result is None:
            logger.warning("%s API failed — aborting classification", label)
            conn.close()
            return
        all_cls.extend(result)

    cls_by_idx = {int(c["index"]): c for c in all_cls if "index" in c}

    passed, filtered_out = [], []
    for i, art in enumerate(articles):
        cls = cls_by_idx.get(i, {})
        depth = cls.get("depth_score", min_depth)
        if not isinstance(depth, int) or depth < 1:
            depth = min_depth
        relevant = cls.get("relevant", True)
        reason = cls.get("reason", "")

        if not dry_run:
            conn.execute(
                """INSERT OR REPLACE INTO classifications (article_id, topic, depth_score, relevant, excluded, reason)
                   VALUES (?, ?, ?, ?, 0, ?)""",
                (art["article_id"], topic, depth, 1 if relevant else 0, reason),
            )

        if not relevant:
            filtered_out.append({"filter_reason": f"off-topic ({reason or 'not about ' + topic})", "depth_score": depth, **art})
        elif depth < min_depth:
            filtered_out.append({"filter_reason": f"depth too low ({reason or 'shallow'})", "depth_score": depth, **art})
        else:
            passed.append({"depth_score": depth, **art})

    conn.commit()

    # Print summary
    print(f"\n=== Filter Results (topic={topic}, min_depth={min_depth}, classifier={classifier}) ===")
    print(f"Total: {len(articles)}  |  Pass: {len(passed)}  |  Filtered: {len(filtered_out)}")
    if filtered_out:
        reasons: dict[str, int] = {}
        for a in filtered_out:
            r = a.get("filter_reason", "unknown")
            reasons[r] = reasons.get(r, 0) + 1
        for r, c in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"  {c} — {r}")

    if passed:
        print(f"\n=== Passed Articles ({len(passed)}) ===")
        for i, a in enumerate(passed, 1):
            print(f"  {i}. [{a['account']}] {a['title'][:60]}  (depth={a['depth_score']})")

    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify KOL articles from SQLite via LLM")
    parser.add_argument("--topic", type=str, required=True, help="Topic to classify (e.g. 'OpenClaw')")
    parser.add_argument("--min-depth", type=int, default=2, choices=[1, 2, 3], help="Minimum depth score (default: 2)")
    parser.add_argument("--classifier", type=str, default="deepseek", choices=["deepseek", "gemini"],
                        help="Classifier: deepseek (default) or gemini")
    parser.add_argument("--dry-run", action="store_true", help="Classify and print results without writing to DB")
    args = parser.parse_args()

    if not DB_PATH.exists():
        logger.error("DB not found: %s. Run batch_scan_kol.py first.", DB_PATH)
        sys.exit(1)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    run(args.topic, args.min_depth, args.classifier, args.dry_run)


if __name__ == "__main__":
    main()
