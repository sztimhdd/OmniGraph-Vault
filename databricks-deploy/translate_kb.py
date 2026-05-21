# Databricks notebook source
# MAGIC %md
# MAGIC # kb-v2.2-7 — KB bilingual translation (manual one-shot)
# MAGIC
# MAGIC Translates `articles` + `rss_articles` rows where DATA-07 passes (`L1='candidate' AND L2='ok'`)
# MAGIC and `body_translated IS NULL` (idempotent — re-running "Run all" only translates new rows).
# MAGIC
# MAGIC **Manual trigger only.** No bundle yaml, no scheduling, no automation.
# MAGIC Run via Databricks workspace "Run all" after a Hermes ingest cron has produced fresh L2='ok' rows.
# MAGIC
# MAGIC ## Workflow (operator)
# MAGIC
# MAGIC 1. **On Hermes (pre-step, run BEFORE this notebook):**
# MAGIC    ```
# MAGIC    sqlite3 ~/OmniGraph-Vault/data/kol_scan.db ".backup /tmp/kol_scan.db.snap"
# MAGIC    ```
# MAGIC    Out-of-process snapshot avoids SQLite write-lock contention with the live ingest cron.
# MAGIC    NOTE: live DB is at `~/OmniGraph-Vault/data/kol_scan.db` (not the empty placeholder
# MAGIC    `~/.hermes/omonigraph-vault/kol_scan.db`).
# MAGIC
# MAGIC 2. **In Databricks:** open this notebook, click **Run all**.
# MAGIC    Cells 1→7 execute sequentially: SCP pull → SELECT → translate (Opus + Tavily) →
# MAGIC    UPDATE local → generate SQL apply file → SCP push apply.sql → summary.
# MAGIC    Cell 6 (apply on Hermes) is operator-gated — run during quiet window.
# MAGIC
# MAGIC 3. **On Hermes (post-step, in quiet window — avoid 09:00/14:00/21:00 ADT cron):**
# MAGIC    Apply UPDATE statements to live DB (does NOT overwrite — only merges translation cols):
# MAGIC    ```
# MAGIC    cp ~/OmniGraph-Vault/data/kol_scan.db ~/OmniGraph-Vault/data/kol_scan.db.bak-pre-translate
# MAGIC    sqlite3 ~/OmniGraph-Vault/data/kol_scan.db < /tmp/kol_scan_apply.sql
# MAGIC    ```
# MAGIC    (Cell 6 automates this via SSH if operator un-comments the trigger.)
# MAGIC
# MAGIC ## Workspace secret scope: `kb-translate`
# MAGIC
# MAGIC | Key | Value |
# MAGIC |---|---|
# MAGIC | `hermes_host` | Hermes SSH hostname |
# MAGIC | `hermes_port` | Hermes SSH port |
# MAGIC | `hermes_user` | Hermes SSH username |
# MAGIC | `hermes_ssh_key` | Full PEM private key contents (multi-line) |
# MAGIC
# MAGIC Operator sets these once via `databricks secrets put-secret kb-translate <key>` before the first run.
# MAGIC No literal credentials in this notebook.
# MAGIC
# MAGIC ## What this notebook does NOT do
# MAGIC
# MAGIC - Does NOT auto-promote the translated DB on Hermes (operator does step 3 manually after verifying)
# MAGIC - Does NOT block UPDATE on the post-LLM image-count safety check (log-only; UAT scenario 9 is the gate)
# MAGIC - Does NOT delete or modify rows where `body_translated IS NOT NULL` (idempotent guard)
# MAGIC - Does NOT translate rows that fail DATA-07 (`L1!='candidate'` OR `L2!='ok'`) — they are filtered out

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 1 — Config + SCP pull from Hermes
# MAGIC
# MAGIC Reads SSH credentials from workspace secret scope `kb-translate`, writes the
# MAGIC private key to a 0600-mode tmp file, then SCPs the snapshot from Hermes.

# COMMAND ----------

import json
import os
import re
import stat
import subprocess
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

# Local paths inside the Databricks driver node
LOCAL_DB_PATH = "/tmp/kol_scan.db"
LOCAL_KEY_PATH = "/tmp/hermes_key"
LOCAL_APPLY_SQL_PATH = "/tmp/kol_scan_apply.sql"

# Hermes-side staging paths. Operator pre-step writes the snapshot to .snap;
# this notebook pushes ONLY the SQL apply file (UPDATE statements) — never the
# whole DB — so applying on Hermes merges translation columns and does not
# overwrite ingest-cron rows that landed after the SCP-pull.
HERMES_SNAPSHOT_PATH = "/tmp/kol_scan.db.snap"
HERMES_APPLY_SQL_PATH = "/tmp/kol_scan_apply.sql"

# Hermes-side live DB path (used only by the optional operator-gated apply in cell 6).
HERMES_LIVE_DB_PATH = "~/OmniGraph-Vault/data/kol_scan.db"

# Translation model — Opus 4.7 for highest quality (one-shot bilingual backfill;
# quality dominates throughput per user spec).
TRANSLATION_MODEL = "databricks-claude-opus-4-7"

# Per-call LLM retry budget (1 translate + up to 3 retries on malformed JSON).
# Tavily HTTP calls do not count toward this budget. Applied per LLM call (single-shot
# row, single chunk, or single title) — chunked mode multiplies total calls per row.
MAX_LLM_CALLS_PER_ROW = 4

# Body-length threshold: above this, chunk on paragraph boundaries.
# Most candidates are < 15KB; only ~17 of 238 exceed 20KB. Smaller chunks give
# the model more headroom under the per-HTTP-call timeout.
BODY_CHUNK_THRESHOLD = 15_000
# Target chunk size when splitting a long body. Tighter than threshold so each
# chunk's generation completes well under the per-HTTP-call timeout.
BODY_CHUNK_TARGET = 12_000

# WorkspaceClient HTTP timeout. SDK default is 300s — too tight for Opus 4.7
# generating 5-7K output tokens per chunk. Bump to 900s (15 min) so neither
# the title call nor any chunk call hits a client-side timeout. Foundation-model
# serving endpoints respond in seconds-to-low-minutes for normal sizes; the
# generous client timeout only surfaces if generation legitimately needs the headroom.
HTTP_TIMEOUT_SECONDS = 900

# Tavily REST API for term/name/product authoritative-reference lookups.
TAVILY_ENDPOINT = "https://api.tavily.com/search"
TAVILY_TIMEOUT_S = 15
TAVILY_MAX_RESULTS = 5

# Image markdown reference regex — matches ![alt](url) inline image syntax.
# Used by the post-LLM safety check to compare counts in source vs translated body.
_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _load_ssh_secrets() -> dict[str, str]:
    """Read Hermes SSH credentials + Tavily API key from workspace secret scope kb-translate.

    `dbutils` is injected automatically by the Databricks notebook runtime;
    referenced here without import per Databricks convention.
    """
    return {
        "host": dbutils.secrets.get(scope="kb-translate", key="hermes_host"),  # noqa: F821
        "port": dbutils.secrets.get(scope="kb-translate", key="hermes_port"),  # noqa: F821
        "user": dbutils.secrets.get(scope="kb-translate", key="hermes_user"),  # noqa: F821
        "key": dbutils.secrets.get(scope="kb-translate", key="hermes_ssh_key"),  # noqa: F821
        "tavily_api_key": dbutils.secrets.get(scope="kb-translate", key="tavily_api_key"),  # noqa: F821
    }


def _write_key_file(key_pem: str, path: str) -> None:
    """Write the SSH private key to a 0600-mode tmp file (sshd refuses world-readable keys)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(key_pem)
        if not key_pem.endswith("\n"):
            f.write("\n")
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600


def _scp_pull(creds: dict[str, str], remote_path: str, local_path: str) -> None:
    """SCP from Hermes to local tmp. Raises CalledProcessError on failure."""
    subprocess.run(
        [
            "scp",
            "-i", LOCAL_KEY_PATH,
            "-P", creds["port"],
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{creds['user']}@{creds['host']}:{remote_path}",
            local_path,
        ],
        check=True,
        capture_output=True,
    )


def _scp_push(creds: dict[str, str], local_path: str, remote_path: str) -> None:
    """SCP from local tmp to Hermes. Raises CalledProcessError on failure."""
    subprocess.run(
        [
            "scp",
            "-i", LOCAL_KEY_PATH,
            "-P", creds["port"],
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            local_path,
            f"{creds['user']}@{creds['host']}:{remote_path}",
        ],
        check=True,
        capture_output=True,
    )


# Pull the snapshot the operator created in step 1 of the workflow
_creds = _load_ssh_secrets()
_write_key_file(_creds["key"], LOCAL_KEY_PATH)
_scp_pull(_creds, HERMES_SNAPSHOT_PATH, LOCAL_DB_PATH)
print(f"SCP pull OK: {HERMES_SNAPSHOT_PATH} → {LOCAL_DB_PATH} ({os.path.getsize(LOCAL_DB_PATH)} bytes)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 2 — SELECT candidate rows (DATA-07 + idempotency guard)
# MAGIC
# MAGIC `body_translated IS NULL` means re-running "Run all" only translates new rows
# MAGIC (the operator can safely re-run after each Hermes ingest cron).

# COMMAND ----------

@dataclass(frozen=True)
class CandidateRow:
    """One translation candidate. Frozen for immutability per common/coding-style.md."""
    table_name: str  # 'articles' | 'rss_articles'
    row_id: int
    title: str
    body: str
    lang: str | None  # source language code, detected from body via CJK heuristic


_CJK_RE = re.compile(r"[一-鿿]")


def _detect_src_lang(body: str) -> str | None:
    """CJK-ratio heuristic on first 1000 chars. >=30% CJK → 'zh-CN', else None.

    Hermes schema has no source-language column; KOL articles are uniformly zh-CN
    and RSS feeds are mixed (English Substack + Chinese feeds). NULL on detection
    fail-through routes to English-source path in `_resolve_target_lang`.
    """
    sample = body[:1000]
    if not sample:
        return None
    cjk = len(_CJK_RE.findall(sample))
    return "zh-CN" if cjk / max(len(sample), 1) >= 0.30 else None


def _load_candidates(db_path: str, max_rows: int = 0) -> list[CandidateRow]:
    """Load DATA-07-passing rows lacking translation. UNION across both source tables.

    `max_rows > 0` caps the result for smoke testing; `max_rows == 0` means no cap.
    """
    sql = """
        SELECT 'articles' AS table_name, id, title, body
          FROM articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND body_translated IS NULL
        UNION ALL
        SELECT 'rss_articles' AS table_name, id, title, body
          FROM rss_articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND body_translated IS NULL
        ORDER BY table_name, id
    """
    if max_rows > 0:
        sql += f" LIMIT {int(max_rows)}"
    with sqlite3.connect(db_path) as conn:
        return [
            CandidateRow(
                table_name=r[0],
                row_id=r[1],
                title=r[2] or "",
                body=r[3],
                lang=_detect_src_lang(r[3] or ""),
            )
            for r in conn.execute(sql).fetchall()
        ]


# Smoke-test gate: widget `max_rows` ("0" = full backfill; "2" = 2-row smoke test, etc).
# Set via Databricks notebook widget UI before "Run all"; ignored on first import.
try:
    dbutils.widgets.text("max_rows", "0")  # noqa: F821
    _max_rows_str = dbutils.widgets.get("max_rows")  # noqa: F821
    _MAX_ROWS = int(_max_rows_str) if _max_rows_str.strip() else 0
except Exception:  # noqa: BLE001 — running outside a Databricks notebook (e.g. unit test)
    _MAX_ROWS = 0

candidates = _load_candidates(LOCAL_DB_PATH, max_rows=_MAX_ROWS)
print(f"Candidates: {len(candidates)} rows need translation (max_rows={_MAX_ROWS})")
print(
    f"  KOL (articles):   {sum(1 for c in candidates if c.table_name == 'articles')}"
)
print(
    f"  RSS (rss_articles): {sum(1 for c in candidates if c.table_name == 'rss_articles')}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 3 — Translate each row (single JSON call via Opus 4.7 + Tavily context)
# MAGIC
# MAGIC One Tavily search per title for term/name/product authoritative references,
# MAGIC then ONE LLM call (with up to 3 JSON-parse retries) returning strict JSON
# MAGIC `{"title_translated": "...", "body_translated": "..."}`. Tavily HTTP calls
# MAGIC do not count toward the per-row LLM budget.
# MAGIC
# MAGIC Image refs `![alt](url)` are STRUCTURAL DATA — preserved at exact line/paragraph
# MAGIC positions. Post-LLM image-count check is logged but does NOT block UPDATE.
# MAGIC UAT scenario 9 (zh/en pair compare) is the actual quality gate.

# COMMAND ----------

_TRANSLATION_PROMPT = """You are translating a Markdown article from {src_lang} to {tgt_lang}.

Authoritative web search references for the article's title (use as ground truth
for proper nouns, brand names, product names, technical terms — do NOT translate
acronyms or tool/brand names that have no localized form):
{tavily_block}

Hard rules — violations break downstream rendering:
- Image references of the form ![alt](url) MUST appear at the EXACT same line/paragraph
  positions as in the source. Do NOT relocate, consolidate, or reorder images.
- Heading levels (#, ##, ###, ...) preserved exactly. Do NOT promote or demote.
- Code blocks delimited by triple backticks are preserved verbatim — content untranslated.
- List bullets, blockquote markers, and paragraph order are structural — preserve them.
- Translate natural-language text only.

Output STRICT JSON only — no markdown code fence, no preamble, no explanation.
The JSON object must have EXACTLY two string keys: "title_translated" and "body_translated".

Article title:
{title}

Article body:
{body}"""


_TAVILY_FALLBACK = "(no external references retrieved — translate using the article's own context)"


_TITLE_PROMPT = """You are translating an article title from {src_lang} to {tgt_lang}.

Authoritative web search references for the article's title (use as ground truth
for proper nouns, brand names, product names, technical terms — do NOT translate
acronyms or tool/brand names that have no localized form):
{tavily_block}

Output STRICT JSON only — no markdown code fence, no preamble, no explanation.
The JSON object must have EXACTLY one string key: "title_translated".

Title:
{title}"""


_BODY_CHUNK_PROMPT = """You are translating section {idx} of {total} of a Markdown article from {src_lang} to {tgt_lang}.

Authoritative web search references for the article's title (use as ground truth
for proper nouns, brand names, product names, technical terms — do NOT translate
acronyms or tool/brand names that have no localized form):
{tavily_block}

Hard rules — violations break downstream rendering:
- Image references of the form ![alt](url) MUST appear at the EXACT same line/paragraph
  positions as in this section. Do NOT relocate, consolidate, or reorder images.
- Heading levels (#, ##, ###, ...) preserved exactly. Do NOT promote or demote.
- Code blocks delimited by triple backticks are preserved verbatim — content untranslated.
- List bullets, blockquote markers, and paragraph order are structural — preserve them.
- Translate natural-language text only.
- Do NOT add a section header or preamble — output only the translated section content.

Output STRICT JSON only — no markdown code fence, no preamble, no explanation.
The JSON object must have EXACTLY one string key: "body_translated".

Section to translate:
{chunk}"""


def _split_body_into_chunks(body: str, max_chars: int = BODY_CHUNK_TARGET) -> list[str]:
    """Split body on paragraph boundaries into chunks of <= max_chars.

    Greedy pack: walk paragraphs (split by blank lines), append to current chunk
    while size budget allows; flush and start new chunk when next paragraph would
    overflow. Single paragraphs > max_chars fall back to line-split, then hard-cut.
    Preserves paragraph integrity for the common case (most paragraphs are < 2KB).
    """
    if len(body) <= max_chars:
        return [body]
    paragraphs = body.split("\n\n")
    chunks: list[str] = []
    cur = ""
    for p in paragraphs:
        if len(p) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            for line in p.split("\n"):
                if len(line) > max_chars:
                    if cur:
                        chunks.append(cur)
                        cur = ""
                    for i in range(0, len(line), max_chars):
                        chunks.append(line[i : i + max_chars])
                elif len(cur) + len(line) + 1 > max_chars:
                    chunks.append(cur)
                    cur = line
                else:
                    cur = cur + "\n" + line if cur else line
            if cur:
                chunks.append(cur)
                cur = ""
        elif len(cur) + len(p) + 2 > max_chars:
            chunks.append(cur)
            cur = p
        else:
            cur = cur + "\n\n" + p if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def _tavily_search(api_key: str, query: str) -> str:
    """Single Tavily REST call. Returns a compact JSON string of {title, url, content} entries.

    On any error (network, rate limit, malformed response), returns the fallback marker
    so translation can proceed without external references. Tavily failures must NOT
    block the per-row translation budget.
    """
    if not query:
        return _TAVILY_FALLBACK
    try:
        resp = requests.post(
            TAVILY_ENDPOINT,
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": TAVILY_MAX_RESULTS,
                "include_answer": False,
            },
            timeout=TAVILY_TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", []) or []
        if not results:
            return _TAVILY_FALLBACK
        compact = [
            {
                "title": (r.get("title") or "")[:200],
                "url": r.get("url", ""),
                "content": (r.get("content") or "")[:400],
            }
            for r in results[:TAVILY_MAX_RESULTS]
        ]
        return json.dumps(compact, ensure_ascii=False)
    except Exception:  # noqa: BLE001 — Tavily failure is non-fatal
        return _TAVILY_FALLBACK


# Single client constructed once per notebook run; closure captured by helpers below.
# http_timeout_seconds bumped from SDK default 300s to HTTP_TIMEOUT_SECONDS
# (smoke #3 + #4 both hit `TimeoutError('Timed out after 0:05:00')` on the 154KB
# body — that's the SDK's default client-side ceiling, not a serving SLA error).
_w = WorkspaceClient(config=Config(http_timeout_seconds=HTTP_TIMEOUT_SECONDS))


def _resolve_target_lang(src_lang: str | None) -> tuple[str, str, str]:
    """Return (src_label, tgt_label, target_code) for the prompt.

    zh-CN ↔ en is the only mapping. Anything not zh-CN (NULL, 'en', or unrecognized)
    is treated as English source and translated to Chinese.
    """
    if src_lang == "zh-CN":
        return ("Chinese", "English", "en")
    return ("English", "Chinese", "zh-CN")


def _query_opus(prompt: str) -> str:
    """One serving-endpoint round-trip. Returns the raw text content.

    `max_tokens=32000` accommodates large bodies (KOL articles up to ~150KB → ~30-40K
    output tokens at 1:1 zh↔en ratio). Default of 4096 truncates mid-body and triggers
    JSON parse failure → all 4 retries waste budget on the same truncation.
    """
    resp = _w.serving_endpoints.query(
        name=TRANSLATION_MODEL,
        messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
        max_tokens=32000,
    )
    return resp.choices[0].message.content


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return s


def _parse_translation_json(raw: str) -> dict[str, str] | None:
    """Strict parse — accepts only a JSON object with both required string keys.

    Tolerates a leading/trailing ```json fence in case the model adds one despite
    the instruction. Returns None on any structural problem so the caller can retry.
    """
    try:
        obj = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    t = obj.get("title_translated")
    b = obj.get("body_translated")
    if not isinstance(t, str) or not isinstance(b, str):
        return None
    return {"title_translated": t, "body_translated": b}


def _parse_single_key_json(raw: str, key: str) -> str | None:
    """Strict parse for single-key prompts (title-only or body-only chunked translations)."""
    try:
        obj = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    v = obj.get(key)
    return v if isinstance(v, str) else None


def _translate_with_retry(prompt: str, parser, *, attempts: int = MAX_LLM_CALLS_PER_ROW):
    """Call Opus + parser with up to `attempts` retries on JSON parse failure.

    Returns (parsed_value, n_calls_used). Raises RuntimeError on budget exhaustion.
    """
    last_head = ""
    for attempt in range(1, attempts + 1):
        raw = _query_opus(prompt)
        parsed = parser(raw)
        if parsed is not None:
            return parsed, attempt
        last_head = raw[:200]
    raise RuntimeError(
        f"JSON parse failed after {attempts} attempts; last raw head: {last_head!r}"
    )


def _translate_row(row: CandidateRow, tavily_api_key: str) -> tuple[str, str, str, int]:
    """Translate one row. Returns (translated_title, translated_body, target_code, llm_calls).

    Bodies <= BODY_CHUNK_THRESHOLD use a single-shot prompt returning both keys.
    Bodies > BODY_CHUNK_THRESHOLD chunk on paragraph boundaries: title is translated
    once, then each chunk is translated separately and concatenated with "\n\n".
    Chunked mode multiplies LLM calls per row (1 title + N chunks, each with up to
    MAX_LLM_CALLS_PER_ROW retries) — necessary because the Databricks serving
    endpoint has a hard 5-min request SLA that 100KB+ bodies routinely exceed.

    Raises RuntimeError on budget exhaustion (caller catches per-row).
    """
    src_label, tgt_label, target_code = _resolve_target_lang(row.lang)
    tavily_block = _tavily_search(tavily_api_key, row.title or row.body[:200])

    if len(row.body) <= BODY_CHUNK_THRESHOLD:
        prompt = _TRANSLATION_PROMPT.format(
            src_lang=src_label,
            tgt_lang=tgt_label,
            tavily_block=tavily_block,
            title=row.title,
            body=row.body,
        )
        parsed, n_calls = _translate_with_retry(prompt, _parse_translation_json)
        return (
            parsed["title_translated"].strip(),
            parsed["body_translated"].strip(),
            target_code,
            n_calls,
        )

    # Chunked path — body > threshold
    chunks = _split_body_into_chunks(row.body, max_chars=BODY_CHUNK_TARGET)
    print(
        f"  CHUNKED row={row.table_name}/{row.row_id} body_len={len(row.body):,} "
        f"chunks={len(chunks)} (sizes: {[len(c) for c in chunks]})"
    )

    title_prompt = _TITLE_PROMPT.format(
        src_lang=src_label,
        tgt_lang=tgt_label,
        tavily_block=tavily_block,
        title=row.title,
    )
    t_title, calls_title = _translate_with_retry(
        title_prompt, lambda r: _parse_single_key_json(r, "title_translated")
    )

    translated_chunks: list[str] = []
    total_chunk_calls = 0
    for idx, chunk in enumerate(chunks, start=1):
        chunk_prompt = _BODY_CHUNK_PROMPT.format(
            idx=idx,
            total=len(chunks),
            src_lang=src_label,
            tgt_lang=tgt_label,
            tavily_block=tavily_block,
            chunk=chunk,
        )
        translated, n = _translate_with_retry(
            chunk_prompt, lambda r: _parse_single_key_json(r, "body_translated")
        )
        translated_chunks.append(translated.strip())
        total_chunk_calls += n

    return (
        t_title.strip(),
        "\n\n".join(translated_chunks),
        target_code,
        calls_title + total_chunk_calls,
    )


def _check_image_count(orig_body: str, translated_body: str) -> tuple[int, int]:
    """Count image refs in source vs translation. Mismatch is logged but does NOT block."""
    return (
        len(_IMG_REF_RE.findall(orig_body)),
        len(_IMG_REF_RE.findall(translated_body)),
    )


# Run the translation loop and accumulate results in memory; cell 4 commits them.
translated_rows: list[
    tuple[str, int, str, str, str, str]
] = []  # (table_name, id, t_title, t_body, t_lang, t_at_iso)
image_mismatches: list[tuple[str, int, int, int]] = []  # (table, id, orig_n, trans_n)
errors: list[tuple[str, int, str]] = []  # (table, id, repr(e))
total_llm_calls = 0

_tavily_api_key = _creds["tavily_api_key"]

for i, row in enumerate(candidates, start=1):
    try:
        t_title, t_body, t_lang, n_calls = _translate_row(row, _tavily_api_key)
        total_llm_calls += n_calls
        orig_n, trans_n = _check_image_count(row.body, t_body)
        if orig_n != trans_n:
            image_mismatches.append((row.table_name, row.row_id, orig_n, trans_n))
            print(
                f"  WARN image-count mismatch row={row.table_name}/{row.row_id} "
                f"orig={orig_n} translated={trans_n} (logged, NOT blocking)"
            )
        t_at = datetime.now(timezone.utc).isoformat()
        translated_rows.append(
            (row.table_name, row.row_id, t_title, t_body, t_lang, t_at)
        )
        if i % 10 == 0:
            print(
                f"  progress: {i}/{len(candidates)} translated "
                f"(LLM calls so far: {total_llm_calls})"
            )
    except Exception as e:  # noqa: BLE001 — per-row isolation; one row failure must not abort the batch
        errors.append((row.table_name, row.row_id, repr(e)[:200]))
        print(f"  ERROR row={row.table_name}/{row.row_id}: {repr(e)[:200]}")

print(
    f"Translation done: {len(translated_rows)} ok / "
    f"{len(image_mismatches)} image-count mismatches / "
    f"{len(errors)} errors / {total_llm_calls} total LLM calls"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 4 — UPDATE the four translation columns (parameterized binding)
# MAGIC
# MAGIC One UPDATE per row, parameterized — no string concatenation. Wrapped in a
# MAGIC single transaction so a mid-batch crash leaves either the full batch
# MAGIC committed or none of it committed.

# COMMAND ----------

def _commit_translations(
    db_path: str,
    rows: list[tuple[str, int, str, str, str, str]],
) -> int:
    """UPDATE 4 cols per row across articles + rss_articles. Returns rows updated."""
    n_updated = 0
    with sqlite3.connect(db_path) as conn:
        for table_name, row_id, t_title, t_body, t_lang, t_at in rows:
            # Parameterized; table_name is whitelisted by upstream SELECT (no injection surface)
            if table_name not in {"articles", "rss_articles"}:
                raise ValueError(f"unexpected table_name: {table_name!r}")
            conn.execute(
                f"UPDATE {table_name} SET title_translated = ?, "  # noqa: S608 — table whitelisted above
                "body_translated = ?, translated_lang = ?, translated_at = ? "
                "WHERE id = ?",
                (t_title, t_body, t_lang, t_at, row_id),
            )
            n_updated += 1
        conn.commit()
    return n_updated


n_committed = _commit_translations(LOCAL_DB_PATH, translated_rows)
print(f"UPDATE committed: {n_committed} rows in {LOCAL_DB_PATH}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 5 — Generate SQL apply file (UPDATE statements only)
# MAGIC
# MAGIC Writes `/tmp/kol_scan_apply.sql` with one UPDATE per translated row, wrapped in
# MAGIC `BEGIN; ... COMMIT;` for atomic application on Hermes. Each UPDATE has an
# MAGIC `AND title_translated IS NULL` idempotency guard — if a concurrent operator
# MAGIC has already filled translation columns for the same row, the UPDATE no-ops
# MAGIC instead of overwriting.
# MAGIC
# MAGIC We push UPDATE statements (not the whole DB) so applying on Hermes ONLY merges
# MAGIC translation columns and does NOT clobber ingest-cron rows that arrived after
# MAGIC the SCP-pull snapshot.

# COMMAND ----------

def _sql_quote(s: str) -> str:
    """SQLite SQL string literal — single-quote and escape internal single-quotes."""
    return "'" + s.replace("'", "''") + "'"


def _emit_apply_sql(
    rows: list[tuple[str, int, str, str, str, str]],
    out_path: str,
) -> int:
    """Write one UPDATE per row inside a single transaction. Returns row count."""
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("-- kb-v2.2-7 KB bilingual translation backfill\n")
        f.write(f"-- Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"-- Row count: {len(rows)}\n")
        f.write("BEGIN;\n")
        for table_name, row_id, t_title, t_body, t_lang, t_at in rows:
            if table_name not in {"articles", "rss_articles"}:
                raise ValueError(f"unexpected table_name: {table_name!r}")
            stmt = (
                f"UPDATE {table_name} SET "
                f"title_translated = {_sql_quote(t_title)}, "
                f"body_translated = {_sql_quote(t_body)}, "
                f"translated_lang = {_sql_quote(t_lang)}, "
                f"translated_at = {_sql_quote(t_at)} "
                f"WHERE id = {row_id} AND title_translated IS NULL;\n"
            )
            f.write(stmt)
            n += 1
        f.write("COMMIT;\n")
    return n


n_emitted = _emit_apply_sql(translated_rows, LOCAL_APPLY_SQL_PATH)
print(
    f"Apply SQL emitted: {n_emitted} UPDATE statements in "
    f"{LOCAL_APPLY_SQL_PATH} ({os.path.getsize(LOCAL_APPLY_SQL_PATH)} bytes)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 6 — SCP push apply.sql to Hermes (operator-gated SSH apply)
# MAGIC
# MAGIC Always pushes the SQL apply file to Hermes staging. The actual
# MAGIC `sqlite3 < apply.sql` execution on Hermes is operator-gated — uncomment the
# MAGIC `_ssh_apply_on_hermes(...)` call below ONLY during a quiet window
# MAGIC (avoid 09:00 / 14:00 / 21:00 ADT cron). Default behavior leaves Cell 6 as a
# MAGIC pure SCP push so the operator can verify apply.sql on Hermes before running it.

# COMMAND ----------

def _ssh_apply_on_hermes(
    creds: dict[str, str],
    remote_db_path: str,
    remote_sql_path: str,
) -> str:
    """Operator-gated. Backs up live DB, applies SQL transactionally, returns reconciled counts."""
    backup_cmd = (
        f"cp {remote_db_path} {remote_db_path}.bak-pre-translate-"
        f"$(date -u +%Y%m%dT%H%M%SZ)"
    )
    apply_cmd = f"sqlite3 {remote_db_path} < {remote_sql_path}"
    verify_cmd = (
        f"sqlite3 {remote_db_path} \"SELECT "
        f"(SELECT COUNT(*) FROM articles WHERE title_translated IS NOT NULL) AS articles_translated, "
        f"(SELECT COUNT(*) FROM rss_articles WHERE title_translated IS NOT NULL) AS rss_translated;\""
    )
    full_cmd = f"{backup_cmd} && {apply_cmd} && {verify_cmd}"
    result = subprocess.run(
        [
            "ssh",
            "-i", LOCAL_KEY_PATH,
            "-p", creds["port"],
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            f"{creds['user']}@{creds['host']}",
            full_cmd,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


# Always push the apply.sql file to Hermes staging.
_scp_push(_creds, LOCAL_APPLY_SQL_PATH, HERMES_APPLY_SQL_PATH)
print(
    f"SCP push OK: {LOCAL_APPLY_SQL_PATH} → {HERMES_APPLY_SQL_PATH} "
    f"({os.path.getsize(LOCAL_APPLY_SQL_PATH)} bytes)"
)

# OPERATOR GATE — uncomment ONLY during a quiet window (avoid the cron firings):
# apply_stdout = _ssh_apply_on_hermes(_creds, HERMES_LIVE_DB_PATH, HERMES_APPLY_SQL_PATH)
# print(f"Hermes apply result:\n{apply_stdout}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 7 — Run summary
# MAGIC
# MAGIC Counts, image-count mismatches needing manual spot-check, and the operator
# MAGIC instructions for the post-step (apply on Hermes during a quiet window).

# COMMAND ----------

print("=" * 60)
print("kb-v2.2-7 KB bilingual translation run summary")
print("=" * 60)
print(f"  candidates loaded:        {len(candidates)}")
print(f"  rows translated + UPDATE: {n_committed}")
print(f"  apply.sql statements:     {n_emitted}")
print(f"  total LLM calls:          {total_llm_calls}")
print(f"  per-row errors:           {len(errors)}")
print(f"  image-count mismatches:   {len(image_mismatches)}")
if image_mismatches:
    print()
    print("Image-count mismatches (manual spot-check via UAT scenario 9):")
    for table, row_id, orig_n, trans_n in image_mismatches:
        print(f"  {table:14s} id={row_id:6d}  orig={orig_n:3d}  trans={trans_n:3d}")
if errors:
    print()
    print("Per-row errors (transient — re-run notebook to retry NULL rows):")
    for table, row_id, err in errors:
        print(f"  {table:14s} id={row_id:6d}  {err}")
print()
print("Next step (operator, on Hermes — during quiet window):")
print(f"  cp {HERMES_LIVE_DB_PATH} {HERMES_LIVE_DB_PATH}.bak-pre-translate-$(date -u +%Y%m%dT%H%M%SZ)")
print(f"  sqlite3 {HERMES_LIVE_DB_PATH} < {HERMES_APPLY_SQL_PATH}")
print(f"  sqlite3 {HERMES_LIVE_DB_PATH} \"SELECT")
print(f"    (SELECT COUNT(*) FROM articles WHERE title_translated IS NOT NULL),")
print(f"    (SELECT COUNT(*) FROM rss_articles WHERE title_translated IS NOT NULL);\"")
print()
print("(Or un-comment the _ssh_apply_on_hermes(...) call in Cell 6 to automate.)")

# Surface diagnostic stats via dbutils.notebook.exit so `databricks jobs get-run-output`
# returns a structured JSON for non-UI inspection (e.g. CLI smoke review).
try:
    _stats = {
        "candidates_loaded": len(candidates),
        "rows_translated": n_committed,
        "apply_sql_statements": n_emitted,
        "total_llm_calls": total_llm_calls,
        "errors": [
            {"table": t, "id": rid, "err": e} for (t, rid, e) in errors
        ],
        "image_mismatches": [
            {"table": t, "id": rid, "orig": o, "translated": tr}
            for (t, rid, o, tr) in image_mismatches
        ],
        "translated_row_ids": [
            {"table": t, "id": rid, "lang": lg}
            for (t, rid, _tt, _tb, lg, _ta) in translated_rows
        ],
    }
    dbutils.notebook.exit(json.dumps(_stats))  # noqa: F821
except NameError:
    pass  # running outside notebook (unit test)
