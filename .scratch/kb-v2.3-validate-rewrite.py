"""kb-v2.3 rewrite-prompt validation harness.

Runs lib.rewrite.rewrite_body_with_deepseek on real dirty article DISPLAY
content pulled from the LIVE Aliyun DB and prints programmatic pass/fail on each
of the 5 CONTEXT.md prompt gates. Writes input/output pairs to
.scratch/kb-v2.3-rewrite-samples/ for human eyeball review.

NOT a pytest file — makes real DeepSeek calls.

CRITICAL — the rewrite INPUT is the D-14-resolved DISPLAY content, NOT raw DB
`body`. Live-probe (2026-07-03) proved DB `body` carries WeChat CDN URLs
(mmbiz.qpic.cn), never `http://localhost:8765/` — so the OLD
`body LIKE '%localhost:8765%'` sampling predicate matched nothing and made the
URL-set diff valve inert (∅==∅). The real localhost URLs + real displayed
content live in filesystem `final_content(.enriched).md`. This harness now
mirrors get_article_body()'s fs read (article_query.py:587-619) so the valve's
main defense is actually exercised. See memory
`decision_rewrite_display_only_kg_uses_original.md` "CRITICAL CORRECTION" and
`kb_v2_3_aliyun_db_paths.md`.

Usage (on Aliyun — DeepSeek CN egress; corp laptop blocks DeepSeek):
    cd /root/OmniGraph-Vault
    set -a; source /root/.hermes/.env; set +a
    export KB_DB_PATH=/root/OmniGraph-Vault/data/kol_scan.db
    export KB_IMAGES_DIR=/root/.hermes/omonigraph-vault/images
    venv/bin/python .scratch/kb-v2.3-validate-rewrite.py --limit 8

Exit code:
  0 — >= 3 image-bearing samples run AND every non-valve-rejected sample passes
      ALL 5 gates AND valve-reject rate < 30%
  1 — insufficient image-bearing coverage, gate failures, or valve-reject >= 30%

This harness is the ENFORCEABLE form of the CONTEXT.md "PROMPT VALIDATION GATE
(blocks batch)". Its exit-0 unblocks plan 03 backfill.

NOTE: READ-ONLY on prod tables (SELECT via mode=ro + writes only to .scratch/).
Consumes ~1 DeepSeek call per sample (~8 with --limit 8).
"""
from __future__ import annotations

# Phase 5 cross-coupling defense: set before any lib.* import.
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import argparse
import asyncio
import hashlib
import json
import re
import sqlite3
import sys
from datetime import date
from pathlib import Path

# sys.path bootstrap — verbatim from scripts/translate_body_cron.py:52-54
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# kb.config is the SINGLE source of truth for the DB + images paths — the same
# ones get_article_body() reads. Do NOT copy translate_body_cron._resolve_db_path
# (it resolves to a 38-byte stub under .env-only; see kb_v2_3_aliyun_db_paths).
from kb import config as kb_config  # noqa: E402


# ---------------------------------------------------------------------------
# Gate definitions
# ---------------------------------------------------------------------------

# Match genuine HTML tags only. The tag name must be followed by a tag-name
# boundary: '>', whitespace, or '/'. This prevents false positives like
# '<thinking>' (a code-block string / regex token) matching the 'th' alternative.
_HTML_TAGS_RE = re.compile(
    r"</?(script|style|div|span|table|tr|td|th|thead|tbody)(?=[\s/>])",
    re.IGNORECASE,
)
_BOILERPLATE_MARKERS = ["关注公众号", "点赞", "扫码"]
_IMAGE_URL_RE = re.compile(r"http://localhost:8765/\S+")
_URL_TRAILING = re.compile(r"[)\]>\"']+$")


def _extract_image_urls(text: str) -> set[str]:
    found = _IMAGE_URL_RE.findall(text)
    return {_URL_TRAILING.sub("", url) for url in found}


def _gate_url(input_body: str, output_body: str) -> tuple[bool, str]:
    """GATE-URL: output URL set must be byte-identical to input URL set."""
    in_urls = _extract_image_urls(input_body)
    out_urls = _extract_image_urls(output_body)
    if in_urls == out_urls:
        return True, f"OK (urls={len(in_urls)})"
    dropped = in_urls - out_urls
    added = out_urls - in_urls
    return False, f"FAIL dropped={dropped} added={added}"


def _gate_html(output_body: str) -> tuple[bool, str]:
    """GATE-HTML: no raw HTML tags in output."""
    matches = _HTML_TAGS_RE.findall(output_body)
    if not matches:
        return True, "OK"
    return False, f"FAIL found_tags={matches[:3]}"


def _gate_boilerplate(output_body: str) -> tuple[bool, str]:
    """GATE-BOILERPLATE: no WeChat ad/boilerplate markers in output."""
    found = [m for m in _BOILERPLATE_MARKERS if m in output_body]
    if not found:
        return True, "OK"
    return False, f"FAIL markers_remaining={found}"


def _gate_markdownlint(output_body: str) -> tuple[bool, str]:
    """GATE-MARKDOWNLINT: in-process minimal check (markdownlint CLI not required).

    Checks the most common structural issues:
    - No bare <br> tags (should be markdown line breaks)
    - No consecutive blank lines > 2 (excessive whitespace)
    - No lines that look like raw HTML blocks (already caught by GATE-HTML)

    A full markdownlint CLI run is not required on the Aliyun host (Node not
    guaranteed present); this in-process check covers the structural issues the
    rewrite could realistically introduce.
    """
    issues = []

    # More than 2 consecutive blank lines
    if re.search(r"\n{4,}", output_body):
        issues.append("excessive_blank_lines")

    # Raw <br> tags in output
    if re.search(r"<br\s*/?>", output_body, re.IGNORECASE):
        issues.append("bare_br_tags")

    if issues:
        return False, f"FAIL issues={issues}"
    return True, "OK"


def _gate_length(input_body: str, output_body: str) -> tuple[bool, str]:
    """GATE-LENGTH: output >= 20% of input length."""
    ratio = len(output_body) / max(len(input_body), 1)
    if ratio >= 0.20:
        return True, f"OK (ratio={ratio:.2%})"
    return False, f"FAIL (ratio={ratio:.2%} < 20%)"


# ---------------------------------------------------------------------------
# D-14 DISPLAY-CONTENT resolution — mirrors article_query.py get_article_body
# (587-619) + resolve_url_hash (134-153). Returns RAW markdown with the
# localhost:8765 URLs INTACT (does NOT apply _rewrite_image_paths) so the URL
# valve has real URLs to diff. This is exactly what plan-03's cron will feed.
# ---------------------------------------------------------------------------

def _resolve_url_hash(source: str, content_hash: str | None, url: str) -> str:
    """Pure url-hash resolution (DATA-06). No DB, no fs.

    - wechat + content_hash -> content_hash (already 10 chars)
    - wechat + NULL hash     -> md5(url)[:10]   (e.g. articles id=861)
    - rss + content_hash     -> content_hash[:10]
    - rss + NULL hash        -> ValueError (RSS rows always have a hash)
    """
    if source == "wechat":
        if content_hash:
            return content_hash
        return hashlib.md5(url.encode("utf-8")).hexdigest()[:10]
    if source == "rss":
        if content_hash:
            return content_hash[:10]
        raise ValueError(f"rss row url={url!r} has NULL content_hash (unexpected)")
    raise ValueError(f"unknown source: {source}")


def _resolve_display_content(
    source: str,
    content_hash: str | None,
    url: str,
    body_cleaned: str | None,
    body: str | None,
) -> str:
    """The D-14 display content, raw (localhost:8765 URLs kept intact).

    fs: {KB_IMAGES_DIR}/{url_hash}/final_content.enriched.md -> final_content.md
    db fallback: body_cleaned or body (only when NO fs file exists, ~30%).
    """
    try:
        url_hash = _resolve_url_hash(source, content_hash, url)
    except ValueError:
        return body_cleaned or body or ""
    images_dir = Path(kb_config.KB_IMAGES_DIR)
    for fname in ("final_content.enriched.md", "final_content.md"):
        p = images_dir / url_hash / fname
        if p.exists():
            return p.read_text(encoding="utf-8")
    return body_cleaned or body or ""


# ---------------------------------------------------------------------------
# Pull + resolve candidate samples
# ---------------------------------------------------------------------------

def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    try:
        conn.execute(f"SELECT {column} FROM {table} LIMIT 0")  # noqa: S608
        return True
    except sqlite3.OperationalError:
        return False


def _pull_candidate_pool(conn: sqlite3.Connection, pool: int) -> list[tuple]:
    """Pull a POOL of DATA-07 candidates (dirtiest = longest body first).

    Returns rows of (id, source, table_name, title, url, content_hash,
    body_cleaned, body). The fs resolution + image-bearing partition happens in
    Python — a DB predicate CANNOT know which rows have localhost URLs because
    those live on disk, not in `body`.

    DATA-07 filter: layer1_verdict='candidate' AND layer2_verdict='ok'
    AND body IS NOT NULL AND body != '' AND (body_rewritten IS NULL, guarded).
    """
    def _rewritten_guard(table: str) -> str:
        return "AND body_rewritten IS NULL" if _table_has_column(conn, table, "body_rewritten") else ""

    def _bc_expr(table: str) -> str:
        return "body_cleaned" if _table_has_column(conn, table, "body_cleaned") else "NULL"

    art_guard = _rewritten_guard("articles")
    rss_guard = _rewritten_guard("rss_articles")
    art_bc = _bc_expr("articles")
    rss_bc = _bc_expr("rss_articles")

    sql = f"""
        SELECT id, source, table_name, title, url, content_hash, body_cleaned, body
          FROM (
            SELECT id, 'wechat' AS source, 'articles' AS table_name, title, url,
                   content_hash, {art_bc} AS body_cleaned, body,
                   length(body) AS body_len
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               {art_guard}
            UNION ALL
            SELECT id, 'rss' AS source, 'rss_articles' AS table_name, title, url,
                   content_hash, {rss_bc} AS body_cleaned, body,
                   length(body) AS body_len
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               {rss_guard}
          )
         ORDER BY body_len DESC
         LIMIT ?
    """  # noqa: S608
    return list(conn.execute(sql, (pool,)))


def _select_samples(pool_rows: list[tuple], limit: int, max_body_len: int) -> list[dict]:
    """Resolve each candidate's D-14 display content, then pick the sample set.

    Strategy (fixes the prior all-0-image blind spot): PREFER image-bearing rows
    (non-empty localhost:8765 URL set in the RESOLVED content), longest resolved
    body first — so the run exercises the URL valve's main defense AND near-cap
    content. Rows whose resolved content exceeds max_body_len are dropped
    (they'd trip the 300s per-call timeout — unrelated to the URL test).
    """
    resolved = []
    for (art_id, source, table, title, url, content_hash, body_cleaned, body) in pool_rows:
        display = _resolve_display_content(source, content_hash, url, body_cleaned, body)
        if not display or len(display) > max_body_len:
            continue
        urls = _extract_image_urls(display)
        resolved.append({
            "id": art_id,
            "source": source,
            "table": table,
            "title": title or "",
            "display": display,
            "url_count": len(urls),
            "resolved_len": len(display),
        })

    image_bearing = sorted(
        (r for r in resolved if r["url_count"] > 0),
        key=lambda r: r["resolved_len"], reverse=True,
    )
    non_image = sorted(
        (r for r in resolved if r["url_count"] == 0),
        key=lambda r: r["resolved_len"], reverse=True,
    )

    # Fill with image-bearing first (up to limit), then top up with non-image.
    samples = image_bearing[:limit]
    if len(samples) < limit:
        samples += non_image[: limit - len(samples)]
    return samples


# ---------------------------------------------------------------------------
# Run harness
# ---------------------------------------------------------------------------

SAMPLES_DIR = _REPO_ROOT / ".scratch" / "kb-v2.3-rewrite-samples"


async def _run_harness(args: argparse.Namespace) -> int:
    """Run validation harness; returns exit code (0=pass, 1=fail)."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    log = logging.getLogger("kb-v2.3-validate-rewrite")

    db_path = Path(kb_config.KB_DB_PATH)
    if not db_path.exists():
        log.error(
            "DB not found at %s — export KB_DB_PATH to the real DB "
            "(/root/OmniGraph-Vault/data/kol_scan.db on Aliyun)", db_path,
        )
        return 1

    log.info("DB: %s", db_path)
    log.info("IMAGES_DIR: %s", kb_config.KB_IMAGES_DIR)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)

    try:
        pool_rows = _pull_candidate_pool(conn, args.pool)
    finally:
        conn.close()

    if not pool_rows:
        log.error("No DATA-07 candidates found — nothing to validate")
        return 1

    log.info("Pulled %d candidates into pool; resolving D-14 display content...", len(pool_rows))
    samples = _select_samples(pool_rows, args.limit, args.max_body_len)

    if not samples:
        log.error("No samples survived resolution + max_body_len=%d filter", args.max_body_len)
        return 1

    image_bearing_selected = sum(1 for s in samples if s["url_count"] > 0)
    log.info(
        "Selected %d samples (%d image-bearing) from pool; running rewrite...",
        len(samples), image_bearing_selected,
    )

    # Lazy import rewrite function (so the DB/pool guards can bail without the key)
    from lib.rewrite import rewrite_body_with_deepseek

    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    gate_names = ["URL", "HTML", "BOILERPLATE", "MARKDOWNLINT", "LENGTH"]
    gate_totals = {g: 0 for g in gate_names}
    gate_passes = {g: 0 for g in gate_names}
    valve_rejects = 0
    image_bearing_run = 0
    total_run = 0
    all_results = []

    for s in samples:
        total_run += 1
        art_id, table, title = s["id"], s["table"], s["title"]
        display = s["display"]
        input_url_count = s["url_count"]
        if input_url_count > 0:
            image_bearing_run += 1
        log.info(
            "--- Sample %d/%d id=%s table=%s title=%.60s resolved_len=%d input_urls=%d ---",
            total_run, len(samples), art_id, table, title, len(display), input_url_count,
        )

        result = await rewrite_body_with_deepseek(title, display)

        sample_id = f"{art_id}-{table}"
        (SAMPLES_DIR / f"{sample_id}-input.md").write_text(display, encoding="utf-8")

        if result is None:
            # Could be valve reject OR empty output — valve logs WARNING
            valve_rejects += 1
            log.info(
                "  REJECTED-BY-VALVE or EMPTY (safe outcome; not a gate failure). "
                "input_urls=%d", input_url_count,
            )
            all_results.append({
                "id": art_id, "table": table, "title": title,
                "status": "VALVE_REJECTED", "gates": {},
                "input_len": len(display), "output_len": 0,
                "input_url_count": input_url_count, "output_url_count": None,
            })
            continue

        # Run gates
        url_ok, url_msg = _gate_url(display, result)
        html_ok, html_msg = _gate_html(result)
        bp_ok, bp_msg = _gate_boilerplate(result)
        md_ok, md_msg = _gate_markdownlint(result)
        len_ok, len_msg = _gate_length(display, result)

        gate_results = {
            "URL": (url_ok, url_msg),
            "HTML": (html_ok, html_msg),
            "BOILERPLATE": (bp_ok, bp_msg),
            "MARKDOWNLINT": (md_ok, md_msg),
            "LENGTH": (len_ok, len_msg),
        }

        for g in gate_names:
            gate_totals[g] += 1
            if gate_results[g][0]:
                gate_passes[g] += 1

        all_pass = all(gate_results[g][0] for g in gate_names)
        status = "PASS" if all_pass else "FAIL"

        output_url_count = len(_extract_image_urls(result))
        log.info("  %s | URL:%s HTML:%s BP:%s MD:%s LEN:%s (in_urls=%d out_urls=%d)",
                 status,
                 "✓" if url_ok else "✗",
                 "✓" if html_ok else "✗",
                 "✓" if bp_ok else "✗",
                 "✓" if md_ok else "✗",
                 "✓" if len_ok else "✗",
                 input_url_count, output_url_count)
        for g in gate_names:
            if not gate_results[g][0]:
                log.info("    GATE-%s: %s", g, gate_results[g][1])

        all_results.append({
            "id": art_id, "table": table, "title": title,
            "status": status,
            "gates": {g: {"pass": gate_results[g][0], "msg": gate_results[g][1]} for g in gate_names},
            "input_len": len(display), "output_len": len(result),
            "input_url_count": input_url_count, "output_url_count": output_url_count,
        })

        (SAMPLES_DIR / f"{sample_id}-output.md").write_text(result, encoding="utf-8")

    # Write JSON summary
    summary = {
        "date": str(date.today()),
        "db_path": str(db_path),
        "total_samples": total_run,
        "image_bearing_run": image_bearing_run,
        "valve_rejects": valve_rejects,
        "gate_totals": gate_totals,
        "gate_passes": gate_passes,
        "results": all_results,
    }
    summary_path = SAMPLES_DIR / "validation-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print summary table
    non_rejected = total_run - valve_rejects
    valve_rate = valve_rejects / max(total_run, 1)

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"  Samples run:       {total_run}")
    print(f"  Image-bearing run: {image_bearing_run}  (gate requires >= 3)")
    print(f"  Valve rejects:     {valve_rejects} ({valve_rate:.0%})")
    print(f"  Non-rejected:      {non_rejected}")
    print()
    print(f"  {'GATE':<15} {'PASS':>6}/{' TOTAL':>6}  {'RATE':>6}")
    print(f"  {'-'*40}")
    for g in gate_names:
        t = gate_totals[g]
        p = gate_passes[g]
        rate = p / max(t, 1)
        marker = "  " if t == 0 or p == t else "!!"
        print(f"{marker} {g:<15} {p:>6}/{t:>6}  {rate:>6.0%}")
    print()

    # Determine exit code
    gate_failures = any(
        gate_passes[g] < gate_totals[g]
        for g in gate_names
        if gate_totals[g] > 0
    )
    valve_too_high = valve_rate >= 0.30
    insufficient_images = image_bearing_run < 3

    if insufficient_images:
        print(f"  STATUS: FAIL — only {image_bearing_run} image-bearing samples run (need >= 3)")
        print("  ACTION: increase --pool or check final_content.md availability on this host")
    elif gate_failures:
        print("  STATUS: FAIL — gate failures detected (see above)")
        print("  ACTION: tune the prompt in lib/rewrite.py and re-run")
    elif valve_too_high:
        print(f"  STATUS: FAIL — valve-reject rate {valve_rate:.0%} >= 30%")
        print("  ACTION: prompt is mangling image URLs; tune and re-run")
    else:
        print("  STATUS: PASS — >= 3 image-bearing, all gates pass, valve-reject < 30%")
        print("  This harness exit-0 unblocks plan 03 backfill.")

    print(f"\n  Input/output pairs: {SAMPLES_DIR}")
    print(f"  JSON summary:       {summary_path}")
    print("=" * 70 + "\n")

    if gate_failures or valve_too_high or insufficient_images:
        return 1
    return 0


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="kb-v2.3 rewrite-prompt validation harness (real DeepSeek calls)"
    )
    p.add_argument(
        "--limit", type=int, default=8,
        help="Number of samples to actually rewrite (default 8; image-bearing preferred)",
    )
    p.add_argument(
        "--pool", type=int, default=80,
        help="Candidate rows to pull + fs-resolve before selecting --limit samples "
             "(default 80; larger pool => more image-bearing candidates to choose from)",
    )
    p.add_argument(
        "--max-body-len", type=int, default=30000,
        help="Skip rows whose RESOLVED display content exceeds this (chars); default "
             "30000 avoids the 154K-char article that exceeds the 300s per-call timeout.",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run_harness(args))


if __name__ == "__main__":
    raise SystemExit(main())
