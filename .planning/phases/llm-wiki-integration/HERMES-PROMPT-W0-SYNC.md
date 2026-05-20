# Hermes Operator Prompt — W0 Sync (Export + Symlink)

> Per CLAUDE.md Rule 5 — Claude does not SSH-mutate Hermes. The user forwards the relevant section to Hermes; Hermes runs it and pastes back any output.

This file has **two sections**. Run **Section 1 first** (read-only export). Run **Section 2 only after explicit user confirmation** (it replaces `~/wiki-omnigraph/`).

---

## Section 1 — Export wiki seed content (one-shot, read-only)

Forward this block to Hermes. It prints (does not modify) the existing `~/wiki-omnigraph/` content so the user can paste it back into the Claude session and W1 has accurate seed material to compare against.

```bash
echo "=== SCHEMA.md ==="
[ -f ~/wiki-omnigraph/SCHEMA.md ] && cat ~/wiki-omnigraph/SCHEMA.md || echo "(missing)"

echo ""
echo "=== index.md ==="
[ -f ~/wiki-omnigraph/index.md ] && cat ~/wiki-omnigraph/index.md || echo "(missing)"

echo ""
echo "=== log.md ==="
[ -f ~/wiki-omnigraph/log.md ] && cat ~/wiki-omnigraph/log.md || echo "(missing)"

echo ""
echo "=== entities/openclaw.md ==="
[ -f ~/wiki-omnigraph/entities/openclaw.md ] && cat ~/wiki-omnigraph/entities/openclaw.md || echo "(missing)"
```

This is read-only. Safe to run at any time.

---

## Section 2 — Set up production symlink

> **WAIT for user confirmation before running Section 2** — symlinking replaces the existing `~/wiki-omnigraph/` directory. The script backs it up to `~/wiki-omnigraph.backup-<timestamp>` first, but the user must explicitly OK the change because Hermes-side cron jobs read this path.

After:

1. The user has reviewed the Section 1 output and confirmed they have what they need from the existing dir
2. The OmniGraph-Vault repo on Hermes has been pulled to a commit that includes `kb/wiki/entities/openclaw.md`

…forward this block to Hermes:

```bash
set -e

cd ~/OmniGraph-Vault
git pull --ff-only

# Backup the existing dir (if it is a real dir, not already a symlink)
if [ -d ~/wiki-omnigraph ] && [ ! -L ~/wiki-omnigraph ]; then
  mv ~/wiki-omnigraph ~/wiki-omnigraph.backup-$(date +%Y%m%d-%H%M%S)
fi

# Create the symlink
ln -sfn ~/OmniGraph-Vault/kb/wiki ~/wiki-omnigraph

# Verify
ls -la ~/wiki-omnigraph
echo ""
echo "=== Symlink target now serves: ==="
ls ~/wiki-omnigraph/
```

Expected post-state:

```text
~/wiki-omnigraph -> ~/OmniGraph-Vault/kb/wiki
```

After this, Hermes-side `cd ~/OmniGraph-Vault && git pull --ff-only` is sufficient to refresh the wiki content — no copy step.

---

## Notes for the user

- Section 1 is harmless. Run it any time you want to compare existing Hermes content with what's now in this repo.
- Section 2 is the production cutover. Do not run it until W1 has at least replaced the placeholder `kb/wiki/entities/openclaw.md` with real generated content (otherwise the Hermes side would briefly serve a placeholder).
- If you want to revert: `rm ~/wiki-omnigraph && mv ~/wiki-omnigraph.backup-<timestamp> ~/wiki-omnigraph`.
