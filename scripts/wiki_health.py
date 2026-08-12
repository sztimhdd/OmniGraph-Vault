#!/usr/bin/env python3
"""Wiki health checker — read-only audit of kb/wiki/ against SCHEMA.md.

Checks:
  1. page-count/index consistency
  2. required frontmatter fields per SCHEMA.md
  3. YAML parse validity
  4. citation/source integrity (legacy + GFM footnote)
  5. wikilink target validity
  6. orphan/unindexed pages
  7. duplicate slugs
  8. staleness signal (last_updated age)
  9. index.md freshness vs constituent files

Exit codes: 0=OK, 1=ERROR(s) found, 2=WARN(s) only

Usage:
    python scripts/wiki_health.py [--json] [--wiki-root kb/wiki] [--db-path data/kol_scan.db]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import frontmatter

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_LEGACY_CITATION_RE = re.compile(r"\^\[article:([a-f0-9]{10})\]")
_FOOTNOTE_CITATION_RE = re.compile(r"\[\^(\d+)\]")
_BACKLINK_RE = re.compile(r"\[\[([a-z0-9-]+)\]\]")

# SCHEMA required fields
_REQUIRED_FM = {"title", "created", "last_updated", "sources", "confidence_level"}


def _findings() -> dict:
    return {"errors": [], "warns": []}


def check_yaml_validity(page_path: Path, findings: dict) -> None:
    try:
        frontmatter.load(str(page_path))
    except Exception as e:
        findings["errors"].append(f"{page_path.name}: YAML parse failed: {e}")


def check_frontmatter_fields(page_path: Path, findings: dict) -> None:
    try:
        post = frontmatter.load(str(page_path))
    except Exception:
        return  # YAML parse already reported
    missing = _REQUIRED_FM - set(post.metadata.keys())
    if missing:
        findings["errors"].append(
            f"{page_path.name}: missing frontmatter fields: {sorted(missing)}"
        )


def check_citations(page_path: Path, known_hashes: set[str], findings: dict) -> None:
    try:
        post = frontmatter.load(str(page_path))
    except Exception:
        return
    text = post.content
    # Legacy citations: every hash must be in known_hashes
    for m in _LEGACY_CITATION_RE.finditer(text):
        if m.group(1) not in known_hashes:
            findings["errors"].append(
                f"{page_path.name}: unresolved legacy citation ^[article:{m.group(1)}]"
            )
    # GFM footnotes: validate against frontmatter sources
    sources = post.metadata.get("sources") or []
    source_by_id = {}
    for s in sources:
        if isinstance(s, dict) and "id" in s:
            source_by_id[str(s["id"])] = s
    for m in _FOOTNOTE_CITATION_RE.finditer(text):
        sid = m.group(1)
        src = source_by_id.get(sid)
        if src is None:
            findings["errors"].append(
                f"{page_path.name}: [^{sid}] — id not in frontmatter sources[]"
            )
            continue
        if (src.get("type") or "").lower() == "article":
            ref = str(src.get("ref") or "")
            if ref and known_hashes and ref not in known_hashes:
                findings["warns"].append(
                    f"{page_path.name}: [^{sid}] — article ref {ref!r} not in DB corpus"
                )


def check_wikilinks(page_path: Path, wiki_root: Path, findings: dict) -> None:
    try:
        text = page_path.read_text(encoding="utf-8")
    except Exception:
        return
    for m in _BACKLINK_RE.finditer(text):
        slug = m.group(1)
        # Check entities/ first, then other subdirs
        found = False
        for subdir in ("entities", "concepts", "comparisons", "queries"):
            if (wiki_root / subdir / f"{slug}.md").exists():
                found = True
                break
        if not found:
            findings["warns"].append(
                f"{page_path.name}: broken wikilink [[{slug}]] — target not found"
            )


def check_staleness(page_path: Path, max_days: int, today: date, findings: dict) -> None:
    try:
        post = frontmatter.load(str(page_path))
    except Exception:
        return
    raw = post.metadata.get("last_updated")
    if raw is None:
        findings["errors"].append(f"{page_path.name}: missing last_updated")
        return
    if isinstance(raw, date):
        last = raw
    elif isinstance(raw, datetime):
        last = raw.date()
    else:
        try:
            last = datetime.strptime(str(raw), "%Y-%m-%d").date()
        except ValueError:
            findings["errors"].append(
                f"{page_path.name}: unparseable last_updated: {raw!r}"
            )
            return
    age = (today - last).days
    if age > max_days:
        findings["warns"].append(
            f"{page_path.name}: stale — last_updated={last.isoformat()}, age={age}d"
        )


def check_index_consistency(wiki_root: Path, findings: dict) -> None:
    index_path = wiki_root / "index.md"
    if not index_path.exists():
        findings["warns"].append("index.md missing")
        return
    # Collect all wiki pages
    pages: set[str] = set()
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            pages.add(f"{subdir}/{f.name}")
    # Parse index.md references
    index_content = index_path.read_text(encoding="utf-8")
    indexed = set(re.findall(r"\]\(([^)]+\.md)\)", index_content))
    in_index_not_disk = indexed - pages
    on_disk_not_index = pages - indexed
    for p in sorted(in_index_not_disk):
        findings["errors"].append(f"index.md references missing file: {p}")
    for p in sorted(on_disk_not_index):
        pobj = wiki_root / p
        if "_suggestions" in str(pobj) or pobj.parent.name.startswith("_"):
            continue
        findings["warns"].append(f"{p}: on disk but not in index.md")


def check_index_freshness(wiki_root: Path, findings: dict) -> None:
    index_path = wiki_root / "index.md"
    if not index_path.exists():
        return
    index_mtime = index_path.stat().st_mtime
    stale_pages = []
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            if f.stat().st_mtime > index_mtime:
                stale_pages.append(str(f.relative_to(wiki_root)))
    if stale_pages:
        findings["warns"].append(
            f"index.md older than {len(stale_pages)} page(s): "
            f"{', '.join(stale_pages[:5])}"
            f"{'...' if len(stale_pages) > 5 else ''}"
        )


def check_duplicate_slugs(wiki_root: Path, findings: dict) -> None:
    seen: dict[str, list[str]] = {}
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        for f in d.glob("*.md"):
            slug = f.stem
            seen.setdefault(slug, []).append(str(f.relative_to(wiki_root)))
    for slug, paths in seen.items():
        if len(paths) > 1:
            findings["errors"].append(f"duplicate slug '{slug}': {', '.join(paths)}")


def load_known_hashes(db_path: Path | None) -> set[str]:
    """Known-article citation corpus (name kept for compatibility).

    Uses the shared source-aware resolver
    (``kb.wiki_articles.known_wiki_article_refs``) so canonical RSS URL refs
    are recognized while legacy valid 10-char WeChat refs remain. RSS
    32-char body MD5 values are never admitted (W5B Task 1).
    """
    if db_path is None or not db_path.exists():
        return set()
    import sqlite3

    from kb.wiki_articles import known_wiki_article_refs

    try:
        with sqlite3.connect(str(db_path)) as conn:
            return known_wiki_article_refs(conn)
    except sqlite3.Error:
        return set()


def run_health(
    wiki_root: Path,
    db_path: Path | None = None,
    max_stale_days: int = 180,
    today: date | None = None,
) -> dict[str, Any]:
    """Run all health checks. Returns dict with errors, warns, and summary."""
    findings = _findings()
    today = today or date.today()
    known_hashes = load_known_hashes(db_path)

    # Collect all wiki pages
    pages: list[Path] = []
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        pages.extend(sorted(d.glob("*.md")))

    if not pages:
        findings["warns"].append("no wiki pages found")
        return findings

    for page in pages:
        check_yaml_validity(page, findings)
        if findings["errors"] and findings["errors"][-1].startswith(page.name):
            continue  # skip remaining checks if YAML broken
        check_frontmatter_fields(page, findings)
        check_citations(page, known_hashes, findings)
        check_wikilinks(page, wiki_root, findings)
        check_staleness(page, max_stale_days, today, findings)

    check_index_consistency(wiki_root, findings)
    check_index_freshness(wiki_root, findings)
    check_duplicate_slugs(wiki_root, findings)

    findings["summary"] = {
        "pages_checked": len(pages),
        "errors": len(findings["errors"]),
        "warns": len(findings["warns"]),
        "db_hashes_loaded": len(known_hashes),
        "wiki_root": str(wiki_root),
        "today": today.isoformat(),
    }
    return findings


def _rebuild_index(wiki_root: Path) -> None:
    """Regenerate index.md from current page set. Skips _suggestions/."""
    index_path = wiki_root / "index.md"
    sections: list[str] = [
        "# Wiki Index", "",
        "Auto-generated. Re-run `scripts/wiki_health.py --rebuild-index` to refresh.",
        "",
    ]
    for subdir in ("entities", "concepts", "comparisons", "queries"):
        d = wiki_root / subdir
        if not d.exists():
            continue
        files = sorted(d.glob("*.md"))
        if not files:
            continue
        sections.append(f"## {subdir.title()}")
        sections.append("")
        for f in files:
            try:
                post = frontmatter.load(f)
                title = post.get("title") or f.stem
            except Exception:
                title = f.stem
            sections.append(f"- [{title}]({subdir}/{f.name})")
        sections.append("")
    index_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Wiki health checker")
    p.add_argument("--json", action="store_true", help="Machine-readable output")
    p.add_argument("--wiki-root", default="kb/wiki", help="Wiki root dir")
    p.add_argument("--db-path", default=None, help="SQLite DB for citation validation")
    p.add_argument("--max-stale-days", type=int, default=180, help="Staleness threshold")
    p.add_argument("--rebuild-index", action="store_true",
                   help="Regenerate index.md from current page set")
    args = p.parse_args(argv)

    wiki_root = Path(args.wiki_root)
    db_path = Path(args.db_path) if args.db_path else None

    if args.rebuild_index:
        _rebuild_index(wiki_root)
        print(f"Rebuilt {wiki_root / 'index.md'}")

    findings = run_health(wiki_root, db_path, args.max_stale_days)

    if args.json:
        print(json.dumps(findings, indent=2, default=str))
    else:
        print(f"Wiki Health Report — {findings['summary']['today']}")
        print(f"  Root: {findings['summary']['wiki_root']}")
        print(f"  Pages: {findings['summary']['pages_checked']}")
        print(f"  DB hashes: {findings['summary']['db_hashes_loaded']}")
        print()
        if findings["errors"]:
            print(f"ERRORS ({len(findings['errors'])}):")
            for e in findings["errors"]:
                print(f"  ❌ {e}")
        if findings["warns"]:
            print(f"WARNINGS ({len(findings['warns'])}):")
            for w in findings["warns"]:
                print(f"  ⚠️  {w}")
        if not findings["errors"] and not findings["warns"]:
            print("✅ All checks passed.")
        print()
        print(f"Exit: {'ERROR' if findings['errors'] else 'WARN' if findings['warns'] else 'OK'}")

    if findings["errors"]:
        return 1
    if findings["warns"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
