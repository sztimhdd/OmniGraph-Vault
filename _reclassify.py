#!/usr/bin/env python3
"""Re-classify articles from a previous dry-run summary with a topic filter."""
import json, os, sys, requests, time, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

API_URL = "https://api.deepseek.com/chat/completions"

def build_prompt(titles, topic_filter, min_depth):
    articles = "\n".join(f"{i}: {t}" for i, t in enumerate(titles))
    return f"""You are a technical article curator. Classify each article below.

For each article, return a JSON array of objects with:
- index: the 0-based index
- depth_score: 1 (shallow news blurb), 2 (moderate analysis), 3 (deep technical deep-dive)
- relevant: true/false — is this article substantially about "{topic_filter}"?
- reason: brief explanation

Articles:
{articles}

Return ONLY valid JSON, no other text."""

def call_deepseek(prompt, api_key):
    resp = requests.post(API_URL, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }, json={
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }, timeout=120)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        start = content.find("\n") + 1
        end = content.rfind("```")
        if end > start:
            content = content[start:end].strip()
    return json.loads(content)

def main():
    _, summary_path, topic, min_depth = sys.argv[0:4]
    min_depth = int(min_depth)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        # Fallback: read from Hermes credential pool
        auth_path = os.path.expanduser("~/.hermes/auth.json")
        if os.path.exists(auth_path):
            try:
                with open(auth_path) as f:
                    pool = json.load(f).get("credential_pool", {})
                for cred in pool.get("deepseek", []):
                    if cred.get("access_token"):
                        api_key = cred["access_token"]
                        break
            except Exception:
                pass
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not set")
        sys.exit(1)

    articles = [a for a in json.load(open(summary_path)) if a.get("status") == "dry_run"]
    logger.info(f"Loaded {len(articles)} dry_run articles from {summary_path}")

    titles = [a.get("title", "(no title)") for a in articles]
    prompt = build_prompt(titles, topic, min_depth)
    logger.info(f"Calling DeepSeek to classify {len(titles)} articles (topic={topic})...")
    result = call_deepseek(prompt, api_key)

    if isinstance(result, dict):
        for key in ("results", "articles", "classifications"):
            if key in result and isinstance(result[key], list):
                result = result[key]
                break

    cls_by_idx = {}
    for c in result:
        idx = c.get("index")
        if idx is not None:
            cls_by_idx[int(idx)] = c

    passed, filtered = [], []
    for i, a in enumerate(articles):
        cls = cls_by_idx.get(i, {})
        depth = cls.get("depth_score", min_depth)
        if not isinstance(depth, int) or depth < 1:
            depth = min_depth
        relevant = cls.get("relevant", True)
        reason = cls.get("reason", "")

        reasons = []
        if not relevant:
            reasons.append(f"off-topic (not about {topic})")
        if depth < min_depth:
            reasons.append(f"depth too low ({reason})")

        entry = {**a}
        if reasons:
            entry["filter_reason"] = "; ".join(reasons)
            entry["depth_score"] = depth
            filtered.append(entry)
        else:
            entry["depth_score"] = depth
            passed.append(entry)

    # Print filter summary
    depth_low = sum(1 for f in filtered if "depth too low" in f.get("filter_reason", ""))
    off_topic = sum(1 for f in filtered if "off-topic" in f.get("filter_reason", ""))

    print(f"\n=== Filter Results (topic={topic}, min_depth={min_depth}) ===")
    print(f"Total articles analyzed: {len(articles)}")
    print(f"Pass: {len(passed)}")
    if filtered:
        print(f"Filtered out:")
        if off_topic: print(f"  {off_topic} - off-topic")
        if depth_low: print(f"  {depth_low} - depth too low")
        print(f"  ---")
        print(f"  {len(filtered)} total filtered")
    print()

    # Print passed articles
    print("=== Articles Passing Filter ===")
    for i, a in enumerate(passed, 1):
        title = a.get("title", "(no title)")
        account = a.get("account", "?")
        depth = a.get("depth_score", "?")
        print(f"  [{i}/{len(passed)}] [{account}] (depth={depth}) {title}")

    if filtered:
        print(f"\n=== Filtered Out ({len(filtered)} articles) ===")
        for i, a in enumerate(filtered, 1):
            reason = a.get("filter_reason", "")
            print(f"  [{i}] {a.get('title','?')} — {reason}")

if __name__ == "__main__":
    main()
