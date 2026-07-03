"""kb-v2.3 rewrite-prompt validation harness.

Runs lib.rewrite.rewrite_body_with_deepseek on real dirty WeChat article bodies
pulled from the LIVE Aliyun DB and prints programmatic pass/fail on each of the
5 CONTEXT.md prompt gates. Writes input/output pairs to
.scratch/kb-v2.3-rewrite-samples/ for human eyeball review.

NOT a pytest file — makes real DeepSeek calls.

Usage (on Aliyun — must source ~/.hermes/.env first):
    cd /root/OmniGraph-Vault
    set -a; source /root/.hermes/.env; set +a
    venv/bin/python .scratch/kb-v2.3-validate-rewrite.py --limit 8

Exit code:
  0 — every non-valve-rejected sample passes ALL 5 gates AND valve-reject < 30%
  1 — gate failures or valve-reject rate >= 30%

This harness is the ENFORCEABLE form of the CONTEXT.md "PROMPT VALIDATION GATE
(blocks batch)". Its exit-0 unblocks plan 03 backfill.

NOTE: This script is READ-ONLY on prod tables (SELECT only + writes to .scratch/).
It does NOT mutate prod data. Consumes ~1 DeepSeek call per article (~8 calls
with --limit 8).

Runs on Aliyun only (DeepSeek CN egress; corp laptop blocks DeepSeek).
"""
from __future__ import annotations

# Phase 5 cross-coupling defense: set before any lib.* import.
import os
os.environ.setdefault("DEEPSEEK_API_KEY", "dummy")

import argparse
import asyncio
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

from config import BASE_DIR  # noqa: E402


# ---------------------------------------------------------------------------
# DB resolution — verbatim from scripts/translate_body_cron.py:62-78
# ---------------------------------------------------------------------------

def _resolve_db_path() -> Path:
    """Locate the SQLite DB.

    Production (Aliyun): ``$BASE_DIR/data/kol_scan.db`` or
    ``$BASE_DIR/kol_scan.db``.
    """
    base = Path(BASE_DIR)
    nested = base / "data" / "kol_scan.db"
    if nested.exists():
        return nested
    return base / "kol_scan.db"


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

    A full markdownlint run is logged as advisory; harness passes with warnings.
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
# Pull dirty samples from DB
# ---------------------------------------------------------------------------

def _pull_dirty_samples(
    conn: sqlite3.Connection,
    limit: int,
    with_images: bool = False,
    max_body_len: Optional[int] = None,
) -> list[tuple]:
    """SELECT the dirtiest unprocessed samples (longest body first).

    Returns rows of (id, table_name, title, body).
    DATA-07 filter: layer1_verdict='candidate' AND layer2_verdict='ok'
    AND body IS NOT NULL AND body != '' AND body_rewritten IS NULL.

    Args:
        with_images: if True, restrict to bodies that contain at least one
            ``http://localhost:8765/`` image URL. This exercises the URL
            safety valve's PRIMARY defense (verbatim image-URL preservation
            on dirty text WITH images) — the 0-image longest-body samples
            trivially pass the URL gate (urls=0) and never test it.
        max_body_len: if set, restrict to bodies with length <= this value.
            Used with --with-images to avoid the 154K-char article that
            exceeds the 300s per-call timeout (unrelated to the URL test).
    """
    # Check if body_rewritten column exists (may not exist before migration 009)
    tables_with_rewritten = set()
    for table in ("articles", "rss_articles"):
        try:
            conn.execute(f"SELECT body_rewritten FROM {table} LIMIT 0")  # noqa: S608
            tables_with_rewritten.add(table)
        except sqlite3.OperationalError:
            pass  # column not yet migrated — treat all rows as unprocessed

    def rewritten_guard(table: str) -> str:
        if table in tables_with_rewritten:
            return "AND body_rewritten IS NULL"
        return ""  # column absent — skip guard (all rows eligible)

    # Optional extra filters (forward-only; default behavior unchanged when
    # both flags are off).
    img_guard = "AND body LIKE '%http://localhost:8765/%'" if with_images else ""
    len_guard = f"AND length(body) <= {int(max_body_len)}" if max_body_len else ""
    extra = f"{img_guard} {len_guard}".strip()

    art_guard = rewritten_guard("articles")
    rss_guard = rewritten_guard("rss_articles")

    sql = f"""
        SELECT id, table_name, title, body
          FROM (
            SELECT id, 'articles' AS table_name, title, body, layer2_at,
                   length(body) AS body_len
              FROM articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               {art_guard} {extra}
            UNION ALL
            SELECT id, 'rss_articles' AS table_name, title, body, layer2_at,
                   length(body) AS body_len
              FROM rss_articles
             WHERE layer1_verdict = 'candidate'
               AND layer2_verdict = 'ok'
               AND body IS NOT NULL AND body != ''
               {rss_guard} {extra}
          )
         ORDER BY body_len DESC
         LIMIT ?
    """  # noqa: S608
    return list(conn.execute(sql, (limit,)))


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

    db_path = _resolve_db_path()
    if not db_path.exists():
        log.error("DB not found at %s — must run on Aliyun with correct BASE_DIR", db_path)
        return 1

    log.info("DB: %s", db_path)
    conn = sqlite3.connect(str(db_path))

    try:
        rows = _pull_dirty_samples(
            conn, args.limit,
            with_images=args.with_images,
            max_body_len=args.max_body_len,
        )
    finally:
        conn.close()

    if not rows:
        log.error("No dirty samples found — nothing to validate")
        return 1

    mode = "WITH-IMAGES" if args.with_images else "longest-body"
    log.info("Pulled %d dirty samples (%s mode, ordered by body length desc)", len(rows), mode)

    # Lazy import rewrite function (lazy so the guard above can bail without needing the key)
    from lib.rewrite import rewrite_body_with_deepseek, _extract_image_urls as _eu

    # With-images samples go to a subdirectory so they never overwrite the
    # 0-image longest-body samples from a previous run.
    out_dir = (SAMPLES_DIR / "with-images") if args.with_images else SAMPLES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_names = ["URL", "HTML", "BOILERPLATE", "MARKDOWNLINT", "LENGTH"]
    gate_totals = {g: 0 for g in gate_names}
    gate_passes = {g: 0 for g in gate_names}
    valve_rejects = 0
    total_run = 0
    all_results = []

    for art_id, table, title, body in rows:
        total_run += 1
        input_url_count = len(_eu(body))
        log.info(
            "--- Sample %d/%d id=%s table=%s title=%.60s body_len=%d input_urls=%d ---",
            total_run, len(rows), art_id, table, (title or ""), len(body), input_url_count,
        )

        result = await rewrite_body_with_deepseek(title or "", body)

        if result is None:
            # Could be valve reject OR empty output — valve logs WARNING
            valve_rejects += 1
            log.info(
                "  REJECTED-BY-VALVE or EMPTY (safe outcome; not a gate failure). "
                "input_urls=%d", input_url_count,
            )
            all_results.append({
                "id": art_id,
                "table": table,
                "title": title or "",
                "status": "VALVE_REJECTED",
                "gates": {},
                "input_len": len(body),
                "output_len": 0,
                "input_url_count": input_url_count,
                "output_url_count": None,
            })
            # Write input for reference
            sample_id = f"{art_id}-{table}"
            (out_dir / f"{sample_id}-input.md").write_text(body, encoding="utf-8")
            continue

        # Run gates
        url_ok, url_msg = _gate_url(body, result)
        html_ok, html_msg = _gate_html(result)
        bp_ok, bp_msg = _gate_boilerplate(result)
        md_ok, md_msg = _gate_markdownlint(result)
        len_ok, len_msg = _gate_length(body, result)

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

        output_url_count = len(_eu(result))
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
            "id": art_id,
            "table": table,
            "title": title or "",
            "status": status,
            "gates": {g: {"pass": gate_results[g][0], "msg": gate_results[g][1]} for g in gate_names},
            "input_len": len(body),
            "output_len": len(result),
            "input_url_count": input_url_count,
            "output_url_count": output_url_count,
        })

        # Write input/output pair
        sample_id = f"{art_id}-{table}"
        (out_dir / f"{sample_id}-input.md").write_text(body, encoding="utf-8")
        (out_dir / f"{sample_id}-output.md").write_text(result, encoding="utf-8")

    # Write JSON summary
    summary = {
        "date": str(date.today()),
        "mode": "with-images" if args.with_images else "longest-body",
        "total_samples": total_run,
        "valve_rejects": valve_rejects,
        "gate_totals": gate_totals,
        "gate_passes": gate_passes,
        "results": all_results,
    }
    summary_name = (
        "validation-summary-with-images.json" if args.with_images
        else "validation-summary.json"
    )
    summary_path = out_dir / summary_name
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Print summary table
    non_rejected = total_run - valve_rejects
    valve_rate = valve_rejects / max(total_run, 1)

    print("\n" + "=" * 70)
    print("VALIDATION SUMMARY")
    print("=" * 70)
    print(f"  Samples run:       {total_run}")
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

    if gate_failures:
        print("  STATUS: FAIL — gate failures detected (see above)")
        print("  ACTION: tune the prompt in lib/rewrite.py and re-run")
    elif valve_too_high:
        print(f"  STATUS: FAIL — valve-reject rate {valve_rate:.0%} >= 30%")
        print("  ACTION: prompt is mangling image URLs; tune and re-run")
    else:
        print("  STATUS: PASS — all gates pass, valve-reject < 30%")
        print("  This harness exit-0 unblocks plan 03 backfill.")

    print(f"\n  Input/output pairs: {out_dir}")
    print(f"  JSON summary:       {summary_path}")
    print("=" * 70 + "\n")

    if gate_failures or valve_too_high:
        return 1
    return 0


def _parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="kb-v2.3 rewrite-prompt validation harness (real DeepSeek calls)"
    )
    p.add_argument(
        "--limit",
        type=int,
        default=8,
        help="Number of dirty samples to run (default 8; ordered by body length desc)",
    )
    p.add_argument(
        "--with-images",
        action="store_true",
        help="Restrict to bodies containing >= 1 http://localhost:8765/ image URL. "
             "Exercises the URL safety valve's primary defense (verbatim image-URL "
             "preservation on dirty text WITH images). Writes samples to a "
             "with-images/ subdirectory. Default (off) preserves prior behavior.",
    )
    p.add_argument(
        "--max-body-len",
        type=int,
        default=None,
        help="Skip bodies longer than this (chars). Use with --with-images to avoid "
             "the 154K-char article that exceeds the 300s per-call timeout "
             "(e.g. --max-body-len 30000).",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run_harness(args))


if __name__ == "__main__":
    raise SystemExit(main())
