# 260610-eoy — Unknowns / User Decisions Required

**Status:** items NOT determined by audit; user must answer before BACKUP_PLAN.md is run.

---

## 1. Tenant cleanup decision (~8G saving)

5 tenant directories under `planb-local-m1/vitaclaw-local/tenants/` whose containers are `Exited (255) 3 days ago`:

| Tenant | Size | Container status |
|---|---|---|
| `viaproxy` | 1.6G | Exited 3d ago |
| `finalfinal` | 1.6G | Exited 3d ago |
| `debug2` | 1.6G | Exited 3d ago |
| `cacheclear` | 1.6G | Exited 3d ago |
| `bugfixtest` | 1.5G | Created (never started) |

Plus `tenants/uat-*` (5 dirs, ~280M) — UAT artifacts.

**Question:** are any of these load-bearing in any way (data still needed, intentional reserved space, archival reference)? Or is the only "real" tenant `tenantB` and the rest are QA / debug / abandoned experiments?

**Default if no answer:** SKIP — exclude from backup, preserve on old host until snapshot.

---

## 2. VDB archive files (1.7G saving)

Inside `/root/.hermes/omonigraph-vault/lightrag_storage/`:

| File | Size |
|---|---|
| `vdb_archive_relationships.json` | 1.1G |
| `vdb_archive_entities.json` | 743M |
| `vdb_archive_chunks.json` | 57M |

**Question:** are these still load-bearing post-aim2 Qdrant migration? Or are they leftover from before the Qdrant cutover?

**How to verify:** `grep -rE "vdb_archive" /root/OmniGraph-Vault/{lib,kb,scripts}/ /root/OmniGraph-Vault/*.py 2>/dev/null` on the live host. If nothing references them in active code paths, they can be DROPPED.

**Default if no answer:** include in backup (safer; only adds 600M-700M compressed).

---

## 3. OmniGraph repo source: GitHub vs tarball

`/root/OmniGraph-Vault` is currently 4 commits BEHIND `origin/main` AND has 3 untracked items:

```
?? kol_config.py.bak-260610
?? scripts/qdrant_reingest_252.sh.bak-pre-collection-suffix
?? venv-aim1/
```

**Question:** is the canonical source-of-truth GitHub `origin/main` or the live Aliyun working tree?

- **If GitHub canonical:** SKIP P1.12 (omnigraph repo tarball). On new host, `git clone` the GitHub repo. The 4-commits-ahead remote state IS the truth.
- **If Aliyun working tree canonical:** include P1.12. The new host gets the local working tree (incl those 4 deviations).
- **Hybrid:** include P1.12 anyway as a paranoid safety net. ~150M compressed.

**Default if no answer:** Hybrid — include P1.12. Cheap insurance.

---

## 4. Vitaclaw planb-local-m1 compose orchestration

The `compose/` dir on Aliyun contains only:

- `conversation-store.yml` (1560 bytes, last modified Jun 8)
- `delivery.yml` (2206 bytes, Jun 8)

…but `docker ps` shows ~20 active containers — orchestrator, ag-ui, document-service, identity-service, persona-service, skill-service, tenant-web, ai-infra-rs, push, inbox, postgres, timescaledb, nats, minio, admin-dashboard, management-service, vc-delivery, plus a few exited tenants.

**Question:** where are the compose files / scripts that launch the OTHER 18 services?

**Hypothesis:** could be:
- (a) A separate ops repo (e.g. on GitHub or laptop) with the master compose stack
- (b) Each tenant has its own `compose/` dir launched by `docker compose -f tenants/<t>/compose/...`
- (c) A shell script in `/opt/vitaclaw/planb-local-m1/scripts/` orchestrates everything
- (d) Manual `docker run` via custom shell utilities

Without knowing the answer, P1.11 captures `compose/`, `dockerfiles/`, `scripts/`, `prompts/` — but if the launch logic is elsewhere (e.g. a separate GitHub repo), restoring this is incomplete.

**Default if no answer:** include P1.11; ALSO grep `/opt/vitaclaw/planb-local-m1/scripts/` and `tenants/tenantB/compose/` for compose references; flag any missing pieces. User must supply the master compose strategy before restore.

---

## 5. Vitaclaw shared volume consistency (live dump risk)

`vitaclaw-shared_convstore_runtime` and 3 other 1.3G runtime volumes are bind-mounted into `oven/bun:1.3.4` containers that are `Up 2 days (healthy)`.

**Question:** is hot-dumping these volumes safe? (i.e. are the bun runtimes flushing to disk such that a tar at any moment captures a consistent state?)

**Risk if NOT:** restored volume may have torn writes or partial state — services restart but with corrupt internal state.

**Mitigation:** scale services to 0 via compose, dump cold, scale back up. Cost: ~10 minutes of conversation-store / delivery / inbox / push downtime during the dump.

**Default if no answer:** hot dump (faster, ~99% safe). Document the risk; if any service misbehaves on restore, can re-dump cold.

---

## 6. Aliyun snapshot vs targeted backup priority

User has already taken an ECS snapshot. **Question:** is the targeted backup intended as:

- (a) **Primary** — restore strategy is "spin up new host, run RESTORE_RUNBOOK against fresh OS"
- (b) **Secondary** — restore strategy is "spin up snapshot-based ECS, only use targeted backup for selective transplant to k8s/ACK"
- (c) **Both** — keep both, decide at restore time based on what new infra ends up being

**Affects:** how aggressive the backup needs to be. If (a), we MUST capture every config + secret. If (b), the snapshot already covers everything; targeted backup just ensures portability across infra types.

**Default if no answer:** assume (c) Both. Targeted backup IS comprehensive. Snapshot is the disaster-recovery insurance.

---

## 7. New host topology (placeholder for user-supplied detail)

Backup is environment-agnostic. Restore depends on what user picks:

- (i) **Single new ECS** — just runs the same systemd services (RESTORE_RUNBOOK as written)
- (ii) **ACK k8s cluster** — same containers wrapped in k8s manifests (additional translation needed; not in this runbook)
- (iii) **Hybrid** — Caddy + omnigraph on a small ECS, vitaclaw on k8s

**Question:** which architecture is the new env?

**Default if no answer:** runbook assumes (i) for clarity; user adapts to (ii)/(iii) using same artifacts.

---

## 8. Aliyun backup retention before old host dies

ECS subscription expiry: **unknown** (user says "soon").

**Question:** how many days until OLD ECS is terminated?

**Affects:**
- Time available for parallel run on new host before DNS cutover
- Whether to keep paying ECS for grace period for safety net
- Whether to do backup once-and-done or also schedule a 2nd backup the day before expiry

**Default if no answer:** assume ≤14 days. Plan for cutover within 7d, keep old ECS as fallback for the remaining ~7d.

---

## 9. Domain / DNS owner

Caddy serves `:80` (no domain in Caddyfile, only IP-based + nip.io fallback for tenant routing).

**Question:** what's the production domain? Is DNS managed via:
- Aliyun DNS console
- Cloudflare
- Other registrar

**Affects:** Step 11 of RESTORE_RUNBOOK (DNS cutover).

**Default if no answer:** runbook stays domain-agnostic. User does DNS update outside of runbook scope.

---

## 10. WeChat scrape session state

`omnigraph-kol-scan.service` is currently `failed` on the old host. WeChat session likely needs re-auth (per memory `wechat_cookie_refresh_runbook.md`).

**Question:** is this OK to leave failed during cutover, or is it a blocker?

**Default if no answer:** leave failed, fix post-restore. New articles via RSS still flow; KOL scraping is just temporarily off. Re-auth flow exists in Hermes operator skill.

---

## 11. iptables / UFW ruleset

Aliyun has UFW chains + Docker chains visible in `iptables -S`. `iptables -P INPUT DROP` policy.

**Question:** are there custom UFW rules beyond Docker default? `ufw status` would show if user-defined rules exist.

**Affects:** P1.2 captures `iptables-save`, but UFW status is separate. If custom `ufw allow` rules exist, must restore them on new host.

**Default if no answer:** capture both `iptables-save` AND `ufw status verbose` in P1.2 to be safe. Add to runbook P1.2:
```bash
ufw status verbose > /tmp/ufw-status-260610.txt
```

---

## 12. /opt/vitaclaw/.deploy-backups + .incoming + kite-data

3 sub-dirs not listed in inventory:

- `.deploy-backups/` (Jun 8)
- `.incoming/` (May 27, perm 0700)
- `kite-data/` (May 23, ~192K)

**Question:** are these:
- Operator scratch dirs (drop)
- Live deploy state (keep)
- Mid-deploy partial uploads (`.incoming` smells like that)

**Default if no answer:** include `kite-data` in P1.11 (192K is trivial); skip `.deploy-backups` and `.incoming` (likely scratch).

---

## Action items for user

Before running any backup command:

1. ☐ Decide on items 1, 2, 3, 6, 7 — affects what gets backed up
2. ☐ Confirm item 4 (compose orchestration source) — affects whether restore is complete
3. ☐ Decide item 5 (hot vs cold volume dump) — affects ~10 min downtime trade-off
4. ☐ Confirm item 8 (days until expiry) — affects schedule
5. ☐ Items 9, 10, 11, 12 are nice-to-have; defaults are safe

Once answers are in, BACKUP_PLAN.md commands can run with confidence.
