# VitaX Wiki candidate preflight

Date: 2026-09-09. Scope: read-only checks before copying or running the
controller-approved candidate runner.

## Result

`PASS` for the required preflight. No remote files were modified and the
accepted input was not executed.

## Accepted input

- `OHPC` reported hostname `OH-Desktop`.
- The accepted run is a directory and is not a symlink.
- The sorted SHA-256 manifest contains 20 regular files; see
  `INPUT-MANIFEST.json`.
- `rag/graph_chunk_entity_relation.graphml` SHA-256 is
  `c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768`,
  exactly matching the single-article acceptance contract.
- The source receipt SHA-256 is
  `e24f4195e5bd071eb48010a3fcb340ba166d7e470afe913b748945fbd397d4af`.
- A redacted structural check found `READY_FOR_REVIEW`, both recorded phases
  `PASS`, one processed record, and that record present in the full-document
  store. Its key-set digest is
  `5a72abae1a5c183e0fc705e7fbcea9c0bd258ef453a652b3d4d0b3c4251ff1e7`,
  matching the prior acceptance.

## Compiler dependencies

The isolated candidate code sibling matches the local intended sources for all
bounded dependencies:

| Path | SHA-256 |
| --- | --- |
| `kb/error_book.py` | `395c4c8e7e4d09503a22b627317b52126cfdcbe25eedea49e45f540f213696e8` |
| `kb/wiki_compiler/__init__.py` | `2d674a9eaf916ea28910b614635c7e924a7c0a32543287a78f034cc075e10923` |
| `kb/wiki_compiler/adapters/__init__.py` | `9e1e3b63ebff221d62f63c002fb15e4cb19f4150f4e2d7df828d2a24647695c2` |
| `kb/wiki_compiler/adapters/w3.py` | `0331ef5a9b31e4da271e7c0676a18e4ae4d9374c0fed86660b552f3c2106b48c` |
| `kb/wiki_compiler/assembler.py` | `e67c617025d941e980d5fa5f548d7d77e361f80dd88a45b958e6916ac0111f4c` |
| `kb/wiki_compiler/engine.py` | `60f7ed1c14ed7b47f85b9a281f0b7170a3fb7bb4d8c84b6f8c732f56e284a9f8` |
| `kb/wiki_compiler/models.py` | `3a75778f37e17943798c3cbaafa795d3c594821b244ba0f90466555dca4fa270` |

The remote venv resolves `frontmatter` successfully. This preflight did not
load the probe runner, call a model or service, create a tunnel, or write to a
repository Wiki path.
