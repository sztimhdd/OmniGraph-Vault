# VX005 prestart read-only slice: TDD evidence

Recorded: 2026-09-09
Repository: /Users/hai/Projects/ohpc-migration/VitaX

## RED

Command:

```sh
.venv/bin/python -m pytest tests/unit/test_ingest_prestart_read_only.py -q
```

Observed result: `1 failed`.

Expected failure:

```text
AssertionError: ... cleanup_stuck_docs.py --all-failed ... endswith(
    "cleanup_stuck_docs.py --dry-run"
)
```

The CLI portion of the test completed against a temporary status file and a
mocked `config` module. The failure was limited to the three tracked systemd
templates retaining destructive `ExecStartPre ... --all-failed`.

## GREEN

After replacing only the three tracked `ExecStartPre` arguments with
`--dry-run`, the following command completed successfully:

```sh
.venv/bin/python -m pytest tests/unit/test_ingest_prestart_read_only.py tests/unit/test_cleanup_stuck_docs.py -q
```

Observed result:

```text
14 passed in 0.04s
```

The new regression executes the cleanup CLI with a temporary fake status file
and mocked config import. It proves dry-run reports the processing candidate,
does not construct RAG, reports zero deletions, and preserves the status file
bytes. It also asserts the three `ExecStart` ingest commands remain unchanged.

## Diff whitespace scope

Whole-tree whitespace verification must accept CRLF line endings retained by
parallel `config.py` work:

```sh
git -c core.whitespace=cr-at-eol diff --check
```

No deployment, daemon reload, service start, SSH operation, real cleanup, or
runtime-data operation was performed.
