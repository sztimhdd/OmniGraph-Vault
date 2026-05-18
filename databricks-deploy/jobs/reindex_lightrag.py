"""kdb-2.5 — Re-index LightRAG storage as a Databricks Job.

Modes:
  --mode smallbatch    Sample N articles (stratified by body length), measure,
                       extrapolate. Gate decision = output of this run.
  --mode fullreindex   Iterate ALL filtered candidates. Per-article exception
                       isolation. Resume from progress CSV if present.
  --mode postcheck     Sanity-verify dim=1024 vectors + bilingual coverage +
                       2 round-trip queries. Read-only against lightrag_storage.

Auth: Job runs as user identity (Bundle deploy with dev profile) with
WRITE_VOLUME on /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/.

Empty-target safety: smallbatch + fullreindex check lightrag_storage/ is
empty before first ainsert; if non-empty AND --force-overwrite NOT passed,
fail with the existing artifact mtimes in the error message.

Design:
  - Single LightRAG instance, single thread, NO ThreadPoolExecutor (D-04).
    LightRAG internal embedding_func_max_async=8 + llm_model_max_async=4
    provide 12-way HTTP concurrency. Multiple LightRAG instances corrupt
    the shared graphml / vdb_*.json files (single-writer constraint).
  - Doc-status post-check mandatory (D-05): ainsert can silently fail
    (per-chunk LLM errors caught inside apipeline_process_enqueue_documents,
    mark doc FAILED in doc_status but never raise). try/except alone is
    INSUFFICIENT — must consult aget_docs_by_ids post-ainsert.
  - Idempotency via ids=[content_hash] (D-06): LightRAG filter_keys at
    :1453 auto-skips already-PROCESSED docs on retry.

Phase: kdb-2.5
Requirements: SEED-DBX-02, SEED-DBX-03
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import logging
import random
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Databricks spark_python_task runs inside an IPython/Spark kernel that already
# has a running event loop. asyncio.run() raises "cannot be called from a running
# event loop" in that context. nest_asyncio patches the event loop to allow nested
# asyncio.run() / loop.run_until_complete() calls — same pattern used by
# kdb-1.5's config.py and the existing codebase for Databricks-hosted execution.
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass  # Not in Databricks kernel context; asyncio.run() will work fine

# databricks-deploy/ is hyphenated — not importable as a package.
# Add it to sys.path so we can import lightrag_databricks_provider directly.
#
# Pitfall: spark_python_task runs the script via exec(), which does NOT set
# __file__ in the global namespace. Use sys.argv[0] as the script path fallback.
# In the Bundle workspace layout, the file lands at:
#   .bundle/<bundle>/dev/files/jobs/reindex_lightrag.py
# so HERE.parent == files/ == bundle root (where lightrag_databricks_provider.py is).
try:
    HERE = Path(__file__).resolve().parent
except NameError:
    # spark_python_task exec() context: __file__ is not set
    HERE = Path(sys.argv[0]).resolve().parent
sys.path.insert(0, str(HERE.parent))  # databricks-deploy/ (local) or files/ (workspace)

from lightrag_databricks_provider import (  # noqa: E402
    EMBEDDING_DIM,
    KB_LLM_MODEL,
    make_embedding_func,
    make_llm_func,
)

logger = logging.getLogger("kdb-2.5")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

# Volume layout (locked per STATE rev 3):
#   /Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault/
#     data/kol_scan.db              <- source DB (READ_VOLUME)
#     lightrag_storage/             <- re-index output (WRITE_VOLUME)
#     output/kdb-2.5-progress.csv
#     output/kdb-2.5-FAILURES.csv
#     output/kdb-2.5-smallbatch-stats.json
#     output/kdb-2.5-postcheck-stats.json
VOLUME_ROOT = "/Volumes/mdlg_ai_shared/kb_v2/omnigraph_vault"
DB_PATH = f"{VOLUME_ROOT}/data/kol_scan.db"
LIGHTRAG_DIR = f"{VOLUME_ROOT}/lightrag_storage"

# UC Volume FUSE does not support seek-based I/O (open("a") triggers EILSEQ / Errno 29).
# Strategy: write progress/failures CSVs to /tmp/ (local ephemeral disk, no FUSE seek
# restrictions), then copy full file to Volume output/ after each N articles.
# At run START, we read from Volume output/ to restore resume state, then write to /tmp/.
_TMP_PROGRESS_CSV = "/tmp/kdb-2.5-progress.csv"
_TMP_FAILURES_CSV = "/tmp/kdb-2.5-FAILURES.csv"

# Volume paths for persistence (read at start, written at end / periodically)
PROGRESS_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-progress.csv"
FAILURES_CSV = f"{VOLUME_ROOT}/output/kdb-2.5-FAILURES.csv"

# How often to sync local /tmp/ CSV to Volume (in articles written)
_VOLUME_SYNC_EVERY_N = 10

# Step-1 extrapolation baseline (populated after first smallbatch run,
# read by _compute_burn_rate_ratio during Step 2).
_STEP1_BASELINE_PATH = f"{VOLUME_ROOT}/output/kdb-2.5-smallbatch-stats.json"

# DATA-07 strict filter (hardcoded per D-01 — matches kb/data/article_query.py):
#   body IS NOT NULL AND body != ''
#   AND content_hash IS NOT NULL
#   AND layer1_verdict = 'candidate'
#   AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')
_DATA07_STRICT_LAYER_CLAUSE = (
    "AND layer1_verdict = 'candidate' "
    "AND (layer2_verdict IS NULL OR layer2_verdict != 'reject')"
)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateRow:
    """Single re-index candidate row from kol_scan.db.

    Immutable frozen dataclass per common/coding-style.md.
    """

    source_table: str    # 'articles' | 'rss_articles'
    content_hash: str
    title: str
    body: str
    lang: str | None


@dataclass(frozen=True)
class IngestResult:
    """Outcome of a single ainsert call.

    status:
      'ok'      — ainsert completed AND doc_status == PROCESSED
      'failed'  — ainsert raised OR doc_status in {FAILED, unknown}
      'skipped' — already in graph (LightRAG duplicate-hash detection)
    """

    content_hash: str
    source_table: str
    status: Literal["ok", "failed", "skipped"]
    elapsed_s: float
    error_truncated: str | None   # 200-char trimmed repr(e), no PII / path
    track_id: str | None


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------

def _load_candidates(
    db_path: str,
    *,
    filter_mode: str = "strict",
    sample_n: int | None = None,
) -> list[CandidateRow]:
    """Load filtered re-index candidates from kol_scan.db.

    filter_mode values:
      'strict'      — DATA-07: body NOT NULL + layer1=candidate + layer2 != reject
      'layer1-only' — body NOT NULL + layer1=candidate (ignore layer2)
      'all'         — body NOT NULL only (no layer filtering)

    Default is 'strict' (D-01: hardcoded scope; --filter-mode kept for testing).

    sample_n: if set, returns N rows stratified across body-length quintiles
    (5 buckets, sample_n // 5 from each).  random.seed(42) for determinism.
    """
    if filter_mode == "strict":
        layer_clause = _DATA07_STRICT_LAYER_CLAUSE
    elif filter_mode == "layer1-only":
        layer_clause = "AND layer1_verdict = 'candidate'"
    elif filter_mode == "all":
        layer_clause = ""
    else:
        raise ValueError(f"Unknown filter_mode={filter_mode!r}")

    # UNION ALL of articles + rss_articles with the same WHERE shape.
    # Both tables have: content_hash, title, body, layer1_verdict, layer2_verdict.
    # 'lang' may be absent in older prod DB snapshots — we introspect PRAGMA
    # table_info() and fall back to NULL AS lang if the column is missing.
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as _probe:
        def _has_col(table: str, col: str) -> bool:
            cols = {r[1] for r in _probe.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()}
            return col in cols
        articles_lang = "lang" if _has_col("articles", "lang") else "NULL"
        rss_lang = "lang" if _has_col("rss_articles", "lang") else "NULL"

    sql = f"""
        SELECT 'articles' AS source_table,
               content_hash, title, body, {articles_lang} AS lang
        FROM articles
        WHERE body IS NOT NULL
          AND body != ''
          AND content_hash IS NOT NULL
          {layer_clause}
        UNION ALL
        SELECT 'rss_articles' AS source_table,
               content_hash, title, body, {rss_lang} AS lang
        FROM rss_articles
        WHERE body IS NOT NULL
          AND body != ''
          AND content_hash IS NOT NULL
          {layer_clause}
        ORDER BY content_hash
    """
    with sqlite3.connect(uri, uri=True) as conn:
        rows: list[CandidateRow] = [
            CandidateRow(
                source_table=row[0],
                content_hash=row[1],
                title=row[2] or "",
                body=row[3],
                lang=row[4],
            )
            for row in conn.execute(sql).fetchall()
        ]

    if sample_n is None:
        return rows

    # Stratified sample: sort by body length, divide into 5 ntiles,
    # draw sample_n // 5 from each bucket. random.seed(42) for determinism.
    rows_sorted = sorted(rows, key=lambda r: len(r.body))
    n = len(rows_sorted)
    bucket_size = max(1, n // 5)
    per_bucket = max(1, sample_n // 5)
    sampled: list[CandidateRow] = []
    random.seed(42)
    for b in range(5):
        start = b * bucket_size
        end = (b + 1) * bucket_size if b < 4 else n
        bucket = rows_sorted[start:end]
        draw = min(per_bucket, len(bucket))
        sampled.extend(random.sample(bucket, draw))
    return sampled


# ---------------------------------------------------------------------------
# Empty-target safety (D-07)
# ---------------------------------------------------------------------------

def _verify_target_empty(
    *,
    lightrag_dir: str,
    force_overwrite: bool,
) -> None:
    """Empty-target safety check.

    Raises RuntimeError on non-empty + no --force-overwrite flag.
    Lists existing artifacts + mtimes so the operator can decide.

    ROADMAP rev 3 line 169: 'Job must NOT silently overwrite existing
    lightrag_storage/ if previously populated.'
    """
    p = Path(lightrag_dir)
    if not p.exists():
        return
    existing = sorted(p.iterdir())
    if not existing:
        return

    if force_overwrite:
        logger.warning(
            "kdb-2.5: --force-overwrite passed; %d existing artifacts in %s "
            "will be overwritten. This is intentional.",
            len(existing),
            lightrag_dir,
        )
        return

    # Build an informative error with up to 10 artifact mtimes.
    mtimes = "\n".join(
        f"  {f.name:50s}  mtime={time.ctime(f.stat().st_mtime)}"
        for f in existing[:10]
    )
    raise RuntimeError(
        f"kdb-2.5 EMPTY-TARGET CHECK FAILED:\n"
        f"  {lightrag_dir!r} contains {len(existing)} artifact(s):\n"
        f"{mtimes}\n"
        f"  To overwrite intentionally, re-run with --force-overwrite.\n"
        f"  To resume an interrupted run, the existing artifacts are preserved;\n"
        f"  see {PROGRESS_CSV} for already-processed hashes."
    )


# ---------------------------------------------------------------------------
# Per-article ingestion (D-05 + D-06)
# ---------------------------------------------------------------------------

async def _ingest_one(rag, row: CandidateRow) -> IngestResult:
    """Ingest a single article into LightRAG.

    Wraps ainsert with broad exception trap (per-article isolation — single
    failure must NOT propagate to the batch).

    D-05: Mandatory doc_status post-check.  ainsert can silently fail —
    per-chunk LLM errors are caught inside apipeline_process_enqueue_documents,
    mark doc FAILED in doc_status, and do NOT re-raise.  try/except alone
    is INSUFFICIENT; we must consult aget_docs_by_ids post-ainsert.

    D-06: ids=[row.content_hash] — explicit ID for LightRAG idempotency.
    Re-runs auto-skip PROCESSED docs (filter_keys at lightrag.py:1453).
    """
    t0 = time.time()
    try:
        track_id = await rag.ainsert(
            row.body,
            ids=[row.content_hash],
            file_paths=[f"{row.source_table}/{row.content_hash}"],
        )
        # D-05: Post-ainsert doc_status check.
        # When ainsert(ids=[hash]) explicitly passes ids, LightRAG uses the raw
        # hash as the doc_status key (lightrag.py:1395-1415 — `contents = {id_:
        # {...}}`, id_ used verbatim). When ids=None, LightRAG auto-prefixes
        # with `doc-` (line 1426). We always pass ids=[content_hash] (D-06),
        # so the post-check key is the raw content_hash WITHOUT prefix.
        # API path: LightRAG.aget_docs_by_ids() (main class, async, returns
        # dict[doc_id, DocProcessingStatus]) — NOT rag.doc_status.get_docs_by_ids
        # (the storage class doesn't expose that method).
        # See lightrag/lightrag.py:3159 for the canonical signature.
        doc_id = row.content_hash
        status_records = await rag.aget_docs_by_ids([doc_id])
        if doc_id not in status_records:
            # No record in doc_status — treat as unexpected failure
            doc_status_val = "unknown"
        else:
            doc_status_val = status_records[doc_id].status.value

        if doc_status_val == "PROCESSED":
            return IngestResult(
                content_hash=row.content_hash,
                source_table=row.source_table,
                status="ok",
                elapsed_s=time.time() - t0,
                error_truncated=None,
                track_id=track_id,
            )
        elif doc_status_val in ("FAILED",):
            return IngestResult(
                content_hash=row.content_hash,
                source_table=row.source_table,
                status="failed",
                elapsed_s=time.time() - t0,
                error_truncated=(
                    f"doc_status=FAILED for hash {row.content_hash[:10]}"
                ),
                track_id=track_id,
            )
        else:
            # PENDING / PROCESSING / unknown — unexpected post-ainsert state
            return IngestResult(
                content_hash=row.content_hash,
                source_table=row.source_table,
                status="failed",
                elapsed_s=time.time() - t0,
                error_truncated=(
                    f"doc_status={doc_status_val} (unexpected) "
                    f"for hash {row.content_hash[:10]}"
                ),
                track_id=track_id,
            )

    except Exception as e:  # noqa: BLE001 — broad on purpose; isolate failure
        # Truncate to 200 chars; strip path separators to avoid path leaks.
        raw_err = repr(e)[:200]
        err = raw_err.replace("/", " ").replace("\\", " ")
        logger.exception(
            "ainsert failed for hash %s table=%s",
            row.content_hash[:10],
            row.source_table,
        )
        return IngestResult(
            content_hash=row.content_hash,
            source_table=row.source_table,
            status="failed",
            elapsed_s=time.time() - t0,
            error_truncated=err,
            track_id=None,
        )


# ---------------------------------------------------------------------------
# LightRAG factory
# ---------------------------------------------------------------------------

async def _instantiate_lightrag(working_dir: str):
    """Construct a LightRAG instance using the kdb-1.5 frozen factories.

    Consumes make_llm_func() + make_embedding_func() from
    lightrag_databricks_provider (imported at module top via sys.path.insert).
    """
    from lightrag.lightrag import LightRAG  # noqa: PLC0415

    rag = LightRAG(
        working_dir=working_dir,
        llm_model_func=make_llm_func(),
        embedding_func=make_embedding_func(),
    )
    if hasattr(rag, "initialize_storages"):
        await rag.initialize_storages()
    logger.info(
        "_instantiate_lightrag: LightRAG ready in %s (model=%s, dim=%d)",
        working_dir,
        KB_LLM_MODEL,
        EMBEDDING_DIM,
    )
    return rag


# ---------------------------------------------------------------------------
# Progress / failures CSV helpers
# ---------------------------------------------------------------------------

def _csv_line(*fields: str) -> str:
    """Format one CSV row without using csv.writer (avoids UC FUSE seek issues)."""
    parts = []
    for f in fields:
        s = str(f)
        if any(c in s for c in (',', '"', '\n', '\r')):
            s = '"' + s.replace('"', '""') + '"'
        parts.append(s)
    return ",".join(parts) + "\n"


def _init_tmp_csv(volume_path: str, tmp_path: str) -> None:
    """Copy Volume CSV to /tmp/ at startup to seed cross-run resume state.

    If the Volume path exists, copy it to tmp_path so _load_progress_hashes
    can read from /tmp/ and we avoid UC FUSE seek throughout the run.
    If Volume path is absent, create an empty /tmp/ file so subsequent appends
    start with a fresh header.
    """
    v = Path(volume_path)
    t = Path(tmp_path)
    if v.exists():
        import shutil
        shutil.copy2(str(v), str(t))
        logger.info("_init_tmp_csv: copied %s → %s (%d bytes)", v, t, t.stat().st_size)
    else:
        # No prior run — start fresh (header written by first _append_progress call)
        if t.exists():
            t.unlink()
        logger.info("_init_tmp_csv: no Volume CSV at %s, starting fresh", v)


def _sync_csv_to_volume(tmp_path: str, volume_path: str) -> None:
    """Copy /tmp/ CSV to Volume for persistence (full-file overwrite, no seek).

    UC Volume FUSE supports full-file write (open "w" + write_text / copyfile)
    but NOT seek-based append ("a" mode).  We write the complete /tmp/ file
    over the Volume path every _VOLUME_SYNC_EVERY_N articles.
    """
    t = Path(tmp_path)
    if not t.exists():
        return
    v = Path(volume_path)
    v.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(str(t), str(v))
    logger.info("_sync_csv_to_volume: synced %d bytes → %s", t.stat().st_size, v)


def _append_progress(r: IngestResult) -> None:
    """Append one row to the progress CSV in /tmp/ (seek-safe local disk).

    UC Volume FUSE does not support seek-based I/O (open("a") triggers
    OSError EILSEQ / Errno 29 on the first text-mode append).  We write
    exclusively to _TMP_PROGRESS_CSV (/tmp/) and sync to Volume periodically
    via _sync_csv_to_volume.
    """
    p = Path(_TMP_PROGRESS_CSV)
    new_file = not p.exists()
    with p.open("a", encoding="utf-8") as f:
        if new_file:
            f.write(_csv_line(
                "content_hash", "source_table", "status",
                "elapsed_s", "error_truncated", "track_id", "ts",
            ))
        f.write(_csv_line(
            r.content_hash,
            r.source_table,
            r.status,
            f"{r.elapsed_s:.2f}",
            r.error_truncated or "",
            r.track_id or "",
            str(time.time()),
        ))


def _append_failures_csv(r: IngestResult) -> None:
    """Append a failed article to the FAILURES CSV in /tmp/.

    Same /tmp/ strategy as _append_progress — UC FUSE seek-safe.
    """
    p = Path(_TMP_FAILURES_CSV)
    new_file = not p.exists()
    with p.open("a", encoding="utf-8") as f:
        if new_file:
            f.write(_csv_line("content_hash", "source_table", "error_truncated"))
        f.write(_csv_line(
            r.content_hash,
            r.source_table,
            r.error_truncated or "",
        ))


def _load_progress_hashes(*, status_filter: set[str]) -> set[str]:
    """Return content_hashes from the /tmp/ progress CSV matching status_filter.

    Reads from _TMP_PROGRESS_CSV (/tmp/), which is seeded from Volume at
    run start by _init_tmp_csv.  Falls back to PROGRESS_CSV (Volume) if
    /tmp/ file is absent (safety net for callers that skip _init_tmp_csv).
    """
    # Prefer /tmp/ (seeded at startup); fall back to Volume path.
    p = Path(_TMP_PROGRESS_CSV)
    if not p.exists():
        p = Path(PROGRESS_CSV)
    if not p.exists():
        return set()
    out: set[str] = set()
    with p.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("status") in status_filter:
                out.add(row["content_hash"])
    return out


# ---------------------------------------------------------------------------
# Burn-rate monitoring
# ---------------------------------------------------------------------------

def _compute_burn_rate_ratio(t_start: float, articles_done: int) -> float:
    """Compare current wallclock burn-rate to Step-1 extrapolation.

    Returns ratio: >1.5 triggers a BURN-RATE WARNING log in Step 2.
    Falls back to 1.0 if no baseline (Step 1 not yet run).
    """
    if articles_done < 1:
        return 1.0
    elapsed = time.time() - t_start
    current_per_article = elapsed / articles_done

    # Read Step-1 baseline from the stats JSON
    baseline_path = Path(_STEP1_BASELINE_PATH)
    if not baseline_path.exists():
        return 1.0
    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline_per_article = data.get("avg_wallclock_per_ok", 0.0)
        if baseline_per_article <= 0:
            return 1.0
        return current_per_article / baseline_per_article
    except Exception:  # noqa: BLE001
        return 1.0


# ---------------------------------------------------------------------------
# Findings / stats writers
# ---------------------------------------------------------------------------

def _write_smallbatch_findings(
    *,
    results: list[IngestResult],
    elapsed_total_s: float,
    avg_wallclock: float,
    full_corpus_size: int,
) -> None:
    """Write kdb-2.5-smallbatch-stats.json to Volume output/.

    The executor combines this JSON with the MosaicAI billing dashboard
    data to author kdb-2.5-SMALLBATCH-FINDINGS.md with the cost gate.
    """
    stats_path = Path(VOLUME_ROOT) / "output" / "kdb-2.5-smallbatch-stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)

    n_ok = sum(1 for r in results if r.status == "ok")
    n_failed = sum(1 for r in results if r.status == "failed")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    failure_rate = n_failed / max(len(results), 1)

    stats = {
        "n_results": len(results),
        "n_ok": n_ok,
        "n_failed": n_failed,
        "n_skipped": n_skipped,
        "failure_rate": round(failure_rate, 4),
        "elapsed_total_s": round(elapsed_total_s, 2),
        "avg_wallclock_per_ok": round(avg_wallclock, 2),
        "full_corpus_size": full_corpus_size,
        "gate_criterion_failure_rate_ok": failure_rate <= 0.05,
        # Token counts are NOT available from inside the Job (they require
        # querying the MosaicAI billing API or Dashboard).
        # Executor must fill these from the billing dashboard after the run:
        "avg_sonnet_input_tokens_per_article": None,   # fill from dashboard
        "avg_sonnet_output_tokens_per_article": None,  # fill from dashboard
        "avg_embedding_tokens_per_article": None,      # fill from dashboard
        "step1_actual_cost_usd": None,                 # fill from dashboard
    }
    stats_path.write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("smallbatch-stats.json written to %s", stats_path)


def _write_postcheck_findings(
    *,
    embedding_dim: int,
    n_zh: int,
    n_en: int,
    resp_zh_excerpt: str,
    resp_en_excerpt: str,
) -> None:
    """Write kdb-2.5-postcheck-stats.json to Volume output/."""
    stats_path = Path(VOLUME_ROOT) / "output" / "kdb-2.5-postcheck-stats.json"
    stats_path.parent.mkdir(parents=True, exist_ok=True)
    stats_path.write_text(
        json.dumps({
            "embedding_dim": embedding_dim,
            "bilingual_zh_count_in_sample": n_zh,
            "bilingual_en_count_in_sample": n_en,
            "zh_response_excerpt": resp_zh_excerpt,
            "en_response_excerpt": resp_en_excerpt,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("postcheck-stats.json written to %s", stats_path)


# ---------------------------------------------------------------------------
# Mode runners
# ---------------------------------------------------------------------------

async def _run_smallbatch(args) -> int:
    """Step 1: Sample N articles (stratified), measure, write stats.

    Returns 0 if failure_rate <= 5%, 2 if higher (SUCCEEDED_WITH_FAILURES).
    """
    candidates = _load_candidates(
        args.db_path,
        filter_mode=args.filter_mode,
        sample_n=args.max_articles,
    )
    logger.info(
        "smallbatch: %d candidates sampled (filter_mode=%s, max_articles=%d)",
        len(candidates),
        args.filter_mode,
        args.max_articles,
    )
    if not candidates:
        logger.error(
            "smallbatch: 0 candidates returned — check DATA-07 filter "
            "and DB path=%s",
            args.db_path,
        )
        return 1

    # Seed /tmp/ CSV from Volume (cross-run resume; no-op on first run).
    _init_tmp_csv(PROGRESS_CSV, _TMP_PROGRESS_CSV)
    _init_tmp_csv(FAILURES_CSV, _TMP_FAILURES_CSV)

    # D-07: Empty-target check before touching lightrag_storage.
    _verify_target_empty(
        lightrag_dir=args.lightrag_dir,
        force_overwrite=args.force_overwrite,
    )

    rag = await _instantiate_lightrag(args.lightrag_dir)

    results: list[IngestResult] = []
    t_total0 = time.time()

    for i, row in enumerate(candidates):
        logger.info(
            "smallbatch %d/%d: hash=%s source=%s body_len=%d",
            i + 1,
            len(candidates),
            row.content_hash[:10],
            row.source_table,
            len(row.body),
        )
        r = await _ingest_one(rag, row)
        results.append(r)
        _append_progress(r)
        # Periodic sync to Volume every N articles so we don't lose all progress
        # on a mid-run failure.
        if (i + 1) % _VOLUME_SYNC_EVERY_N == 0:
            _sync_csv_to_volume(_TMP_PROGRESS_CSV, PROGRESS_CSV)

    elapsed_total = time.time() - t_total0

    n_ok = sum(1 for r in results if r.status == "ok")
    n_failed = sum(1 for r in results if r.status == "failed")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    avg_wallclock = (
        sum(r.elapsed_s for r in results if r.status == "ok") / max(n_ok, 1)
    )

    logger.info(
        "smallbatch DONE: total=%.1fs ok=%d failed=%d skipped=%d "
        "avg_wallclock_per_ok=%.2fs",
        elapsed_total,
        n_ok,
        n_failed,
        n_skipped,
        avg_wallclock,
    )

    # Load full corpus size for the extrapolation formula in FINDINGS.
    full_corpus_size = len(
        _load_candidates(args.db_path, filter_mode=args.filter_mode)
    )

    # Final sync of /tmp/ CSVs to Volume before writing stats JSON.
    _sync_csv_to_volume(_TMP_PROGRESS_CSV, PROGRESS_CSV)

    _write_smallbatch_findings(
        results=results,
        elapsed_total_s=elapsed_total,
        avg_wallclock=avg_wallclock,
        full_corpus_size=full_corpus_size,
    )

    if args.shutdown_lightrag and hasattr(rag, "finalize_storages"):
        await rag.finalize_storages()

    failure_rate = n_failed / max(len(results), 1)
    return 0 if failure_rate <= 0.05 else 2


async def _run_fullreindex(args) -> int:
    """Step 2: Full re-index of all filtered candidates.

    Supports resume: reads PROGRESS_CSV, skips already-OK hashes.
    Returns 0 if failure_rate <= 5%, 2 if higher.
    """
    candidates = _load_candidates(
        args.db_path,
        filter_mode=args.filter_mode,
    )
    logger.info(
        "fullreindex: %d total candidates loaded (filter_mode=%s)",
        len(candidates),
        args.filter_mode,
    )
    if not candidates:
        logger.error(
            "fullreindex: 0 candidates — check DATA-07 filter and DB path=%s",
            args.db_path,
        )
        return 1

    # D-07: Empty-target check.
    _verify_target_empty(
        lightrag_dir=args.lightrag_dir,
        force_overwrite=args.force_overwrite,
    )

    # Seed /tmp/ CSV from Volume (cross-run resume; no-op on first run).
    _init_tmp_csv(PROGRESS_CSV, _TMP_PROGRESS_CSV)
    _init_tmp_csv(FAILURES_CSV, _TMP_FAILURES_CSV)

    # Resume support: skip already-OK articles (D-06 + progress CSV).
    done_hashes = _load_progress_hashes(status_filter={"ok"})
    if done_hashes:
        logger.info(
            "fullreindex: resume — skipping %d already-OK hashes",
            len(done_hashes),
        )
        candidates = [r for r in candidates if r.content_hash not in done_hashes]
        logger.info(
            "fullreindex: %d candidates remaining after resume filter",
            len(candidates),
        )

    rag = await _instantiate_lightrag(args.lightrag_dir)

    results: list[IngestResult] = []
    t_total0 = time.time()

    for i, row in enumerate(candidates):
        logger.info(
            "fullreindex %d/%d: hash=%s source=%s body_len=%d",
            i + 1,
            len(candidates),
            row.content_hash[:10],
            row.source_table,
            len(row.body),
        )
        r = await _ingest_one(rag, row)
        results.append(r)
        _append_progress(r)

        if r.status == "failed":
            _append_failures_csv(r)
            logger.warning(
                "fullreindex: FAILURE hash=%s error=%s",
                r.content_hash[:10],
                r.error_truncated,
            )

        # Periodic sync of /tmp/ CSVs to Volume.
        if (i + 1) % _VOLUME_SYNC_EVERY_N == 0:
            _sync_csv_to_volume(_TMP_PROGRESS_CSV, PROGRESS_CSV)
            _sync_csv_to_volume(_TMP_FAILURES_CSV, FAILURES_CSV)

        # Burn-rate alert every 25 articles.
        if (i + 1) % 25 == 0:
            ratio = _compute_burn_rate_ratio(t_total0, i + 1)
            if ratio > 1.5:
                logger.warning(
                    "fullreindex BURN-RATE alert: %.2fx Step-1 extrapolation "
                    "after %d articles. Consider stopping and re-extrapolating.",
                    ratio,
                    i + 1,
                )

    elapsed_total = time.time() - t_total0
    n_ok = sum(1 for r in results if r.status == "ok")
    n_failed = sum(1 for r in results if r.status == "failed")
    n_skipped = sum(1 for r in results if r.status == "skipped")
    failure_rate = n_failed / max(len(results), 1)

    logger.info(
        "fullreindex DONE: total=%.1fs ok=%d failed=%d skipped=%d "
        "failure_rate=%.2f%%",
        elapsed_total,
        n_ok,
        n_failed,
        n_skipped,
        failure_rate * 100,
    )

    # Final sync of /tmp/ CSVs to Volume.
    _sync_csv_to_volume(_TMP_PROGRESS_CSV, PROGRESS_CSV)
    _sync_csv_to_volume(_TMP_FAILURES_CSV, FAILURES_CSV)

    if args.shutdown_lightrag and hasattr(rag, "finalize_storages"):
        await rag.finalize_storages()

    return 0 if failure_rate <= 0.05 else 2


async def _run_postcheck(args) -> int:
    """Step 3: Read-only sanity check of lightrag_storage.

    Verifies:
    1. vdb_entities.json exists and has embedding_dim == 1024 (D-05 artifact)
    2. Bilingual coverage: >=10 zh + >=10 en entities in 200-sample
    3. Two round-trip aquery calls (1 zh + 1 en) return >= 50 chars each
    """
    rag = await _instantiate_lightrag(args.lightrag_dir)

    # 1. Embedding dim check
    vdb_entities_path = Path(args.lightrag_dir) / "vdb_entities.json"
    if not vdb_entities_path.exists():
        logger.error(
            "postcheck FAIL: vdb_entities.json missing in %s — "
            "re-index may be incomplete",
            args.lightrag_dir,
        )
        return 1

    with vdb_entities_path.open(encoding="utf-8") as f:
        vdb_data = json.load(f)

    embedding_dim = vdb_data.get("embedding_dim")
    if embedding_dim != EMBEDDING_DIM:
        logger.error(
            "postcheck FAIL: embedding_dim=%s in vdb_entities.json "
            "(expected %d)",
            embedding_dim,
            EMBEDDING_DIM,
        )
        return 1

    logger.info("postcheck: embedding_dim=%d verified in vdb_entities.json", embedding_dim)

    # 2. Bilingual coverage — sample up to 200 entity names
    matrix = (
        vdb_data.get("data")
        or vdb_data.get("matrix")
        or vdb_data.get("__data__")
        or []
    )
    sample_entity_names: list[str] = []
    for item in matrix[:200]:
        name = None
        if isinstance(item, dict):
            name = item.get("entity_name") or item.get("__id__") or item.get("id")
        if name:
            sample_entity_names.append(str(name))

    n_zh = sum(
        1 for n in sample_entity_names
        if any("一" <= c <= "鿿" for c in n)
    )
    n_en = sum(
        1 for n in sample_entity_names
        if n and not any("一" <= c <= "鿿" for c in n)
    )
    logger.info(
        "postcheck: bilingual sample (n=%d): zh=%d en=%d",
        len(sample_entity_names),
        n_zh,
        n_en,
    )
    if n_zh < 10 or n_en < 10:
        logger.warning(
            "postcheck WARNING: bilingual coverage may be uneven "
            "(zh=%d, en=%d, expected >=10 each); continuing",
            n_zh,
            n_en,
        )

    # 3. Round-trip queries — 1 zh + 1 en
    from lightrag.lightrag import QueryParam  # noqa: PLC0415

    resp_zh = await rag.aquery(
        "LangGraph 与 CrewAI 的对比",
        QueryParam(mode="hybrid"),
    )
    resp_en = await rag.aquery(
        "compare LangGraph and CrewAI frameworks",
        QueryParam(mode="hybrid"),
    )

    logger.info(
        "postcheck: zh response len=%d, en response len=%d",
        len(resp_zh),
        len(resp_en),
    )

    if len(resp_zh) < 50 or len(resp_en) < 50:
        logger.error(
            "postcheck FAIL: round-trip queries returned short responses "
            "(zh=%d chars, en=%d chars)",
            len(resp_zh),
            len(resp_en),
        )
        return 1

    _write_postcheck_findings(
        embedding_dim=embedding_dim,
        n_zh=n_zh,
        n_en=n_en,
        resp_zh_excerpt=resp_zh[:400],
        resp_en_excerpt=resp_en[:400],
    )

    logger.info("postcheck PASS")

    if args.shutdown_lightrag and hasattr(rag, "finalize_storages"):
        await rag.finalize_storages()

    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    """Databricks Job entry point (spark_python_task).

    asyncio.run() wraps the async mode runners.
    """
    parser = argparse.ArgumentParser(
        description="kdb-2.5 Re-index LightRAG storage as a Databricks Job"
    )
    parser.add_argument(
        "--mode",
        choices=["smallbatch", "fullreindex", "postcheck"],
        required=True,
        help="Operation mode",
    )
    parser.add_argument(
        "--db-path",
        default=DB_PATH,
        help=f"Path to kol_scan.db (default: {DB_PATH})",
    )
    parser.add_argument(
        "--lightrag-dir",
        default=LIGHTRAG_DIR,
        help=f"LightRAG working_dir (default: {LIGHTRAG_DIR})",
    )
    parser.add_argument(
        "--filter-mode",
        choices=["strict", "layer1-only", "all"],
        default="strict",
        help="Corpus filter mode. Default 'strict' = DATA-07 (D-01 hardcoded)",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=50,
        help="Smallbatch: number of articles to sample (default 50)",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help=(
            "Allow writing to non-empty lightrag_dir. "
            "Dangerous: pass only on intentional overwrite. "
            "Do NOT include in Job YAML default parameters (D-07)."
        ),
    )
    parser.add_argument(
        "--shutdown-lightrag",
        action="store_true",
        help=(
            "Call rag.finalize_storages() before exit "
            "(default off — keep state between sequential runs)"
        ),
    )

    args = parser.parse_args(argv)

    logger.info(
        "kdb-2.5 starting: mode=%s db=%s lightrag_dir=%s filter=%s",
        args.mode,
        args.db_path,
        args.lightrag_dir,
        args.filter_mode,
    )

    if args.mode == "smallbatch":
        return asyncio.run(_run_smallbatch(args))
    if args.mode == "fullreindex":
        return asyncio.run(_run_fullreindex(args))
    if args.mode == "postcheck":
        return asyncio.run(_run_postcheck(args))

    raise ValueError(f"Unknown mode: {args.mode!r}")


if __name__ == "__main__":
    sys.exit(main())
