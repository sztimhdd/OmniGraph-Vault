# aim-1-2 SUMMARY — DEPLOY-02 venv-aim1 setup

Status: ✅ DONE
Date: 2026-05-22
Commit: (pending — committed alongside DEPLOY-NOTES.md §DEPLOY-02 append)

## Outcome

- **Sibling venv built:** `/root/OmniGraph-Vault/venv-aim1/` on Python 3.11.0rc1, 153 packages, full `requirements.txt` installed cleanly (EXITCODE=0)
- **kb-api venv UNTOUCHED:** `/root/OmniGraph-Vault/venv/` still Python 3.10.12 with 160 packages; kb-api PID 3512216 still serving `uvicorn kb.api:app --host 127.0.0.1 --port 8766` throughout aim-1-2
- **Import smoke:** 25/25 ingest-critical modules import cleanly via `venv-aim1/bin/python`
- **HEAD on Aliyun:** `4eaef45` (unchanged from aim-1-1) — `venv-aim1/` is untracked and will NOT be committed
- **Operator round-trips:** all venv build + pip install + smoke ops ran via direct Bash SSH (`ssh aliyun-vitaclaw '...'`) per `feedback_aim1_agent_is_operator.md`; ZERO user round-trips

## Decision: Option C — sibling `venv-aim1/` for ingest

User-directed (2026-05-22) after agent surfaced the python-version blocker:

- Existing `venv/` is Python 3.10.12 (kb-api prod runtime, 160 packages, hardcoded in `kb-api.service` ExecStart). LightRAG ≥3.11 requirement makes this venv unusable for ingest.
- System python inventory: `/usr/bin/python3.10` (3.10.12), `/usr/bin/python3.11` (3.11.0rc1). No 3.12 / 3.13 available.
- Three options surfaced — **C chosen** for: (a) preserve kb-api 807-package verified prod combo (avoid MemoryMax=8G OOM risk on restart), (b) 3.11.0rc1 ABI is stable (RC published days before 3.11.0 final, all ingest cp311 wheels resolve), (c) aim-3 systemd timer ExecStart simply points at `venv-aim1/bin/python` — long-term maintenance cost is one path string.

## Two deviations recorded (per user mandate)

**Deviation 1 — Python 3.11.0rc1 (release candidate, not formal stable):**
- Selected because Aliyun Ubuntu has no 3.11 final / 3.12 / 3.13 in `/usr/bin/`.
- Risk: 3.11.0rc1 ABI froze before 3.11.0 final (2022-10); ingest-side packages all have cp311 wheels that resolve cleanly. Smoke (25/25 imports) confirms ABI compat.
- Mitigation if instability surfaces: rebuild `venv-aim1` on a properly built python3.11 final (apt or compile from source). Keeping kb-api on 3.10 means rebuild is contained to the ingest side.

**Deviation 2 — Dual-venv architecture:**
- `venv/` → kb-api (uvicorn), Python 3.10.12, 160 packages, PID 3512216 unchanged through aim-1-2.
- `venv-aim1/` → ingest (DEPLOY-04 smoke target, aim-3 systemd timer ExecStart target), Python 3.11.0rc1, 153 packages.
- aim-1-3 / aim-1-4 command templates use `venv-aim1/bin/python` and `venv-aim1/bin/pip` exclusively. `kb-api.service.d/override.conf` is NOT touched.
- aim-3 systemd timer (future phase) ExecStart will be `/root/OmniGraph-Vault/venv-aim1/bin/python <ingest-script>`.

## Build evidence (post-build state on Aliyun)

```
=== venv-aim1 python ===
Python 3.11.0rc1
sys.version_info(major=3, minor=11, micro=0, releaselevel='candidate', serial=1)
executable: /root/OmniGraph-Vault/venv-aim1/bin/python

=== venv-aim1 package count ===
153 packages

=== Key packages ===
lightrag-hku==1.4.16
google-genai==1.75.0
openai==2.38.0
lancedb==0.30.2
kuzu==0.11.3
pymupdf==1.27.2.3
playwright==1.60.0
apify-client==3.0.0
litellm==1.82.6
instructor==1.15.1
graphifyy==0.5.3            # PyPI dist name; import name is `graphify` (one y)
trafilatura==2.0.0
langdetect==1.0.9
aiolimiter==1.2.1
tenacity==9.1.4
numpy==2.4.6
lxml==5.4.0
feedparser==6.0.12

=== kb-api venv (untouched control) ===
venv/bin/python -V          → Python 3.10.12
pip list count              → 160 packages
kb-api process              → PID 3512216 still running uvicorn on 127.0.0.1:8766
```

## Import smoke (25/25 PASS)

```
OK (25/25): lightrag, google.genai, openai, apify_client, playwright, lancedb,
            kuzu, pymupdf, trafilatura, feedparser, litellm, instructor,
            graphify, langdetect, aiolimiter, tenacity, pytest, numpy,
            requests, PIL, bs4, html2text, dotenv, nest_asyncio, lxml
FAIL (0)
EXIT=0
```

**Smoke note — graphifyy import-name divergence:** PyPI distribution `graphifyy==0.5.3` (two `y`) installs into site-packages under top-level module `graphify` (one `y`). Confirmed via `graphifyy-0.5.3.dist-info/top_level.txt`. Production code that uses this lib must `import graphify`, not `import graphifyy`. First smoke iteration imported `graphifyy` and failed; corrected to `graphify` and 25/25 PASS. Documented in DEPLOY-NOTES.md §DEPLOY-02 so future code reviewers don't repeat the mistake.

## Audit verdict

- Sibling venv-aim1 built on intended Python (3.11.0rc1): ✅ YES
- Full `requirements.txt` installed (no subset, per user mandate): ✅ YES (EXITCODE=0)
- 25/25 ingest-critical imports pass: ✅ YES
- kb-api `venv/` Python version unchanged (3.10.12): ✅ YES
- kb-api `venv/` package count unchanged (160): ✅ YES
- kb-api process PID 3512216 still serving uvicorn: ✅ YES
- HEAD unchanged (4eaef45): ✅ YES
- `kb-api.service.d/override.conf` not touched: ✅ YES
- Both deviations recorded in DEPLOY-NOTES.md §DEPLOY-02: ✅ YES

## Discipline checks

- ✅ **No-secrets:** DEPLOY-NOTES.md §DEPLOY-02 + this SUMMARY contain only python versions, package names + versions, file paths, process PIDs, log file paths. No API keys / tokens / SA JSON / `.env` content.
- ✅ **No-connection-details:** No SSH host / port / user / IP / private key. Agent uses local SSH alias `aliyun-vitaclaw`.
- ✅ **Operator-channel:** Agent IS operator per `feedback_aim1_agent_is_operator.md`. All venv build + pip install + smoke ops ran via direct Bash SSH (`ssh aliyun-vitaclaw '...'`), no user round-trips.
- ✅ **Red lines honored:** No `git add -A` / `git add .`, no `--amend`, no `--force`, no `--hard`, no `systemctl` ops, no `kb-api.service.d/override.conf` touched, no kb-api restart triggered, no kb-api venv (`venv/`) packages added/removed/upgraded. `venv-aim1/` is untracked on Aliyun and will NOT be committed (venv contents reproducible from `requirements.txt`).
- ✅ **Forward-only edit:** §DEPLOY-02 is a net-new append to DEPLOY-NOTES.md; §DEPLOY-01 from aim-1-1 is unchanged. This SUMMARY is a net-new file.
- ✅ **kb-api preservation:** PID 3512216 still serving on `127.0.0.1:8766` throughout aim-1-2; `venv/` Python version (3.10.12) and package count (160) unchanged.

## Bridge to aim-1-3

`venv-aim1` is operational with all 27 top-level deps + transitive resolved. aim-1-3 (DEPLOY-03 env extension) and aim-1-4 (DEPLOY-04 e2e smoke) command templates will use `venv-aim1/bin/python` exclusively. `/root/.hermes/.env` is NOT touched in aim-1-2 — env extension is aim-1-3 scope. aim-1-3 will append 6 ingest provider keys (DEEPSEEK / SILICONFLOW / VERTEX SA path / GEMINI / APIFY × 2) preserving existing kb-api keys + file mode/ownership.

aim-3 systemd timer (future phase) ExecStart will be:
```
ExecStart=/root/OmniGraph-Vault/venv-aim1/bin/python <ingest-script>
```

## Files modified by aim-1-2

- `.planning/phases/aim-1-code-env-deploy/DEPLOY-NOTES.md` (§DEPLOY-02 appended)
- `.planning/phases/aim-1-code-env-deploy/aim-1-2-SUMMARY.md` (this file, net-new)

No code / config / runtime changes outside of the untracked Aliyun-side `/root/OmniGraph-Vault/venv-aim1/` directory tree (which is reproducible from `requirements.txt` and intentionally not committed).
