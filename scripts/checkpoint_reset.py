#!/usr/bin/env python3
"""Delete checkpoint state for one article (by hash) or all articles.

Usage:
    python scripts/checkpoint_reset.py --hash {article_hash}
    python scripts/checkpoint_reset.py --all --confirm

--all WITHOUT --confirm is refused (exit 2) per CLAUDE.md guard-clause principle.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.checkpoint import get_checkpoint_dir, reset_article, reset_all  # noqa: E402

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--hash", dest="article_hash", help="16-char article hash to reset")
    group.add_argument("--all", action="store_true", help="Reset ALL checkpoints (requires --confirm)")
    parser.add_argument("--confirm", action="store_true", help="Required for --all to actually delete")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.article_hash:
        # Check existence via a non-creating path probe. get_checkpoint_dir would
        # mkdir the dir as a side effect — avoid that so "missing hash" exit=1 is honest.
        from lib import checkpoint as ckpt
        root = ckpt.BASE_DIR / "checkpoints" / args.article_hash
        if not root.exists() or not any(root.iterdir()):
            logger.error("no checkpoint dir found for hash=%s (path=%s)", args.article_hash, root)
            return 1
        reset_article(args.article_hash)
        logger.info("reset checkpoint for hash=%s", args.article_hash)
        return 0

    if args.all:
        if not args.confirm:
            logger.error(
                "--all refused: destructive operation requires --confirm. "
                "Re-run: python scripts/checkpoint_reset.py --all --confirm"
            )
            return 2
        reset_all()
        logger.info("reset ALL checkpoints (checkpoints/ root removed)")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
