# VitaX Wiki candidate acceptance

## Verdict

**[CURRENTLY VERIFIED / PASS]** The isolated Wiki candidate run is accepted
as a local, synthetic-source compiler artifact.

This acceptance covers only the candidate at
`/home/sztimhdd/.local/share/vitax-probes/vitax-vx001.H8iYB3wq/runs/vitax-wiki-candidate-mt6cr6le`.
It does not accept public Wiki publication, production Wiki consistency,
semantic quality, production deployment, ingestion, or broader VX-004 work.

## Evidence

- **Host and runner:** a fresh read-only SSH check reported `OH-Desktop`; the
  remote runner SHA-256 was
  `199e6589bb8d483373c98cf6615af84f23a8123aaf1527f09aca7e5e699a0a0b`.
- **Input boundary:** the accepted sibling is non-symlink, has exactly 20
  regular files, and every SHA-256 matched `INPUT-MANIFEST.json`. Its GraphML
  digest remained
  `c27f77e054fc309516b3e6840e0665d4f2491ec84440ef961363b26031b18768`.
- **Receipt binding:** the remote raw candidate receipt SHA-256 was
  `e6372a2f63ccd52e8df15c569cf573d36922206753f16d29cc1f13d32ac8bb7b`,
  matching `RECEIPT_REDACTED.json`. The receipt reports `APPLIED`, source
  `synthetic`, and source reference `9955937e7a`.
- **Candidate artifact:** the candidate receipt declares exactly two pre-receipt
  artifacts: the empty per-page lock and
  `wiki/entities/entity-extraction.md`. The page SHA-256 was
  `722c06f89dbde370afa0e43d7bff536de104e27f4748f1b99e979fcf8553fa57`,
  matching both the remote file and `RECEIPT_REDACTED.json`.
- **Lineage:** a read-only stdlib check confirmed one processed persisted
  document, its URL-derived canonical reference, the matching entity buffer,
  the bounded persisted-source summary in the candidate page, and its GFM
  article citation. No article body was emitted in this review.
- **Repository boundary:** the available receipt reports a 29-file repository
  Wiki manifest with aggregate SHA-256
  `c8dae55791f3ddf33a3c939da80252162cfc2a3c5ce0d156dd294f671b5d3047`;
  this acceptance did not read a production Wiki.

## Review limits

[KNOWN] Controller disposition: accepted after reviewing the independent evidence above and the execution record. The three unskipped local tests passed (0.07s), covering source-linked compilation with socket creation denied, refusal of nonprocessed input, and real compiler rejection with candidate-local diagnostics. The project venv added declared python-frontmatter 1.3.0 and PyYAML 6.0.3; pip check passed. These are targeted tests, not the full repository suite.

The acceptance review performed no model calls, project imports, queries,
candidate re-execution, production-Wiki reads, or remote writes. It relied on
the supplied run record and independently read fixed remote files only.
