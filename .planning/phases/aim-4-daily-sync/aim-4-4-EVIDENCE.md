# aim-4-4 — SYNC-03 runbooks evidence

**Timestamp:** 2026-05-24
**Plan:** aim-4-4 (Wave 4)
**REQs:** SYNC-03
**Status:** PARTIAL — runbooks committed; 24h-post-fire verification deferred

## Runbooks committed

- `docs/runbooks/aim-4-aliyun-wiki-commit.md` — Aliyun manual wiki commit (Q4c)
- `docs/runbooks/aim-4-databricks-sync03-verify.md` — SYNC-03 verification

## aim-4 deploy timestamp

- aim-4-3 commit on `main`: `b522f64` ("feat(aim-4): Hermes
  omnigraph-daily-pull systemd timer (SYNC-02,SYNC-04)")
- ISO timestamp: `2026-05-24 21:15:28 -0300`
- This is the reference timestamp for the SYNC-03 pass criterion
  (`git log -1 kb/wiki/` on Databricks must be ≥ this timestamp).

## Contract grep verifications

Run on the two runbooks at commit time (Wave 4 evidence):

| Grep contract | File | Required | Observed |
| --- | --- | --- | --- |
| `grep -c 'aliyun-vitaclaw'` | `docs/runbooks/aim-4-aliyun-wiki-commit.md` | ≥ 1 | 5 |
| `grep -c 'kb/wiki/'` | `docs/runbooks/aim-4-aliyun-wiki-commit.md` | ≥ 1 | 13 |
| `grep -c 'LLM-Wiki-Integration-P2'` | `docs/runbooks/aim-4-aliyun-wiki-commit.md` | exactly 1 | 1 |
| `grep -c 'git log -1 kb/wiki/'` | `docs/runbooks/aim-4-databricks-sync03-verify.md` | ≥ 1 | 7 |
| `grep -c 'aim-4 deploy timestamp'` | `docs/runbooks/aim-4-databricks-sync03-verify.md` | ≥ 1 | 5 |
| Phrase `existing git pull workflow` | `docs/runbooks/aim-4-databricks-sync03-verify.md` | ≥ 1 | 1 |
| Aliyun root password `Hzyc...` (must NOT appear) | both runbooks | 0 | 0 |
| Hermes creds (`49221`, `ohca.ddns.net`, `sztimhdd`) | both runbooks | 0 | 0 |

All contracts satisfied.

## Deferred operator action (post-aim-4-4)

SYNC-03 verification cannot fully close in this plan's execution
window because:

1. The Hermes systemd timer (`omnigraph-daily-pull.timer`) needs at
   least one **natural** fire at 02:00 ADT after aim-4-3 deploy.
   Manual fire from aim-4-3 Task 3 does NOT count per the SYNC-03
   wording "24h after first SYNC-02 fire".
2. The Aliyun operator must execute the wiki commit runbook at least
   once post aim-4 deploy.
3. The Databricks operator (or the Databricks app's existing pull
   workflow) must `git pull` on the consumer side post that commit.

### TODO checklist (track via aim-5 STAB checkpoint)

- [ ] Path A deploy key actually generated on Aliyun + registered
      read-write on the GitHub repo. Deferred — first wiki commit
      will trigger this setup if Path A is the chosen route.
- [ ] Path B patch round-trip exercised end-to-end. Deferred — only
      relevant if Path A is blocked by GitHub admin or corp network.
- [ ] First real wiki commit verified at the Databricks consumer via
      `git log -1 kb/wiki/`. Deferred — depends on
      LLM-Wiki-Integration-P2 (or operator) producing the first wiki
      content commit.
- [ ] aim-5 STAB checkpoint will close all 4 items above (collect
      Databricks `git log -1 kb/wiki/` stdout, Aliyun wiki commit
      hash, PASS verdict, append forward-only to this evidence file).

## References

- aim-4 CONTEXT FINDING 8 (`.planning/phases/aim-4-daily-sync/aim-4-CONTEXT.md`
  lines 132-141)
- aim-4 CONTEXT §"Databricks SYNC-03 verification command"
  (lines 306-314)
- REQUIREMENTS SYNC-03
  (`.planning/REQUIREMENTS-Aliyun-Ingest-Migration-v1.md` line 73)
- aim-4-3 evidence (`b522f64` on `main`, deploy timestamp source)
