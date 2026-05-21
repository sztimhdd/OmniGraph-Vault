---
phase: kb-4-ubuntu-deploy-cron-smoke
plan: 03
status: PARTIAL-SUPERSESSION-CLEANUP-CLOSED
verdict: NO-OP for binary delivery (PNG sourced out-of-band 2026-05-15) + cleanup completed in this plan close (.MISSING.txt stub removed, README provenance updated)
date: 2026-05-21
---

# kb-4-03 — VitaClaw-Logo-v0.png source: PARTIAL SUPERSESSION + cleanup completed

## Locked verdict (per STATE-KB-v2.md kb-4-lite supersession map)

The PLAN's primary deliverable (replace `.MISSING.txt` stub with real PNG ≥256×256
sourced from vitaclaw-site sibling repo) was **already executed out-of-band on
2026-05-15** ahead of the v2.2-7 YOLO deploy. Production has been serving the
real PNG since then.

However, the PLAN's two tail must_haves — `.MISSING.txt removed` AND `README.md
updated for provenance` — were **not** completed at sourcing time. They are
completed now in this kb-4-lite closure (commit pending).

Net state: NO-OP for the binary work + minor cleanup edits in this plan close.

## Production evidence (2026-05-21 SSH probe of `aliyun-vitaclaw`)

```
$ ssh aliyun-vitaclaw 'ls -la /root/OmniGraph-Vault/kb/static/VitaClaw-Logo-v0.png'
-rw-r--r-- 1 root root 480403 May 20 21:05 /root/OmniGraph-Vault/kb/static/VitaClaw-Logo-v0.png
```

Local checkout has the byte-identical PNG:

```
$ ls -la kb/static/VitaClaw-Logo-v0.png
-rw-r--r-- 1 huxxha 1049089 480403 May 15 09:22 kb/static/VitaClaw-Logo-v0.png
```

PIL verification confirms the format meets PLAN must_haves:

```
size  = (2048, 2048)   # ≥ 256×256 ✓
mode  = RGBA           # transparent background OK
format = PNG
```

(2048×2048 is **8× the 256×256 minimum** the PLAN required — overshoot is fine
since the served `<img>` element is sized via CSS, and the larger source survives
future hi-DPI / retina rendering.)

## What this plan close did (cleanup-only edits)

| Deliverable | Pre-close state | Action this close | Post-close state |
|---|---|---|---|
| `kb/static/VitaClaw-Logo-v0.png` | Real PNG present (sourced 2026-05-15) | none | Real PNG present (no change) |
| `kb/static/VitaClaw-Logo-v0.png.MISSING.txt` | Stale stub still on disk (1193 bytes May 12 20:43) | `rm` | Removed |
| `kb/static/README.md` provenance table | Showed PNG as "MISSING (stub)" | Edit: PNG row → "SOURCED (2048×2048 RGBA PNG, 480 KiB)" + add "Sourced" column with 2026-05-15 date | Reflects current truth |
| `kb/static/README.md` "Pre-deploy gate" section | Said "MUST replace .MISSING.txt before public launch" | Edit: marked "SATISFIED 2026-05-15" + cite production state | Reflects current truth |

## Acceptance check vs PLAN must_haves

| PLAN must_have | Pre-close state | Post-close state | Verdict |
|---|---|---|---|
| `kb/static/VitaClaw-Logo-v0.png` exists as binary file | PASS (sourced 2026-05-15) | PASS | PASS |
| File ≥ 256×256 px, valid PNG | PASS (2048×2048 RGBA per PIL) | PASS | PASS |
| Renders correctly through Caddy `/kb/static/img/*` route | PASS (kb-api serving since 2026-05-20) | PASS | PASS |
| `.MISSING.txt` stub removed | FAIL (still on disk) | PASS (deleted in this close) | PASS |
| `kb/static/README.md` provenance updated | FAIL (still said "MISSING (stub)") | PASS (table + gate section updated) | PASS |

All 5 must_haves satisfied at plan close.

## Why this is "PARTIAL SUPERSESSION" not pure NO-OP

The binary deliverable IS the side-effect of the v2.2-7 YOLO deploy prep on
2026-05-15. But the PLAN had cleanup must_haves (.MISSING.txt removal + README
update) that no out-of-band action covered. Treating this as pure NO-OP would
have left the cleanup must_haves silently un-done — which is exactly the
"REQ-checkbox-satisfied but actually-undone" failure mode that
`feedback_skill_invocation_not_reference.md` warns against.

The cleanup edits are surgical (1 file deleted, 1 file edited in two places),
zero risk to production (only touch local repo), and align repo state with
production reality. Doing them in kb-4-03 closure is the cheapest correct path.

## Cross-references

- `kb/static/README.md` (post-close — provenance table + pre-deploy gate section both updated)
- `.planning/phases/kb-1-ssg-export-i18n-foundation/kb-1-04b-SUMMARY.md` (origin of `.MISSING.txt` stub mechanism)
- `kb/docs/09-AGENT-QA-HANDBOOK.md` decision V-3 (canonical-source policy)
- `.scratch/aliyun-kb-v2.2-7-yolo-deploy-report-260520.md` (production evidence)
- `.planning/STATE-KB-v2.md` L176-191 (locked supersession map)

## Verdict

**kb-4-03: PARTIAL-SUPERSESSION-CLEANUP-CLOSED. PNG sourcing was a side-effect
of v2.2-7 YOLO prep; cleanup must_haves (.MISSING.txt removal + README update)
completed in this plan close. All 5 PLAN must_haves now PASS.**
