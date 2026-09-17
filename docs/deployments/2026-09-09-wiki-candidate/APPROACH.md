# VitaX accepted synthetic article Wiki candidate

## Status

`READY_FOR_REVIEW`. This packet authorizes neither public Wiki
publication nor production writes. It uses only the isolated accepted run:

`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-single-article-lao1z1rb`

## Reused entrypoint

`scripts/vitax_wiki_candidate_probe.py` reads the accepted run's processed
LightRAG document record and matching entity buffer, then calls the existing
compiler chain exactly once:

`w3.build_w3_pack_from_records` -> `w3.propose_w3_patch` ->
`engine.apply_patch`.

The probe labels the evidence source `synthetic`, carries its canonical
10-character article reference, chooses the first sorted non-empty existing
compiler slug, and derives a bounded title and summary directly from the
accepted persisted document. It does not ingest, fetch, query, embed, invoke
an LLM, or load credentials.

The W3 record adapter uses a record title for evidence metadata but emits a
generic frequency context block instead of rendering `record["text"]`. The
probe preserves the adapter-generated evidence and identity, then replaces its
sole returned context block with the deterministic bounded source summary
before the existing assembler and engine run. This is source projection, not
LLM summarization.

Before calling the compiler it hashes every regular file beneath the accepted
run. After the compiler returns it recomputes and compares the same map. A
change aborts the run with `SOURCE_INPUT_MUTATED`. It snapshots the explicit
read-only repository-Wiki reference before and after the compiler call and
rejects any change there. The receipt stores the processed document ID, source URL and
reference, input and repository-Wiki hashes, and the complete pre-receipt
candidate artifact hash manifest, including compiler `.locks` files and a
candidate-local `compiler_failures.jsonl` on rejection. It does not store the
article body.

## Reviewed remote command

The reviewed local script must first be present at the same relative path in
the already-isolated candidate code sibling and match its controller-reviewed
SHA-256: `199e6589bb8d483373c98cf6615af84f23a8123aaf1527f09aca7e5e699a0a0b`.
Then run exactly:

```bash
cd /home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/code && \
env -i PATH=/usr/bin:/bin LANG=C.UTF-8 PYTHONPATH="$PWD" PYTHONDONTWRITEBYTECODE=1 OMNIGRAPH_LOAD_ENV=0 \
  /home/sztimhdd/OmniGraph-Vault/venv/bin/python \
  scripts/vitax_wiki_candidate_probe.py \
  --accepted-run /home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-single-article-lao1z1rb \
  --output-parent /home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs \
  --repository-wiki-root /home/sztimhdd/OmniGraph-Vault/kb/wiki \
  --today 2026-09-09 \
  --execute
```

The command requires the accepted run and output parent to be direct siblings,
checks the accepted runner ownership marker, and rejects symlinks. Its sole
write scope is a fresh directory named
`runs/vitax-wiki-candidate-*/`, containing compiler output (including any
`.locks` file), candidate-local `compiler_failures.jsonl` on rejection, and
`VITAX_WIKI_CANDIDATE_PROBE.json`. It does not write to the accepted run, the
candidate code root, or any production Wiki path.

## Required output review

Accept only a zero exit and a receipt with:

- `status: APPLIED` or `status: SUGGESTION`;
- `network_or_model_execution: not attempted`;
- one processed document ID, source URL/ref, and source `synthetic`;
- a candidate directory under the declared `runs/` parent;
- unchanged `source_input_hashes` and `repository_wiki_hashes`; and
- a complete candidate artifact hash manifest whose paths remain under that
  candidate directory.

An `APPLIED` result proves a local candidate page only. It does not establish
public publication, production Wiki consistency, semantic quality, or broader
VX-004 completion.

## Required read-only preflight

Before placing the reviewed runner in candidate code or executing it, the
worker must capture a complete sorted SHA-256 manifest of every regular file
in the accepted run and verify the persisted GraphML digest against the prior
single-article acceptance value
`c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768`.

```bash
ssh -o BatchMode=yes -o ConnectTimeout=15 OHPC '
set -eu
run=/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-single-article-lao1z1rb
test "$(hostname)" = OH-Desktop
test -d "$run"
test ! -L "$run"
test "$(sha256sum "$run/rag/graph_chunk_entity_relation.graphml" | awk "{print \$1}")" = c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768
find "$run" -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
'
```

This preflight is read-only and emits hashes and paths only; it does not read
or print article bodies, credentials, or runtime logs.
