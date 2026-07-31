#!/usr/bin/env python3
"""Qdrant → Qdrant BGE-M3 migration for old machine — in-process inference.

Loads BGEM3FlagModel directly (no HTTP embed-server), uses all CPU threads,
streams scroll → encode → upsert. Resumable via existing target IDs.

Run with /root/embed-venv/bin/python (has FlagEmbedding + CPU torch).
"""
from __future__ import annotations

import argparse, json, os, time

from qdrant_client import QdrantClient, models
from FlagEmbedding import BGEM3FlagModel

QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
MODEL_PATH = os.environ.get("EMBED_MODEL_PATH", "/models/bge-m3/models/BAAI--bge-m3/snapshots/master")
BATCH = 128         # sorted by length; short texts batch big, long ones alone
UPSERT_BATCH = 1024
SUFFIX = "_bge_m3_1024d"
MAX_TEXT_CHARS = 2000  # entity/rel descriptions rarely exceed this

COLLECTIONS = ["entities", "chunks", "relationships"]

_model = None


def get_model() -> BGEM3FlagModel:
    global _model
    if _model is None:
        import torch
        torch.set_num_threads(8)  # machine has 8 cores; torch defaults to 4
        t0 = time.time()
        print(f"Loading BGE-M3 from {MODEL_PATH}...", flush=True)
        _model = BGEM3FlagModel(MODEL_PATH, use_fp16=False, local_files_only=True)
        print(f"Model loaded in {time.time()-t0:.0f}s", flush=True)
    return _model


def existing_ids(c: QdrantClient, dst: str) -> set:
    ids = set()
    offset = None
    while True:
        pts, offset = c.scroll(
            dst, limit=10000, offset=offset,
            with_payload=False, with_vectors=False,
        )
        ids.update(p.id for p in pts)
        if offset is None:
            break
    return ids


def migrate(c: QdrantClient, model, name: str, dry: bool = False) -> dict:
    src = f"lightrag_vdb_{name}_gemini_embedding_2_3072d"
    dst = f"lightrag_vdb_{name}{SUFFIX}"

    cnt = c.count(src, exact=True).count
    done = existing_ids(c, dst) if not dry else set()
    print(f"[{name}] source={src} points={cnt} already_done={len(done)}", flush=True)

    if dry:
        return {"source": cnt, "upserted": 0, "skipped_empty": 0, "resumed": len(done)}

    processed = upserted = skipped = 0
    next_offset = None
    t0 = time.time()
    while True:
        pts, next_offset = c.scroll(
            src, limit=UPSERT_BATCH, offset=next_offset,
            with_payload=True, with_vectors=False,
        )
        if not pts:
            break

        todo = [p for p in pts if p.id not in done]
        payloads = [p.payload or {} for p in todo]
        texts = [
            (pl.get("content") or pl.get("entity_name") or "")[:MAX_TEXT_CHARS]
            for pl in payloads
        ]
        good, bad = [], []
        for p, pl, t in zip(todo, payloads, texts):
            (good if t.strip() else bad).append((p, pl, t))

        # Sort short texts first: BGE-M3 pads to longest in batch, so mixed
        # batches run at long-text speed. Sorting by length batches short
        # texts together → most points embed fast, few long ones pay alone.
        good.sort(key=lambda x: len(x[2]))

        for i in range(0, len(good), BATCH):
            chunk = good[i:i + BATCH]
            out = model.encode([t for _, _, t in chunk], batch_size=len(chunk))
            vectors = out["dense_vecs"]
            c.upsert(
                dst,
                points=[
                    models.PointStruct(id=p.id, vector=v.tolist(), payload=pl)
                    for p, pl, v in zip(
                        [x[0] for x in chunk], [x[1] for x in chunk], vectors
                    )
                ],
                wait=True,
            )
            upserted += len(chunk)
            processed += len(chunk)

        skipped += len(bad)
        elapsed = time.time() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(
            f"[{name}] {processed}/{cnt - len(done)} upserted={upserted} "
            f"empty={skipped} ({rate:.1f} pts/s)", flush=True
        )
        if next_offset is None:
            break

    return {"source": cnt, "upserted": upserted, "skipped_empty": skipped, "resumed": len(done)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only", choices=COLLECTIONS, default=None)
    args = parser.parse_args()

    c = QdrantClient(url=QDRANT_URL, timeout=60)
    model = get_model() if not args.dry_run else None
    names = [args.only] if args.only else COLLECTIONS
    total = {"source": 0, "upserted": 0, "skipped_empty": 0, "resumed": 0}
    for name in names:
        r = migrate(c, model, name, dry=args.dry_run)
        for k in total:
            total[k] += r[k]

    print(f"\nTOTAL: {json.dumps(total)}")
    if args.dry_run:
        print("DRY RUN — no data written")


if __name__ == "__main__":
    main()
