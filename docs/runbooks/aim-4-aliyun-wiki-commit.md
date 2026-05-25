# Runbook — Aliyun manual wiki commit (aim-4..aim-5)

**Scope:** Per Q4c of the Aliyun-Ingest-Migration-v1 milestone, the
Aliyun → repo wiki write-back is **manual** during the aim-4..aim-5
window. This runbook is the operator's reference for when, what, and
how to run the manual commit. The auto-hook (post-write-to-`kb/wiki/`
→ push to `origin/main`) is deferred to a separate milestone (see
References below).

## When to run

Trigger conditions (any one of these → run the runbook):

1. New wiki content has accumulated under `/root/OmniGraph-Vault/kb/wiki/`
   on Aliyun (e.g., new `concepts/<term>.md`, new
   `comparisons/<a>-vs-<b>.md`).
2. The Hermes daily-pull (SYNC-02) and the Databricks `git pull`
   consumer have diverged from Aliyun's `kb/wiki/` (visible by
   comparing `~/.hermes/omonigraph-vault/kb/wiki/` on Hermes vs
   `kb/wiki/` on Aliyun).
3. Operator-discretionary cadence — daily / weekly / on-demand. The
   downstream consumers tolerate up to 7 days of drift before SYNC-03
   verification (`git log -1 kb/wiki/`) becomes stale.

## Steps

```bash
# 1. SSH into Aliyun (alias from memory aliyun_vitaclaw_ssh.md)
ssh aliyun-vitaclaw

# 2. Inside Aliyun shell, navigate to the repo
cd /root/OmniGraph-Vault

# 3. Inspect what changed under kb/wiki/
git status kb/wiki/

# 4. Stage + commit (date-stamped message for traceability)
git add kb/wiki/
git commit -m "wiki: daily increment $(date +%Y-%m-%d)"

# 5. Push to origin/main
git push origin main
```

## Git auth fallback

Aliyun may not have a stored credential helper for `https://` remotes
on first run. If `git push` prompts for a password (or fails outright
with `fatal: Authentication failed`), use one of the two recovery
paths below.

### Path A — install a GitHub deploy key on Aliyun (preferred, one-time)

```bash
# On Aliyun (via `ssh aliyun-vitaclaw`)
ssh-keygen -t ed25519 -f ~/.ssh/aliyun_omnigraph_deploy -N ""
cat ~/.ssh/aliyun_omnigraph_deploy.pub
# → operator copies the printed pubkey, then on GitHub.com:
#   Repo Settings → Deploy keys → Add deploy key
#   • Title: aliyun-vitaclaw write
#   • Key:   <paste pubkey>
#   • [x] Allow write access   ← required so `git push` works, not only pull

# Configure git to use the deploy key
git remote set-url origin git@github.com:<owner>/OmniGraph-Vault.git

# Tell SSH which key to use for github.com
cat >> ~/.ssh/config <<'EOF'
Host github.com
  IdentityFile ~/.ssh/aliyun_omnigraph_deploy
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config

# Validate
ssh -T git@github.com    # expect: "Hi <owner>/OmniGraph-Vault! You've successfully authenticated..."
git push origin main     # expect: clean push, no prompt
```

After Path A is set up once, all subsequent `git push` calls from
Aliyun are frictionless.

### Path B — patch round-trip via local dev box (fallback)

Use this if deploy key registration is blocked (e.g., GitHub admin
not available, corp network restriction on outbound GitHub SSH).

```bash
# 1. On Aliyun, build a patch from the wiki commit instead of pushing
ssh aliyun-vitaclaw '
  cd /root/OmniGraph-Vault
  git format-patch HEAD~1 --stdout
' > /tmp/aliyun-wiki.patch

# 2. On the local dev box (corp Windows / WSL), apply the patch and push
cd ~/Desktop/OmniGraph-Vault
git checkout main
git pull --ff-only origin main
git apply /tmp/aliyun-wiki.patch
git add kb/wiki/
git commit -m "wiki: increment from aliyun $(date +%Y-%m-%d)"
git push origin main

# 3. Re-pull on Aliyun so its working tree matches origin
ssh aliyun-vitaclaw 'cd /root/OmniGraph-Vault && git pull --ff-only origin main'
```

Path A is preferred (one-time setup, then frictionless). Path B is
the fallback when Path A is blocked.

## Verification

After successful push:

```bash
# On Aliyun
git log -1 kb/wiki/ --format='%H %ai %s'

# On any consumer (Hermes / Databricks), 24h later, post-pull
cd <consumer-repo-checkout>
git pull
git log -1 kb/wiki/ --format='%H %ai %s'
# Both ends should print the same commit hash.
```

For the Databricks consumer specifically, use the sibling runbook
`docs/runbooks/aim-4-databricks-sync03-verify.md`.

## Cadence guidance

- **Daily** — simplest cadence; matches the daily-pull rhythm of
  SYNC-02. Recommended default.
- **Weekly** — acceptable if the wiki delta is small. SYNC-03
  verification tolerates up to 7 days of drift before staleness.
- **On-demand** — acceptable if wiki content is rare.

When in doubt: daily.

## Q4c context

This manual flow is the explicit Q4c trade-off for the
Aliyun-Ingest-Migration-v1 milestone. The auto-write-back hook on
Aliyun (post-write-to-`kb/wiki/` → push to `origin`) is a separate
milestone scope (see References). Until that milestone is chartered
and shipped, the operator is the auto-hook.

## References

- `.planning/PROJECT-Aliyun-Ingest-Migration-v1.md` Q4c
- `.planning/STATE-Aliyun-Ingest-Migration-v1.md` Decisions Q4c
- LLM-Wiki-Integration-P2 milestone (separate scope, not yet chartered) — owns the auto-write-back hook deferred from Q4c
- Sibling runbook: `docs/runbooks/aim-4-databricks-sync03-verify.md`
