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
# MAGIC    sqlite3 ~/.hermes/omonigraph-vault/kol_scan.db ".backup /tmp/kol_scan.db.snap"
# MAGIC    ```
# MAGIC    Out-of-process snapshot avoids SQLite write-lock contention with the live ingest cron.
# MAGIC
# MAGIC 2. **In Databricks:** open this notebook, click **Run all**.
# MAGIC    Cells 1→6 execute sequentially: SCP pull → SELECT → translate → UPDATE → SCP push → summary.
# MAGIC
# MAGIC 3. **On Hermes (post-step, after verification):** promote the translated DB
# MAGIC    over the live DB during a quiet window (between ingest crons):
# MAGIC    ```
# MAGIC    cp /tmp/kol_scan.db.translated ~/.hermes/omonigraph-vault/kol_scan.db
# MAGIC    ```
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

import os
import re
import stat
import subprocess
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

# Local paths inside the Databricks driver node
LOCAL_DB_PATH = "/tmp/kol_scan.db"
LOCAL_KEY_PATH = "/tmp/hermes_key"

# Hermes-side staging paths (operator pre-step writes the snapshot to .snap;
# this notebook pushes the translated DB to .translated for manual promotion)
HERMES_SNAPSHOT_PATH = "/tmp/kol_scan.db.snap"
HERMES_TRANSLATED_PATH = "/tmp/kol_scan.db.translated"

# Translation model (Databricks Foundation Model serving endpoint)
TRANSLATION_MODEL = "databricks-claude-haiku-4-5"

# Image markdown reference regex — matches ![alt](url) inline image syntax.
# Used by the post-LLM safety check to compare counts in source vs translated body.
_IMG_REF_RE = re.compile(r"!\[[^\]]*\]\([^)]+\)")


def _load_ssh_secrets() -> dict[str, str]:
    """Read the four Hermes SSH credentials from workspace secret scope kb-translate.

    `dbutils` is injected automatically by the Databricks notebook runtime;
    referenced here without import per Databricks convention.
    """
    return {
        "host": dbutils.secrets.get(scope="kb-translate", key="hermes_host"),  # noqa: F821
        "port": dbutils.secrets.get(scope="kb-translate", key="hermes_port"),  # noqa: F821
        "user": dbutils.secrets.get(scope="kb-translate", key="hermes_user"),  # noqa: F821
        "key": dbutils.secrets.get(scope="kb-translate", key="hermes_ssh_key"),  # noqa: F821
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
    lang: str | None  # source language code from DB; 'zh-CN' / 'en' / NULL


def _load_candidates(db_path: str) -> list[CandidateRow]:
    """Load DATA-07-passing rows lacking translation. UNION across both source tables."""
    sql = """
        SELECT 'articles' AS table_name, id, title, body, lang
          FROM articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND body_translated IS NULL
        UNION ALL
        SELECT 'rss_articles' AS table_name, id, title, body, lang
          FROM rss_articles
         WHERE layer1_verdict = 'candidate'
           AND layer2_verdict = 'ok'
           AND body IS NOT NULL AND body != ''
           AND body_translated IS NULL
        ORDER BY table_name, id
    """
    with sqlite3.connect(db_path) as conn:
        return [
            CandidateRow(table_name=r[0], row_id=r[1], title=r[2] or "", body=r[3], lang=r[4])
            for r in conn.execute(sql).fetchall()
        ]


candidates = _load_candidates(LOCAL_DB_PATH)
print(f"Candidates: {len(candidates)} rows need translation")
print(
    f"  KOL (articles):   {sum(1 for c in candidates if c.table_name == 'articles')}"
)
print(
    f"  RSS (rss_articles): {sum(1 for c in candidates if c.table_name == 'rss_articles')}"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 3 — Translate each row (title + body via haiku-4-5)
# MAGIC
# MAGIC Two LLM calls per row. The body prompt has explicit image-position-invariance
# MAGIC clauses — image refs `![alt](url)` are STRUCTURAL DATA, not stylistic. The
# MAGIC scraper preserves their inline positions; the translator MUST do the same.
# MAGIC
# MAGIC Post-LLM safety check compares image counts (orig vs translated). Mismatches
# MAGIC are logged (warn-only); the UPDATE in cell 4 still proceeds. UAT scenario 9
# MAGIC (zh/en pair compare) is the actual gate per PLAN R7 mitigation.

# COMMAND ----------

# Module-level prompt templates per python-patterns module-level constant pattern.
# Two-clause structure: instruction header then explicit constraints. Constraints
# named explicitly so they survive prompt rephrasing in any future revision.

_TITLE_PROMPT = """Translate the following article title from {src_lang} to {tgt_lang}.

Constraints:
- Return ONLY the translated title — no preamble, no explanation, no quotes around it.
- Preserve any acronyms, product names, or proper nouns verbatim (do NOT translate brand/tool names).
- Do not add commentary about translation choices.

Title to translate:
{title}"""


_BODY_PROMPT = """Translate the following Markdown article body from {src_lang} to {tgt_lang}.

Image positioning is STRUCTURAL DATA, not stylistic. The source markdown has been
authored so that each image reference appears immediately adjacent to the paragraph
it illustrates. Your translation MUST preserve that adjacency exactly.

Hard constraints (violations break downstream rendering):
- Image references of the form ![alt](url) MUST appear at the EXACT same line/paragraph
  positions as in the source markdown. Do NOT relocate images to section ends.
- Do NOT consolidate consecutive images. Two images on adjacent lines in the source
  must remain on adjacent lines in the translation.
- Do NOT reorder paragraphs. The Nth paragraph of the source corresponds to the Nth
  paragraph of the translation.
- Code blocks delimited by ``` are preserved verbatim — content untranslated.
- Heading levels (#, ##, ###, ...) preserved exactly — do NOT promote or demote.
- Translate natural-language text only. Image positioning, code blocks, headings,
  list bullets, and blockquote markers are structural — leave them where they are.
- Return ONLY the translated markdown — no preamble, no explanation, no metadata.

Body to translate:
{body}"""


# Single client constructed once per notebook run; closure captured by the helper below.
_w = WorkspaceClient()


def _resolve_target_lang(src_lang: str | None) -> tuple[str, str]:
    """Return (src_label, tgt_label) for the prompt. zh-CN ↔ en is the only mapping.

    Anything that is not zh-CN (including NULL, 'en', or unrecognized codes) is
    treated as English source and translated to Chinese.
    """
    if src_lang == "zh-CN":
        return ("Chinese", "English")
    return ("English", "Chinese")


def _query_haiku(prompt: str) -> str:
    """One serving-endpoint round-trip. Returns the raw text content."""
    resp = _w.serving_endpoints.query(
        name=TRANSLATION_MODEL,
        messages=[ChatMessage(role=ChatMessageRole.USER, content=prompt)],
    )
    return resp.choices[0].message.content


def _translate_row(row: CandidateRow) -> tuple[str, str, str]:
    """Two LLM calls per row. Returns (translated_title, translated_body, target_lang_code)."""
    src_label, tgt_label = _resolve_target_lang(row.lang)
    target_code = "en" if row.lang == "zh-CN" else "zh-CN"

    translated_title = _query_haiku(
        _TITLE_PROMPT.format(src_lang=src_label, tgt_lang=tgt_label, title=row.title)
    ).strip()
    translated_body = _query_haiku(
        _BODY_PROMPT.format(src_lang=src_label, tgt_lang=tgt_label, body=row.body)
    ).strip()
    return translated_title, translated_body, target_code


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

for i, row in enumerate(candidates, start=1):
    try:
        t_title, t_body, t_lang = _translate_row(row)
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
            print(f"  progress: {i}/{len(candidates)} translated")
    except Exception as e:  # noqa: BLE001 — per-row isolation; one row failure must not abort the batch
        errors.append((row.table_name, row.row_id, repr(e)[:200]))
        print(f"  ERROR row={row.table_name}/{row.row_id}: {repr(e)[:200]}")

print(
    f"Translation done: {len(translated_rows)} ok / "
    f"{len(image_mismatches)} image-count mismatches / "
    f"{len(errors)} errors"
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
# MAGIC ## Cell 5 — SCP push translated DB back to Hermes staging path
# MAGIC
# MAGIC Pushes to `/tmp/kol_scan.db.translated` on Hermes. The operator manually
# MAGIC promotes this over the live DB during a quiet window between ingest crons
# MAGIC (workflow step 3 documented in cell 0).

# COMMAND ----------

_scp_push(_creds, LOCAL_DB_PATH, HERMES_TRANSLATED_PATH)
print(
    f"SCP push OK: {LOCAL_DB_PATH} → {HERMES_TRANSLATED_PATH} "
    f"({os.path.getsize(LOCAL_DB_PATH)} bytes)"
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cell 6 — Run summary
# MAGIC
# MAGIC Counts and any image-count mismatches that need manual spot-check.

# COMMAND ----------

print("=" * 60)
print("kb-v2.2-7 translation run summary")
print("=" * 60)
print(f"  candidates loaded:        {len(candidates)}")
print(f"  rows translated + UPDATE: {n_committed}")
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
print("Next step (operator, on Hermes):")
print(f"  cp {HERMES_TRANSLATED_PATH} ~/.hermes/omonigraph-vault/kol_scan.db")
