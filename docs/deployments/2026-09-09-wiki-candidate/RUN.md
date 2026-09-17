# VitaX Wiki candidate execution

Date: 2026-09-09. The controller-approved runner SHA-256
`199e6589bb8d483373c98cf6615af84f23a8123aaf1527f09aca7e5e699a0a0b`
was copied as the sole source addition to the isolated candidate code sibling.
`OHPC` again reported `OH-Desktop`, and the remote copied file matched the
approved digest before execution.

## Result

`APPLIED`, exit code `0`, within the requested 120-second bound. The runner
reported `network_or_model_execution: not attempted`.

Candidate output directory:

`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-wiki-candidate-mt6cr6le`

The redacted receipt and output digests are in `RECEIPT_REDACTED.json`. No raw
article body, production Wiki path, or production Wiki page name is retained
in this evidence directory.

## Post-run verification

- The 20-file pre-run `INPUT-MANIFEST.json`, receipt source-input hashes, and
  independently recomputed post-run accepted-input manifest are identical.
- The GraphML digest remains
  `c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768`.
- The receipt repository-Wiki manifest equals a freshly recomputed 29-file
  manifest after the run (aggregate SHA-256
  `c8dae55791f3ddf33a3c939da80252162cfc2a3c5ce0d156dd294f671b5d3047`).
- The candidate artifact manifest has two files and matches the receipt;
  the candidate page SHA-256 is
  `722c06f89dbde370afa0e43d7bff536de104e27f4748f1b99e979fcf8553fa57`.
- The page contains the accepted bounded source summary. A read-only lineage
  check confirmed processed document to source URL to canonical MD5 reference
  to the page's GFM article citation.

## Scope controls

The runner source has only standard-library imports plus the bounded Wiki
compiler, adapter, and article-reference modules; static import inspection
found no socket, subprocess, HTTP-client, or runtime-ingestion import. This is
static evidence only; it is not a kernel sandbox claim. The run used the
authorized `env -i` command and did not create a service connection, tunnel,
or production Wiki write.
